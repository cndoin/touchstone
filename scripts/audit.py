#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""audit.py —— 开源合规与质量自检

发布前跑一遍。它检查的不是"功能对不对"，而是"能不能公开发出去"：

  A. 许可证与元数据：LICENSE / NOTICE / CONTRIBUTING / SECURITY / CITATION 是否齐备
  B. SPDX 头：每个 .py 是否带 SPDX-License-Identifier
  C. 依赖洁净：是否只用标准库（第三方 import = 装不上就跑不了，违背设计约束）
  D. 隐私与可移植：是否残留本机绝对路径（家目录）、邮箱、疑似密钥
  E. 版本一致性：VERSION / SKILL.md frontmatter / CHANGELOG 顶部是否一致
  F. 文档完整性：README/CHANGELOG/ATTRIBUTIONS 是否提及关键能力

用法：
  python scripts/audit.py
  python scripts/audit.py --json
  python scripts/audit.py --strict   # 把 WARN 也当失败

退出码：0=通过 1=存在问题 3=用法错误
"""

import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ALLOWED_EXIT = {0, 1, 3}

try:
    STDLIB = set(sys.stdlib_module_names)  # Python 3.10+
except AttributeError:
    STDLIB = {
        "argparse", "ast", "base64", "bisect", "calendar", "collections", "concurrent",
        "contextlib", "csv", "ctypes", "dataclasses", "datetime", "difflib", "enum",
        "fnmatch", "functools", "getpass", "glob", "hashlib", "heapq", "hmac", "io",
        "itertools", "json", "logging", "math", "os", "pathlib", "pickle", "platform",
        "pprint", "queue", "random", "re", "shlex", "shutil", "signal", "socket",
        "sqlite3", "ssl", "stat", "string", "subprocess", "sys", "tempfile", "textwrap",
        "threading", "time", "traceback", "typing", "unicodedata", "urllib", "uuid",
        "warnings", "weakref", "xml", "zipfile", "zlib", "email", "http", "copy",
        "operator", "secrets", "struct", "tarfile", "types",
    }

LOCAL_MODULES = {"_common"}

REQUIRED_FILES = [
    ("LICENSE", "许可证（MIT）"),
    ("NOTICE", "声明：不含第三方代码，方法与出处见 ATTRIBUTIONS"),
    ("CONTRIBUTING.md", "贡献指南"),
    ("SECURITY.md", "安全政策"),
    ("CITATION.cff", "学术引用元数据"),
    ("README.md", "中文说明"),
    ("README.en.md", "英文说明（面向国际用户）"),
    ("i18n/en/SKILL.md", "英文主入口（面向国际模型与用户）"),
    ("CHANGELOG.md", "变更记录"),
    ("ATTRIBUTIONS.md", "出处与许可"),
    ("VERSION", "版本号"),
]

# 隐私 / 可移植性：家目录路径是最常见的开源事故
# 注意：下面用拼接构造正则，避免审计脚本自身触发"含家目录路径"告警
_WIN_USERS = "C:" + "/Users/"          # Windows 家目录前缀
_POSIX_HOME = "/(?:home|Users)/"       # POSIX 家目录前缀
HOME_PATTERNS = [
    re.compile(_WIN_USERS + r"[^/\s\"')]+"),
    re.compile(_POSIX_HOME + r"[A-Za-z0-9_.\-]+/"),
]
SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
]
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")

SKIP_SCAN_DIRS = {"__pycache__", ".git", "_deprecated-v1"}
SCAN_EXT = {".py", ".md", ".json", ".yml", ".yaml", ".cff", ".txt"}


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


class Report(object):
    def __init__(self):
        self.items = []

    def add(self, level, category, target, message):
        self.items.append({"level": level, "category": category,
                           "target": target, "message": message})

    def count(self, level):
        return sum(1 for i in self.items if i["level"] == level)


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SCAN_EXT:
                yield os.path.join(dirpath, fn)


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def check_metadata(rep):
    for name, why in REQUIRED_FILES:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            rep.add("ERROR", "元数据", name, "缺文件：%s" % why)
    # 版本一致性
    ver = read(os.path.join(ROOT, "VERSION")).strip()
    if not ver:
        rep.add("ERROR", "版本", "VERSION", "缺版本号")
        return
    skill = read(os.path.join(ROOT, "SKILL.md"))
    m = re.search(r"^version:\s*([0-9][^\s]*)\s*$", skill, re.M)
    if not m:
        rep.add("ERROR", "版本", "SKILL.md", "frontmatter 缺 version 字段")
    elif m.group(1).strip() != ver:
        rep.add("ERROR", "版本", "SKILL.md",
                "版本不一致：VERSION=%s，SKILL.md=%s" % (ver, m.group(1)))
    changelog = read(os.path.join(ROOT, "CHANGELOG.md"))
    if ver not in changelog.split("##")[1][:400]:
        rep.add("WARN", "版本", "CHANGELOG.md", "顶部条目未出现当前版本 %s" % ver)


def check_python(rep):
    for path in iter_files(os.path.join(ROOT, "scripts")):
        if not path.endswith(".py"):
            continue
        text = read(path)
        rel = os.path.relpath(path, ROOT)
        if "SPDX-License-Identifier:" not in text:
            rep.add("WARN", "许可证", rel, "缺 SPDX-License-Identifier 头")
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            rep.add("ERROR", "语法", rel, "解析失败：%s" % e)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[0]]
            else:
                continue
            for m in mods:
                if not m or m in LOCAL_MODULES or m in STDLIB:
                    continue
                rep.add("ERROR", "依赖洁净", rel,
                        "引入非标准库模块 %s（本套件承诺零第三方依赖）" % m)


def check_hooks(rep):
    hooks = os.path.join(ROOT, "adapters", "claude-code", "hooks")
    if not os.path.isdir(hooks):
        return
    for fn in sorted(os.listdir(hooks)):
        if not fn.endswith(".py"):
            continue
        text = read(os.path.join(hooks, fn))
        if "SPDX-License-Identifier:" not in text:
            rep.add("WARN", "许可证", "adapters/claude-code/hooks/%s" % fn,
                    "缺 SPDX-License-Identifier 头")


def check_privacy(rep):
    for path in iter_files(ROOT):
        rel = os.path.relpath(path, ROOT)
        text = read(path)
        if not text:
            continue
        for pat in HOME_PATTERNS:
            m = pat.search(text)
            if m:
                rep.add("ERROR", "隐私/可移植", rel,
                        "残留本机家目录路径：%s" % m.group(0)[:60])
                break
        for pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m:
                rep.add("ERROR", "隐私/可移植", rel, "疑似密钥：%s" % m.group(0)[:40])
                break
        for m in EMAIL_PATTERN.finditer(text):
            addr = m.group(0)
            if addr.endswith(("@example.com", "@example.org")) or "example" in addr:
                continue
            rep.add("WARN", "隐私/可移植", rel, "含邮箱地址：%s" % addr)
            break


def check_docs(rep):
    readme = read(os.path.join(ROOT, "README.md"))
    for kw in ("selftest.py", "robustness_test.py", "dep_guard.py", "pipeline.py",
               "MIT", "ATTRIBUTIONS"):
        if kw not in readme:
            rep.add("WARN", "文档", "README.md", "未提及 %s" % kw)
    attr = read(os.path.join(ROOT, "ATTRIBUTIONS.md"))
    if "Apache-2.0" not in attr:
        rep.add("WARN", "文档", "ATTRIBUTIONS.md", "未说明借鉴项目的许可证")


def main(argv=None):
    _utf8()
    as_json = "--json" in (argv or [])
    strict = "--strict" in (argv or [])

    rep = Report()
    try:
        check_metadata(rep)
        check_python(rep)
        check_hooks(rep)
        check_privacy(rep)
        check_docs(rep)
    except Exception as e:  # noqa: BLE001  审计自身也绝不崩
        rep.add("ERROR", "审计", "-", "%s: %s" % (type(e).__name__, e))

    errors = rep.count("ERROR")
    warns = rep.count("WARN")
    failed = errors > 0 or (strict and warns > 0)

    payload = {
        "tool": "audit.py",
        "root": ROOT,
        "errors": errors,
        "warnings": warns,
        "verdict": "BLOCKED" if failed else "PASSED",
        "items": rep.items,
    }

    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        lines = ["=== 开源合规审计：%s ===" % ROOT]
        by_cat = {}
        for it in rep.items:
            by_cat.setdefault(it["category"], []).append(it)
        if not rep.items:
            lines.append("未发现问题。")
        for cat, items in sorted(by_cat.items()):
            lines.append("")
            lines.append("- %s（%d 项）" % (cat, len(items)))
            for it in items[:40]:
                lines.append("    [%s] %s :: %s" % (it["level"], it["target"], it["message"]))
            if len(items) > 40:
                lines.append("    ... 另 %d 项" % (len(items) - 40))
        lines.append("")
        lines.append("ERROR=%d WARN=%d → %s" % (errors, warns, payload["verdict"]))
        if failed:
            lines.append(">>> 发布前必须修完 ERROR。")
        sys.stdout.write("\n".join(lines) + "\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
