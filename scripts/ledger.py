#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""ledger.py —— 项目账本（大项目反记忆漂移的核心工具）

为什么需要它：项目的真实状态在磁盘上，模型的认知在上下文里。
两者之间没有强制同步机制时，"我记得我们用的是 Hilt" 就会漂移成 Koin。

账本记四类东西：
  decision   架构决策与技术选型
  contract   接口/数据契约
  convention 命名与代码风格约定
  state      模块完成状态
  constraint 硬约束（不许违反）
  fact       值得长期记住的项目事实

每条可以挂一个 verify 条件，让 check 子命令**实际读文件**去比对：
  {"type": "file_exists",   "path": "..."}
  {"type": "file_contains", "path": "...", "pattern": "hilt"}
  {"type": "dir_exists",    "path": "..."}
  {"type": "command",       "cmd": "..."}   # exit code 0 视为满足

用法：
  python ledger.py add --kind decision --subject "DI 框架" --value "Hilt" \
      --source "docs/arch.md#3" --verify-file app/build.gradle.kts --verify-pattern hilt
  python ledger.py get --subject "DI 框架"
  python ledger.py list [--kind decision] [--status confirmed]
  python ledger.py check --root . [--drift] [--fix]
  python ledger.py remove --id 3

退出码（check）：0=账本与现实一致 1=存在 drift/fail 3=用法错误
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    ArgParser,  # noqa: E402
    EXIT_FAIL,
    EXIT_OK,
    EXIT_USAGE,
    _force_utf8,
    emit,
    err,
    load_json_file,
    load_json_object,
    write_json_file,
)

DEFAULT_FILE = os.path.join(".touchstone", "ledger.json")
VALID_KINDS = {"decision", "contract", "convention", "state", "constraint", "fact"}
VALID_STATUS = {"confirmed", "observed", "assumed", "stale", "unknown"}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def load_ledger(path):
    if not os.path.exists(path):
        return {"version": 2, "entries": []}
    data = load_json_object(path, "账本")
    if not isinstance(data, dict) or "entries" not in data:
        err("账本格式不对（应含 entries 数组）：%s" % path)
        sys.exit(EXIT_USAGE)
    return data


def next_id(entries):
    return (max([e.get("id", 0) for e in entries] or [0]) + 1)


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def run_verify(verify, root, timeout=10):
    """实际执行 verify 条件。返回 (status, detail)。status: pass|fail|unverified"""
    if not isinstance(verify, dict) or not verify.get("type"):
        return "unverified", "verify 字段缺失或格式不对"
    vtype = verify.get("type")
    path = verify.get("path")
    full = os.path.join(root, path) if (path and not os.path.isabs(path)) else path

    if vtype in ("file_exists", "dir_exists"):
        ok = os.path.exists(full) and (
            os.path.isdir(full) if vtype == "dir_exists" else os.path.isfile(full))
        return ("pass" if ok else "fail"), "%s: %s" % (vtype, full)

    if vtype == "file_contains":
        pattern = verify.get("pattern")
        if not pattern:
            return "unverified", "file_contains 缺 pattern"
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except FileNotFoundError:
            return "fail", "文件不存在：%s" % full
        except OSError as e:
            return "unverified", "读取失败：%s" % e
        try:
            hit = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            return "unverified", "pattern 不是合法正则：%s" % e
        return ("pass" if hit else "fail"), "在 %s 中%s匹配 /%s/" % (
            full, "" if hit else "未", pattern)

    if vtype == "command":
        cmd = verify.get("cmd")
        if not cmd:
            return "unverified", "command 缺 cmd"
        try:
            proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                                  text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            return "unverified", "命令超时"
        except Exception as e:
            return "unverified", "%s: %s" % (type(e).__name__, e)
        return ("pass" if proc.returncode == 0 else "fail"), "exit=%d | %s" % (
            proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()[:200])

    return "unverified", "未知 verify 类型：%s" % vtype


def cmd_add(args):
    data = load_ledger(args.file)
    entries = data["entries"]
    entry = {
        "id": next_id(entries),
        "kind": args.kind,
        "subject": args.subject,
        "value": args.value,
        "source": args.source or "",
        "status": args.status or "confirmed",
        "created_at": utc_now(),
        "verified_at": utc_now(),
    }
    if args.verify_file or args.verify_cmd:
        if args.verify_file:
            entry["verify"] = {
                "type": "file_contains" if args.verify_pattern else "file_exists",
                "path": args.verify_file,
            }
            if args.verify_pattern:
                entry["verify"]["pattern"] = args.verify_pattern
        else:
            entry["verify"] = {"type": "command", "cmd": args.verify_cmd}
    entries.append(entry)
    write_json_file(args.file, data)
    emit({"tool": "ledger.py", "action": "add", "entry": entry}, as_json=args.json,
         human_lines=["[ADD] #%d %s | %s = %s" % (
             entry["id"], entry["kind"], entry["subject"], entry["value"])])
    return EXIT_OK


def cmd_get(args):
    data = load_ledger(args.file)
    hits = [e for e in data["entries"]
            if (not args.subject or norm(args.subject) in norm(e.get("subject")))
            and (not args.kind or e.get("kind") == args.kind)]
    if not hits:
        err("账本里没有匹配条目（subject=%r kind=%r）" % (args.subject, args.kind))
        return EXIT_USAGE
    emit({"tool": "ledger.py", "action": "get", "count": len(hits), "entries": hits},
         as_json=args.json,
         human_lines=["#%d [%s/%s] %s = %s  (source=%s, status=%s)" % (
             e.get("id"), e.get("kind"), e.get("status"), e.get("subject"),
             e.get("value"), e.get("source") or "-", e.get("status"))
             for e in hits])
    return EXIT_OK


