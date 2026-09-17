#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""validate-metadata.py —— 仓库元数据与资产校验（CI 用，不属于产品脚本）

产品脚本（scripts/*.py）必须零第三方依赖，但 CI 可以用 PyYAML。
这个脚本因此放在 .github/ 下，不参与 scripts/ 的依赖审计。

检查项：
  A. 所有 .json 能解析
  B. 所有 .yml/.yaml/.cff 能解析（有 PyYAML 时）
  C. CITATION.cff 必填字段齐备、version 与 VERSION 一致、无占位符残留
  D. 文档里引用的相对路径真实存在
  E. 无本机绝对路径 / 邮箱 / 匿名占位符残留

退出码：0=全部通过  1=存在失败  3=用法错误
"""

import json
import os
import re
import sys

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "_deprecated-v1"}

# 公开发布前必须清掉的占位符
PLACEHOLDERS = [
    "github.com/anonymous",
    "example.org/",
    "example.com/",
    "your-",
    "TODO",
    "FIXME",
]

# CFF 1.2.0 必填字段
CFF_REQUIRED = ["cff-version", "message", "authors", "title"]

DOC_FILES = [
    "README.md",
    "README.en.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "ATTRIBUTIONS.md",
    "NOTICE",
    "SKILL.md",
    "i18n/en/SKILL.md",
]

# 反引号里的相对路径：scripts/audit.py、references/01-core-doctrine.md ...
PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|yml|yaml|cff|toml))`")

problems = []


def fail(msg):
    problems.append(msg)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def walk_ext(exts):
    """遍历仓库，返回指定后缀的文件（跳过 SKIP_DIRS）"""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ── A. JSON
json_files = walk_ext({".json"})
for p in json_files:
    try:
        json.loads(read(p))
    except Exception as e:
        fail("JSON 解析失败 %s: %s" % (rel(p), e))
print("A. JSON 解析：%d 个文件" % len(json_files))

# ── B. YAML
try:
    import yaml  # type: ignore
except ImportError:
    print("B. YAML 解析：跳过（无 PyYAML）")
    yaml = None

if yaml is not None:
    yaml_files = walk_ext({".yml", ".yaml", ".cff"})
    for p in yaml_files:
        try:
            yaml.safe_load(read(p))
        except Exception as e:
            # 带上出错的行列号，否则 CI 里只能看到一句 "while scanning for the next token"
            mark = getattr(e, "problem_mark", None)
            where = ""
            if mark is not None:
                where = " (第 %d 行第 %d 列)" % (mark.line + 1, mark.column + 1)
            fail("YAML 解析失败 %s%s: %s" % (rel(p), where, str(e).split("\n")[0]))
    print("B. YAML 解析：%d 个文件" % len(yaml_files))

# ── C. CITATION.cff
cff_path = os.path.join(ROOT, "CITATION.cff")
if not os.path.exists(cff_path):
    fail("缺少 CITATION.cff")
elif yaml is None:
    print("C. CITATION.cff：跳过（无 PyYAML）")
else:
    cff = yaml.safe_load(read(cff_path)) or {}
    for k in CFF_REQUIRED:
        if k not in cff:
            fail("CITATION.cff 缺必填字段：%s" % k)
    ver_file = read(os.path.join(ROOT, "VERSION")).strip()
    ver_cff = str(cff.get("version", "")).strip()
    if ver_cff != ver_file:
        fail("CITATION.cff version=%r 与 VERSION=%r 不一致" % (ver_cff, ver_file))
    # preferred-citation 里的 version 是最容易漏改的一处（缩进一层，肉眼容易跳过）
    pc = cff.get("preferred-citation")
    if isinstance(pc, dict) and "version" in pc:
        ver_pc = str(pc["version"]).strip()
        if ver_pc != ver_file:
            fail("CITATION.cff preferred-citation.version=%r 与 VERSION=%r 不一致"
                 % (ver_pc, ver_file))
    # 每条参考文献都必须有作者
    refs = cff.get("references") or []
    no_author = [r.get("title", "?") for r in refs if not r.get("authors")]
    if no_author:
        fail("CITATION.cff 有条目缺 authors：%s" % no_author)
    print("C. CITATION.cff：%d 条参考文献，version=%s" % (len(refs), ver_cff))

# ── D. 文档引用的文件存在
# 文档里大量使用裸文件名（如 `selftest.py` 指 scripts/selftest.py），
# 所以先建一份 basename → 路径 的索引；唯一命中即视为有效引用。
basename_index = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        basename_index.setdefault(fn, []).append(
            rel(os.path.join(dirpath, fn))
        )


def resolve_ref(target, doc_dir):
    """返回 (是否解析成功, 说明)。target 可能是相对路径或裸文件名"""
    if os.path.exists(os.path.join(ROOT, target)):
        return True, target
    # 相对文档所在目录（i18n/en/SKILL.md 里的相对引用）
    alt = os.path.normpath(os.path.join(doc_dir, target)).replace("\\", "/")
    if os.path.exists(os.path.join(ROOT, alt)):
        return True, alt
    # 裸文件名：全仓库唯一命中
    base = os.path.basename(target)
    cands = basename_index.get(base, [])
    if len(cands) == 1:
        return True, cands[0]
    if len(cands) > 1:
        return False, "歧义（%d 处同名：%s）" % (len(cands), ", ".join(cands[:3]))
    return False, "不存在"


checked_refs = 0
for name in DOC_FILES:
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        fail("文档缺失：%s" % name)
        continue
    doc_dir = os.path.dirname(name)
    for m in PATH_RE.finditer(read(p)):
        target = m.group(1)
        if "://" in target:
            continue
        checked_refs += 1
        ok, why = resolve_ref(target, doc_dir)
        if not ok:
            fail("%s 引用 ` %s ` → %s" % (name, target, why))
print("D. 文档引用：检查 %d 处" % checked_refs)

# ── E. 占位符 / 隐私残留
SCAN_EXT = {".md", ".py", ".json", ".yml", ".yaml", ".cff", ".txt", ".toml"}
hits = 0
for p in walk_ext(SCAN_EXT):
    relp = rel(p)
    if relp.startswith(".github/") or relp in ("CHANGELOG.md",):
        continue
    text = read(p)
    for token in PLACEHOLDERS:
        if token in text:
            fail("%s 残留占位符 %r" % (relp, token))
            hits += 1
    # 本机绝对路径
    for m in re.finditer(r"[A-Za-z]:\\Users\\|/Users/[A-Za-z0-9_.-]+/|/home/[A-Za-z0-9_.-]+/", text):
        fail("%s 残留本机绝对路径：%s" % (relp, m.group(0)))
        hits += 1
    # 邮箱
    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        if "example" in m.group(0).lower():
            continue
        fail("%s 残留邮箱：%s" % (relp, m.group(0)))
        hits += 1
print("E. 占位符/隐私扫描：%d 处问题" % hits)

# ── 汇总
print()
if problems:
    print("FAILED —— %d 个问题：" % len(problems))
    for x in problems:
        print("  ✗ " + x)
    sys.exit(EXIT_FAIL)

print("PASSED —— 元数据与资产校验全部通过")
sys.exit(EXIT_OK)
