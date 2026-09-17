#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""precompact_snapshot.py —— Claude Code PreCompact hook：压缩前状态快照

为什么需要：上下文压缩（/compact）会丢掉早期细节，这正是大项目"约定漂移"和
"状态幻觉"的温床 —— 压缩前记得的东西，压缩后变成"我记得好像是……"。

这个 hook 在压缩**之前**把关键状态写到磁盘，压缩后 Claude 可以读回来：
  - 账本条目（.touchstone/ledger.json）
  - 执行声明（execution_claims.json）
  - 当前 git 状态 / 最近提交
  - 未验证项清单
  - 恢复指令（压缩后该读哪些文件）

永不阻断（exit 0）。任何失败都静默跳过 —— 快照是保险，不是关键路径。
"""

import json
import os
import subprocess
import sys
import time

EXIT_OK = 0


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def git(cwd, args):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                           text=True, timeout=15, errors="replace")
        if r.returncode == 0:
            return (r.stdout or "").strip()
    except Exception:
        pass
    return ""


def main():
    _utf8()
    try:
        raw = sys.stdin.read()
        try:
            event = json.loads(raw) if raw.strip() else {}
        except Exception:
            event = {}
        if not isinstance(event, dict):
            # 顶层不是对象（数组/标量）时按空事件处理：hook 出错必须放行，
            # 绝不能因为拿不到字段就抛异常把正常流程卡死
            event = {}
    except Exception:
        event = {}

    cwd = event.get("cwd") or os.getcwd()
    dh = os.path.join(cwd, ".touchstone")
    snap_dir = os.path.join(dh, "snapshots")

    lines = ["# 上下文压缩前快照", ""]
    lines.append("生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("项目根目录：%s" % cwd)
    lines.append("")

    ledger = read_json(os.path.join(dh, "ledger.json"))
    if ledger:
        lines.append("## 项目账本（决策 / 约定 / 状态）")
        for e in (ledger.get("entries") or []):
            lines.append("- [%s/%s] %s = %s（来源：%s）" % (
                e.get("kind", "-"), e.get("status", "-"),
                e.get("subject", "-"), e.get("value", "-"),
                e.get("source", "-")))
        lines.append("")

    claims = read_json(os.path.join(dh, "execution_claims.json"))
    if claims:
        lines.append("## 执行声明")
        for c in (claims.get("execution_claims") or []):
            if isinstance(c, dict):
                lines.append("- %s | verified=%s | evidence=%s" % (
                    c.get("claim", "-"), c.get("verified"),
                    (c.get("evidence") or "(无)")[:120]))
        lines.append("")

    status = git(cwd, ["status", "--porcelain"])
    if status:
        lines.append("## git status（变更中）")
        lines.append("```")
        lines.append(status[:3000])
        lines.append("```")
        lines.append("")
    log = git(cwd, ["log", "--oneline", "-10"])
    if log:
        lines.append("## 最近提交")
        lines.append("```")
        lines.append(log)
        lines.append("```")
        lines.append("")

    lines.append("## 压缩后恢复清单（必读）")
    lines.append("1. 读 `.touchstone/ledger.json` —— 项目约定以此为准，与记忆冲突时以文件为准")
    lines.append("2. 读 `.touchstone/execution_claims.json` —— 别重复声称已完成的事")
    lines.append("3. 陈述代码库现状前，**实际读文件或跑命令**，不要凭压缩后的模糊记忆")
    lines.append("4. 拿不准的先说「未验证」，再查")

    try:
        os.makedirs(snap_dir, exist_ok=True)
        name = "compact-%s.md" % time.strftime("%Y%m%d-%H%M%S")
        p = os.path.join(snap_dir, name)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, p)
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreCompact",
                "additionalContext": "压缩前快照已写入 %s。压缩后请先读 .touchstone/ledger.json "
                                     "与 execution_claims.json，陈述现状前实际读文件/跑命令。" % p,
            }
        }, ensure_ascii=False))
        sys.stdout.write("\n")
    except Exception:
        pass  # 快照失败不影响压缩

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