def cmd_list(args):
    data = load_ledger(args.file)
    hits = [e for e in data["entries"]
            if (not args.kind or e.get("kind") == args.kind)
            and (not args.status or e.get("status") == args.status)]
    emit({"tool": "ledger.py", "action": "list", "count": len(hits), "entries": hits},
         as_json=args.json,
         human_lines=(
             ["账本共 %d 条（%s）" % (len(data["entries"]), args.file)]
             + ["#%d [%s/%s] %s = %s" % (e.get("id"), e.get("kind"), e.get("status"),
                                         e.get("subject"), e.get("value")) for e in hits]
         ))
    return EXIT_OK


def cmd_remove(args):
    data = load_ledger(args.file)
    before = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if e.get("id") != args.id]
    if len(data["entries"]) == before:
        err("没有 id=%s 的条目" % args.id)
        return EXIT_USAGE
    write_json_file(args.file, data)
    emit({"tool": "ledger.py", "action": "remove", "id": args.id}, as_json=args.json,
         human_lines=["[REMOVE] #%d 已删除" % args.id])
    return EXIT_OK


def cmd_check(args):
    data = load_ledger(args.file)
    entries = data["entries"]
    results = []
    drifted = 0

    for e in entries:
        verify = e.get("verify")
        if not verify:
            results.append({"id": e.get("id"), "subject": e.get("subject"),
                            "status": "unverified", "detail": "无 verify 条件，跳过机器校验"})
            continue
        st, detail = run_verify(verify, args.root, timeout=args.timeout)
        if st == "fail":
            drifted += 1
            if args.fix:
                e["status"] = "stale"
                e["drift_detected_at"] = utc_now()
        elif st == "pass" and args.fix and e.get("status") == "stale":
            e["status"] = "confirmed"
            e["verified_at"] = utc_now()
        results.append({"id": e.get("id"), "subject": e.get("subject"),
                        "kind": e.get("kind"), "status": st, "detail": detail})

    if args.fix:
        write_json_file(args.file, data)

    stale_count = len([e for e in entries if e.get("status") == "stale"])
    payload = {
        "tool": "ledger.py",
        "action": "check",
        "root": args.root,
        "ledger": args.file,
        "results": results,
        "drift_count": drifted,
        "stale_entries": stale_count,
        "fixed": bool(args.fix),
        "hint": "drift/stale 条目不得作为 confirmed 引用；冲突时以磁盘真实现状为准并更新账本。",
    }

    lines = ["=== 账本校验 (root=%s) ===" % args.root]
    for r in results:
        mark = {"pass": "[PASS]", "fail": "[DRIFT]", "unverified": "[SKIP ]"}.get(r["status"], "[?]")
        lines.append("%s #%s %s :: %s" % (mark, r["id"], r["subject"], r["detail"]))
    lines.append("")
    lines.append("drift=%d stale=%d" % (drifted, stale_count))
    if drifted:
        lines.append(">>> 账本与现实不一致：以现实为准，更新账本后再引用。")
    emit(payload, as_json=args.json, human_lines=lines)

    if drifted:
        return EXIT_FAIL
    if stale_count and args.drift:
        return EXIT_FAIL
    return EXIT_OK


def build_parser():
    p = ArgParser(prog="ledger.py", description="项目账本：防记忆漂移")
    p.add_argument("--file", default=DEFAULT_FILE, help="账本文件路径（默认 .touchstone/ledger.json）")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="新增条目")
    a.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    a.add_argument("--subject", required=True)
    a.add_argument("--value", required=True)
    a.add_argument("--source", help="来源（文档路径#章节 / URL / 命令）")
    a.add_argument("--status", default="confirmed", choices=sorted(VALID_STATUS))
    a.add_argument("--verify-file", help="验证用文件路径")
    a.add_argument("--verify-pattern", help="该文件应包含的模式（正则）")
    a.add_argument("--verify-cmd", help="验证用命令（exit 0 视为满足）")
    a.set_defaults(func=cmd_add)

    g = sub.add_parser("get", help="按 subject 查询")
    g.add_argument("--subject")
    g.add_argument("--kind", choices=sorted(VALID_KINDS))
    g.set_defaults(func=cmd_get)

    ls = sub.add_parser("list", help="列出条目")
    ls.add_argument("--kind", choices=sorted(VALID_KINDS))
    ls.add_argument("--status", choices=sorted(VALID_STATUS))
    ls.set_defaults(func=cmd_list)

    rm = sub.add_parser("remove", help="删除条目")
    rm.add_argument("--id", type=int, required=True)
    rm.set_defaults(func=cmd_remove)

    ck = sub.add_parser("check", help="校验账本 vs 真实现状")
    ck.add_argument("--root", default=".", help="项目根目录（verify 中的相对路径基于此）")
    ck.add_argument("--drift", action="store_true", help="存在 stale 条目时也返回非零")
    ck.add_argument("--fix", action="store_true", help="把 drift 条目标为 stale 并写回")
    ck.add_argument("--timeout", type=float, default=10.0)
    ck.set_defaults(func=cmd_check)

    return p


def main(argv=None):
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
