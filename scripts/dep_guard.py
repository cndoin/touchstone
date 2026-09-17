#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""dep_guard.py —— 依赖与符号幻觉防护（slopsquatting 防御）

为什么单独做这个：编码场景最高危的幻觉不是"说错话"，是**写进代码里的假东西**。
  - 幻影依赖：代码 import 了一个 manifest 里没有的包
  - 包幻觉 → slopsquatting：模型编造一个"听起来合理"的包名，攻击者抢注同名包，
    下一次 npm install / pip install 就变成供应链攻击
  - 幻影符号：包存在，但导出的函数/类是编的
  - 幻影路径：内部相对路径指向不存在的文件

检查项：
  [1] 提取 import/require/use/from 语句（Python / JS·TS / Rust / Go / Kotlin·Java）
  [2] 内部导入 → 文件是否真的存在（带扩展名补全）+ 导出符号是否存在
  [3] 外部包 → 是否在 manifest 中声明（未声明 = 幻影依赖，BLOCK）
  [4] 外部包 → registry 是否真的存在（npm / PyPI）
  [5] slopsquat 特征：首次发布时间 < 90 天 / 无仓库链接 / 维护者可疑
  [6] typosquat 特征：与知名包名编辑距离 <= 2

用法：
  python dep_guard.py --root .
  python dep_guard.py --root . --files src/a.py src/b.ts --json
  python dep_guard.py --root . --offline           # 只做本地判定，不联网
  python dep_guard.py --root . --strict            # 把 SUSPICIOUS/WARN 也当失败

退出码：0=通过 1=存在 BLOCK（或 --strict 下有可疑项） 2=存在未验证 3=用法错误
注意：BLOCK 意味着"代码里有不存在的东西"，必须修，不是建议。
"""

import argparse
import difflib
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    ArgParser,  # noqa: E402
    DEFAULT_UA,
    cache_get,
    cache_set,
    default_cache_dir,
    emit,
    err,
    load_json_file,
    map_parallel,
)
from _common import EXIT_FAIL, EXIT_OK, EXIT_UNVERIFIED, EXIT_USAGE, _force_utf8  # noqa: E402

BLOCK = "BLOCK"
WARN = "WARN"
SUSPICIOUS = "SUSPICIOUS"
PASS = "PASS"
UNVERIFIED = "UNVERIFIED"

SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", "build", "dist", "target",
    ".gradle", ".idea", ".vscode", "venv", ".venv", "env", ".tox", ".mypy_cache",
    "out", "bin", "obj", ".next", "coverage", ".pytest_cache",
}
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".jar", ".class", ".so", ".dll",
    ".exe", ".mp4", ".mp3", ".woff", ".woff2", ".ttf", ".lock", ".min.js",
}
SCAN_EXT = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".rs", ".go", ".kt", ".kts", ".java", ".gradle.kts",
}
MAX_FILE_BYTES = 2 * 1024 * 1024

# 按扩展名选语言，避免"Python 规则误吞 TS 的 import"这类跨语言误判
LANGS_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "js", ".tsx": "js",
    ".rs": "rust", ".go": "go",
    ".kt": "kotlin", ".kts": "kotlin", ".java": "java",
}

# 语言 → 包生态；生态 → manifest（仅当该 manifest 存在时才做"未声明依赖"判定）
ECO_BY_LANG = {"python": "pypi", "js": "npm", "rust": "crates", "go": "go",
               "kotlin": "gradle", "java": "gradle"}
MANIFEST_BY_ECO = {
    "pypi": ["requirements.txt", "pyproject.toml", "Pipfile"],
    "npm": ["package.json"],
    "crates": ["Cargo.toml"],
    "go": ["go.mod"],
    "gradle": [],  # gradle 的 import 前缀与 group:artifact 非一一对应，不做未声明判定
}

# 标准库 / 内置模块：不参与幻影依赖判定
PY_STDLIB = {
    "os", "sys", "json", "re", "time", "math", "io", "abc", "enum", "copy", "typing",
    "pathlib", "dataclasses", "itertools", "functools", "collections", "subprocess",
    "asyncio", "logging", "hashlib", "random", "string", "textwrap", "unittest",
    "datetime", "urllib", "http", "socket", "threading", "uuid", "csv", "argparse",
    "contextlib", "shutil", "tempfile", "warnings", "traceback", "inspect", "importlib",
}
NODE_BUILTINS = {
    "fs", "path", "http", "https", "os", "util", "crypto", "events", "stream", "buffer",
    "url", "child_process", "net", "dns", "zlib", "querystring", "timers", "assert",
    "process", "module", "worker_threads", "perf_hooks", "readline", "tty", "vm",
}

# 导入语句提取规则：语言 → 正则列表
IMPORT_PATTERNS = {
    "python": [re.compile(r"^\s*from\s+([A-Za-z0-9_.\-]+)\s+import"),
               re.compile(r"^\s*import\s+([A-Za-z0-9_.\-]+)")],
    "rust": [re.compile(r"^\s*use\s+([A-Za-z0-9_:]+)")],
    "go": [re.compile(r"^\s*import\s+\(?\s*\"([^\"]+)\""),
           re.compile(r"^\s*\"([^\"]+\.[a-z]{2,}/[^\"]+)\"")],
    "kotlin": [re.compile(r"^\s*import\s+([A-Za-z0-9_.\-]+)")],
    "java": [re.compile(r"^\s*import\s+(?:static\s+)?([A-Za-z0-9_.]+)")],
    "js": [re.compile(r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]"),
           re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]"),
           re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)")],
}

MANIFESTS = {
    "package.json": "npm",
    "requirements.txt": "pypi",
    "pyproject.toml": "pypi",
    "Pipfile": "pypi",
    "Cargo.toml": "crates",
    "go.mod": "go",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
}

# typosquat 检测用的知名包名样本（只是常见名，不是完整清单）
WELL_KNOWN = {
    "npm": ["react", "react-dom", "lodash", "axios", "express", "webpack", "typescript",
            "eslint", "prettier", "next", "vue", "jest", "moment", "chalk", "commander",
            "uuid", "dayjs", "zod", "redux", "mobx", "vite", "rollup", "babel"],
    "pypi": ["requests", "numpy", "pandas", "flask", "django", "pytest", "click", "rich",
             "fastapi", "torch", "scipy", "scikit-learn", "boto3", "sqlalchemy", "pydantic",
             "pillow", "matplotlib", "celery", "uvicorn", "httpx", "black", "mypy"],
}

FRESH_PACKAGE_DAYS = 90


def git_changed_files(root, ref):
    """取 git 变更文件（增/改），用于增量核查。git 不可用时返回 None。"""
    try:
        r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=ACM", ref],
                           cwd=root, capture_output=True, text=True,
                           timeout=30, errors="replace")
        if r.returncode != 0:
            return None
        return [os.path.join(root, ln.strip())
                for ln in (r.stdout or "").splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return None


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def iter_files(root, only=None):
    """产出待扫描文件：跳过依赖目录、二进制、超大文件、无后缀匹配的文件。"""
    if only:
        for p in only:
            if os.path.isfile(p):
                yield p
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXT or ext not in SCAN_EXT:
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield full


# 命名导入（可可靠校验导出符号）：(语言, 正则, 模块分组, 符号分组)
NAMED_SYMBOL_PATTERNS = {
    "python": [(re.compile(r"^\s*from\s+([A-Za-z0-9_.\-]+)\s+import\s+([A-Za-z0-9_,\s]+)"), 1, 2)],
    "js": [(re.compile(r"^\s*import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]"), 2, 1)],
    "rust": [(re.compile(r"^\s*use\s+([A-Za-z0-9_:]+)::\{([^}]*)\}"), 1, 2)],
    # Kotlin/Java 的 import 末段即类名，可直接校验
    "kotlin": [(re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)"), 1, None)],
    "java": [(re.compile(r"^\s*import\s+(?:static\s+)?([A-Za-z0-9_.]+)"), 1, None)],
}


def extract_named_symbols(path):
    """提取"可校验"的命名符号：[(module, symbol, lineno)]。

    只处理命名导入 —— 默认导入（`import bar from './x'`）的本地绑定名
    无法从路径推断，强行校验只会制造误报。
    """
    ext = os.path.splitext(path)[1].lower()
    lang = LANGS_BY_EXT.get(ext)
    rules = NAMED_SYMBOL_PATTERNS.get(lang) or []
    if not rules:
        return []
    out = []
    for i, line in enumerate(read_text(path).splitlines(), 1):
        for pat, mod_g, sym_g in rules:
            m = pat.search(line)
            if not m:
                continue
            mod = m.group(mod_g)
            if sym_g is None:
                syms = [mod.split(".")[-1]]
            else:
                raw = m.group(sym_g) if sym_g <= m.re.groups else ""
                syms = [s.strip().split(" as ")[0].strip() for s in raw.split(",")]
            for s in syms:
                if s and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
                    out.append((mod, s, i))
            break
    return out


def extract_imports(path):
    """返回 [(module, language, lineno)]。按扩展名选规则，避免跨语言误判。"""
    ext = os.path.splitext(path)[1].lower()
    lang = LANGS_BY_EXT.get(ext)
    if not lang:
        return []
    pats = IMPORT_PATTERNS.get(lang) or []
    text = read_text(path)
    if not text:
        return []
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for pat in pats:
            m = pat.search(line)
            if m:
                mod = next((g for g in m.groups() if g), None)
                if mod:
                    out.append((mod, lang, i))
                break
    return out


def is_internal(mod):
    return mod.startswith((".", "/", "@/", "~/")) or mod.startswith("src/")


def resolve_internal(root, source_file, mod):
    """相对导入 → 真实文件路径。找不到返回 None。"""
    base_dir = os.path.dirname(os.path.abspath(source_file))
    if mod.startswith("@/"):
        cand = os.path.join(root, mod[2:])
    elif mod.startswith("~/"):
        cand = os.path.join(root, mod[2:])
    else:
        cand = os.path.join(base_dir, mod)
    candidates = [cand]
    ext = os.path.splitext(cand)[1]
    if not ext:
        candidates += [cand + e for e in (".py", ".kt", ".java", ".ts", ".tsx", ".js", ".jsx", ".rs")]
        candidates += [os.path.join(cand, "index" + e) for e in (".ts", ".tsx", ".js", ".jsx")]
        candidates += [os.path.join(cand, "__init__.py")]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def symbol_exported(path, symbol, lang):
    """检查导出的符号是否真的存在于目标文件（近似：源码文本匹配）。"""
    text = read_text(path)
    if not text:
        return None
    if lang == "python":
        pats = [r"^\s*def\s+%s\b" % re.escape(symbol),
                r"^\s*class\s+%s\b" % re.escape(symbol),
                r"^\s*%s\s*=" % re.escape(symbol)]
    elif lang in ("kotlin", "java"):
        pats = [r"\b(?:fun|class|object|interface|val|var)\s+%s\b" % re.escape(symbol)]
    elif lang == "rust":
        pats = [r"\b(?:pub\s+)?(?:fn|struct|enum|trait|const|static)\s+%s\b" % re.escape(symbol)]
    else:
        pats = [r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+%s\b" % re.escape(symbol),
                r"export\s*\{[^}]*\b%s\b" % re.escape(symbol),
                r"module\.exports\.%s\b" % re.escape(symbol)]
    for p in pats:
        if re.search(p, text, re.MULTILINE):
            return True
    return False


def load_manifest(root):
    """按生态收集已声明的包名。返回 ({eco: set(pkg)}, [manifest 文件名])。

    关键设计：**只在该生态的 manifest 存在时**才把"未声明"判为幻影依赖。
    否则 npm 项目里的 Python 文件会被 package.json 误判（跨生态误报）。
    """
    declared = {}
    used = []

    def add(eco, name):
        declared.setdefault(eco, set()).add(name)

    p = os.path.join(root, "package.json")
    if os.path.exists(p):
        used.append("package.json")
        try:
            data = json.loads(read_text(p))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for k in (data.get(section) or {}):
                    add("npm", k)
        except Exception:
            pass

    for name in ("requirements.txt", "pyproject.toml", "Pipfile"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            used.append(name)
            for m in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:==|>=|<=|~=|>|<|\[|@|$)",
                                 read_text(p), re.M):
                add("pypi", m.group(1))

    p = os.path.join(root, "Cargo.toml")
    if os.path.exists(p):
        used.append("Cargo.toml")
        section = False
        for line in read_text(p).splitlines():
            if line.strip().startswith("["):
                section = "dependencies" in line
                continue
            if section:
                m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*=", line)
                if m:
                    add("crates", m.group(1))

    p = os.path.join(root, "go.mod")
    if os.path.exists(p):
        used.append("go.mod")
        for m in re.finditer(r"^\s*([^\s]+)\s+v[0-9]", read_text(p), re.M):
            add("go", m.group(1))

    return declared, used


def norm_pkg(mod):
    """import 模块名 → 包名（npm 带 scope 保留前两段）。"""
    parts = mod.split("/")
    if mod.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def registry_lookup(eco, pkg, cfg):
    """查 registry：存在性 + 首次发布时间（slopsquat 特征）。网络失败 → UNVERIFIED。"""
    if cfg.get("offline"):
        return {"status": UNVERIFIED, "detail": "--offline 跳过联网核查"}
    cache_dir = cfg.get("cache_dir")
    cached = cache_get(cache_dir, "dep", "%s|%s" % (eco, pkg))
    if cached:
        return cached
    info = {"status": UNVERIFIED, "detail": "未知"}
    try:
        if eco == "npm":
            url = "https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@/")
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=cfg.get("timeout", 8)) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            if data.get("error"):
                info = {"status": BLOCK, "detail": "npm registry 上不存在该包"}
            else:
                created = None
                times = data.get("time") or {}
                for k in ("created", "0.0.0", "1.0.0"):
                    if times.get(k):
                        created = times[k]
                        break
                info = {"status": PASS, "detail": "npm 存在",
                        "created": created, "repo": (data.get("repository") or {}).get("url")}
        elif eco == "pypi":
            url = "https://pypi.org/pypi/%s/json" % urllib.parse.quote(pkg)
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
            with urllib.request.urlopen(req, timeout=cfg.get("timeout", 8)) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            releases = data.get("releases") or {}
            created = None
            for files in releases.values():
                for f in files:
                    t = f.get("upload_time") or f.get("upload_time_iso_8601")
                    if t and (created is None or t < created):
                        created = t
            info = {"status": PASS, "detail": "PyPI 存在", "created": created,
                    "repo": (data.get("info") or {}).get("home_page")}
        else:
            info = {"status": UNVERIFIED, "detail": "该生态暂无 registry 核查（%s）" % eco}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            info = {"status": BLOCK, "detail": "registry 404：包不存在"}
        else:
            info = {"status": UNVERIFIED, "detail": "registry HTTP %s" % e.code}
    except Exception as e:  # noqa: BLE001
        info = {"status": UNVERIFIED, "detail": "%s: %s" % (type(e).__name__, e)}
    cache_set(cache_dir, "dep", "%s|%s" % (eco, pkg), info)
    return info


def freshness_flag(created):
    """首版发布时间距今 < 90 天 → 新包（slopsquat 典型特征）。"""
    if not created:
        return None
    try:
        s = str(created).replace("Z", "").strip()
        fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in s else "%Y-%m-%dT%H:%M:%S"
        t = time.mktime(time.strptime(s[:26], fmt)) if "T" in s else \
            time.mktime(time.strptime(s[:10], "%Y-%m-%d"))
        days = (time.time() - t) / 86400.0
        if days < FRESH_PACKAGE_DAYS:
            return int(days)
    except Exception:
        return None
    return None


def typosquat_flag(eco, pkg):
    close = difflib.get_close_matches(pkg, WELL_KNOWN.get(eco, []), n=1, cutoff=0.85)
    if close and close[0] != pkg:
        return close[0]
    return None


def analyze(root, files=None, cfg=None):
    cfg = cfg or {}
    declared, manifests = load_manifest(root)
    findings = []

    scanned = 0
    for path in iter_files(root, files):
        scanned += 1
        for mod, lang, lineno in extract_imports(path):
            rel = os.path.relpath(path, root) if root else path
            if is_internal(mod):
                resolved = resolve_internal(root, path, mod)
                if not resolved:
                    findings.append({
                        "level": BLOCK, "kind": "missing_path", "file": rel, "line": lineno,
                        "module": mod, "detail": "内部导入路径不存在（幻影路径）",
                    })
                continue

            pkg = norm_pkg(mod)
            eco = ECO_BY_LANG.get(lang)

            # 标准库 / 内置模块不参与幻影依赖判定
            if (lang == "python" and pkg in PY_STDLIB) or \
               (lang == "js" and (pkg in NODE_BUILTINS or pkg.startswith("node:"))):
                continue

            # 该生态 manifest 存在时，未在 manifest 中声明 = 幻影依赖
            if eco and eco in declared and pkg not in declared.get(eco, set()):
                findings.append({
                    "level": BLOCK, "kind": "phantom_dependency", "file": rel, "line": lineno,
                    "module": mod,
                    "detail": "%s manifest（%s）中未声明该依赖 —— 幻影依赖" % (
                        eco, ",".join(MANIFEST_BY_ECO.get(eco, []) or ["?"])),
                })
                continue

            if eco not in ("npm", "pypi"):
                findings.append({
                    "level": UNVERIFIED, "kind": "eco_unsupported", "file": rel, "line": lineno,
                    "module": mod,
                    "detail": "%s 生态暂无 registry 自动核查，需人工确认（不是通过）" % eco,
                })
                continue

            info = registry_lookup(eco, pkg, cfg)
            if info.get("status") == BLOCK:
                findings.append({
                    "level": BLOCK, "kind": "package_not_exist", "file": rel, "line": lineno,
                    "module": mod, "detail": info.get("detail", "包不存在"),
                })
                continue
            if info.get("status") == UNVERIFIED:
                findings.append({
                    "level": UNVERIFIED, "kind": "registry_unverified", "file": rel,
                    "line": lineno, "module": mod, "detail": info.get("detail", "未验证"),
                })
                continue

            days = freshness_flag(info.get("created"))
            if days is not None:
                findings.append({
                    "level": SUSPICIOUS, "kind": "fresh_package", "file": rel, "line": lineno,
                    "module": mod,
                    "detail": "该包首版发布于 %d 天前（<%d 天）—— slopsquatting 典型特征，人工确认后再装"
                              % (days, FRESH_PACKAGE_DAYS),
                })
            near = typosquat_flag(eco, pkg)
            if near:
                findings.append({
                    "level": SUSPICIOUS, "kind": "typosquat", "file": rel, "line": lineno,
                    "module": mod, "detail": "与知名包 %s 高度相似，疑似 typosquat" % near,
                })
            if not info.get("repo"):
                findings.append({
                    "level": WARN, "kind": "no_repo", "file": rel, "line": lineno,
                    "module": mod, "detail": "registry 中无仓库链接（低可信信号）",
                })

    # 命名导入的导出符号校验（单独一遍；只查命名导入，默认导入不查，避免误报）
    for path in iter_files(root, files):
        lang = LANGS_BY_EXT.get(os.path.splitext(path)[1].lower())
        for mod, sym, lineno in extract_named_symbols(path):
            if not is_internal(mod):
                continue  # 外部包的符号在 registry 层面无法可靠判定，不制造误报
            resolved = resolve_internal(root, path, mod)
            if not resolved or symbol_exported(resolved, sym, lang) is not False:
                continue
            rel = os.path.relpath(path, root) if root else path
            findings.append({
                "level": WARN, "kind": "missing_symbol", "file": rel, "line": lineno,
                "module": mod, "detail": "在 %s 中未找到导出符号 %s" % (
                    os.path.relpath(resolved, root) if root else resolved, sym),
            })

    return findings, {"manifests": manifests,
                      "declared": {k: sorted(v) for k, v in declared.items()},
                      "files_scanned": scanned}


def main(argv=None):
    _force_utf8()
    p = ArgParser(prog="dep_guard.py",
                                description="依赖与符号幻觉防护（幻影 import / 包幻觉 / slopsquatting）")
    p.add_argument("--root", default=".", help="项目根目录")
    p.add_argument("--files", nargs="*", default=None, help="只扫描这些文件（默认扫全项目）")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--offline", action="store_true", help="不联网（只做本地判定）")
    p.add_argument("--strict", action="store_true", help="把 SUSPICIOUS/WARN 也算失败")
    p.add_argument("--timeout", type=float, default=8.0, help="registry 请求超时秒数")
    p.add_argument("--cache-dir", default=None, help="缓存目录")
    p.add_argument("--allowlist", help="允许的包名清单文件（每行一个）")
    p.add_argument("--changed-only", action="store_true",
                   help="只扫描 git 变更文件（增量核查，快很多）")
    p.add_argument("--git-ref", default="HEAD",
                   help="--changed-only 的比对基准（默认 HEAD）")
    a = p.parse_args(argv)

    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        err("项目根目录不存在：%s" % root)
        return EXIT_USAGE

    files = a.files
    if a.changed_only:
        changed = git_changed_files(root, a.git_ref)
        if changed is None:
            err("无法获取 git 变更（不在 git 仓库中，或 git 不可用）—— "
                "增量核查无法进行，请去掉 --changed-only 或改用 --files")
            return EXIT_USAGE
        changed = [f for f in changed if os.path.isfile(f)]
        if not changed:
            emit(None, as_json=False, human_lines=[
                "=== dep_guard：%s（增量，基准 %s）===" % (root, a.git_ref),
                "无变更文件，跳过扫描。",
            ])
            return EXIT_OK
        files = changed
        err("增量模式：基准 %s，待扫文件 %d 个" % (a.git_ref, len(files)))

    cfg = {
        "offline": a.offline,
        "timeout": a.timeout,
        "cache_dir": None if a.offline else (a.cache_dir or default_cache_dir()),
    }

    allow = set()
    if a.allowlist:
        try:
            with open(a.allowlist, "r", encoding="utf-8", errors="replace") as f:
                allow = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
        except OSError as e:
            err("读取 allowlist 失败：%s" % e)

    findings, meta = analyze(root, a.files, cfg)
    if allow:
        findings = [f for f in findings if f.get("module") not in allow
                    and norm_pkg(f.get("module", "")) not in allow]

    counts = {}
    for f in findings:
        counts[f["level"]] = counts.get(f["level"], 0) + 1

    blocked = counts.get(BLOCK, 0) > 0
    suspicious = counts.get(SUSPICIOUS, 0) + counts.get(WARN, 0)
    unverified = counts.get(UNVERIFIED, 0) > 0

    payload = {
        "tool": "dep_guard.py",
        "root": root,
        "meta": meta,
        "counts": counts,
        "findings": findings,
        "hint": "BLOCK=代码里有不存在的东西，必须改；SUSPICIOUS=安装前人工确认。",
    }

    if a.json:
        emit(payload, as_json=True)
    else:
        lines = ["=== dep_guard：%s ===" % root]
        lines.append("扫描 %d 个文件" % meta.get("files_scanned", 0))
        if meta["manifests"]:
            for eco, pkgs in (meta.get("declared") or {}).items():
                lines.append("  %s manifest（%s）已声明 %d 个包" %
                             (eco, ", ".join(MANIFEST_BY_ECO.get(eco, []) or []), len(pkgs)))
        else:
            lines.append("未检测到 manifest —— 外部包判定退化为 registry 核查（本地判定不做）")
        lines.append("")
        if not findings:
            lines.append("未发现依赖/符号幻觉。")
        for f in findings:
            lines.append("[%s] %s:%s  %s :: %s" % (
                f["level"], f["file"], f.get("line"), f["module"], f["detail"]))
        lines.append("")
        lines.append("合计：BLOCK=%d SUSPICIOUS=%d WARN=%d UNVERIFIED=%d" % (
            counts.get(BLOCK, 0), counts.get(SUSPICIOUS, 0),
            counts.get(WARN, 0), counts.get(UNVERIFIED, 0)))
        if blocked:
            lines.append(">>> 存在 BLOCK：代码里引用了不存在的包/路径，必须修。")
        if counts.get(SUSPICIOUS, 0):
            lines.append(">>> 存在 SUSPICIOUS：安装这些依赖前先人工确认（slopsquatting 风险）。")
        emit(None, as_json=False, human_lines=lines)

    if blocked or (a.strict and suspicious):
        return EXIT_FAIL
    if unverified:
        return EXIT_UNVERIFIED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
