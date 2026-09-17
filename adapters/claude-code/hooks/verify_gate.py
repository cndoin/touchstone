#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""verify_gate.py —— Claude Code Stop hook：交付前闸门（v3）

治最高危的一类幻觉：声称做完了，其实没做。

v3 关键修复 —— 官方语义有两个坑，必须绕开：
  1. **Stop hook 连续阻断 8 次后，Claude Code 会覆盖 hook 强制结束回合。**
     所以不能一味 exit 2。策略：
       - 首次发现缺证据 → exit 2 强阻断（Claude 会回来补证据）
       - 已经处在阻断循环中（stop_hook_active=true）或计数接近上限
         → 改用 JSON `hookSpecificOutput.additionalContext` 反馈并 exit 0
           （Claude 继续回合，但不计入阻断次数，不撞 8 次上限）
       - 超过硬上限（默认 6 次）→ 写日志并放行，绝不把用户卡死
  2. PostToolUse 的 exit 2 不能撤销已执行的工具；能真正阻断的是
     PreToolUse / Stop / SubagentStop / UserPromptSubmit。本 hook 挂在 Stop 上，阻断有效。

输入：stdin JSON（含 cwd、session_id、stop_hook_active）
输出：stdout JSON（additionalContext）或 stderr 文本 + 退出码

退出码：0=放行 2=阻断（仅前几次使用）
"""

import json
import os
import re
import subprocess
import sys
import time

CLAIMS_FILE = os.path.join(".touchstone", "execution_claims.json")
COUNT_FILE = os.path.join(".touchstone", ".stop_block_count")
EXIT_OK = 0
EXIT_BLOCK = 2
MAX_BLOCKS = 6              # 硬上限，超过就放行（不把用户卡死）
COUNT_RESET_SECONDS = 600   # 10 分钟无阻断则计数归零


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def parse_ratio(v):
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def read_count(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - float(d.get("ts", 0)) > COUNT_RESET_SECONDS:
            return 0
        return int(d.get("n", 0))
    except Exception:
        return 0


def write_count(path, n):
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"n": n, "ts": time.time()}, f)
        os.replace(tmp, path)
    except Exception:
        pass


def emit_context(text):
    """用 additionalContext 反馈：Claude 会继续回合，但不计为 hook 阻断。"""
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": text}
    }, ensure_ascii=False))
    sys.stdout.write("\n")


def collect_problems(cwd, doc):
    problems = []
    for i, c in enumerate(doc.get("execution_claims") or []):
        if not isinstance(c, dict):
            problems.append("execution_claims[%d] 不是对象" % i)
            continue
        label = c.get("claim") or ("#%d" % i)
        if c.get("verified") is not True:
            problems.append("「%s」：verified != true —— 没验证就不能说完成" % label)
            continue
        if not (c.get("evidence") or "").strip():
            problems.append("「%s」：verified=true 但没有 evidence（工具输出原文）" % label)
        p = c.get("path")
        if p:
            full = p if os.path.isabs(p) else os.path.join(cwd, p)
            if not os.path.exists(full):
                problems.append("「%s」：路径不存在 %s" % (label, full))
        cmd = c.get("command")
        if cmd:
            try:
                r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                                   text=True, timeout=60, errors="replace")
                if r.returncode != 0:
                    problems.append("「%s」：命令 exit=%d（%s）" % (
                        label, r.returncode, (r.stdout or r.stderr or "")[:200]))
            except Exception as e:
                problems.append("「%s」：命令执行失败 %s（记为未验证）" % (label, e))

    for key, val in (doc.get("hard_checks") or {}).items():
        if key in ("summary", "removed", "notes"):
            continue
        ratio = parse_ratio(val)
        if ratio and ratio[0] < ratio[1]:
            problems.append("硬核查未全过：%s = %s（相关声明必须删除或降级）" % (key, val))
    return problems


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
    in_loop = bool(event.get("stop_hook_active"))
    path = os.path.join(cwd, CLAIMS_FILE)

    if not os.path.exists(path):
        return EXIT_OK  # 没有执行声明 → 不阻断（很多任务本就没有）

    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        sys.stderr.write("[touchstone] %s 解析失败：%s（放行）\n" % (CLAIMS_FILE, e))
        return EXIT_OK

    problems = collect_problems(cwd, doc)
    count_path = os.path.join(cwd, COUNT_FILE)

    if not problems:
        write_count(count_path, 0)
        return EXIT_OK

    n = read_count(count_path)
    body = "闸门未放行，共 %d 项未验证：\n" % len(problems)
    for p in problems:
        body += "  - %s\n" % p
    body += "请补齐证据（工具实际输出）后重试；查不到就明确说「未验证」，不要声称完成。"

    if n >= MAX_BLOCKS:
        sys.stderr.write(
            "[touchstone] 已达阻断上限（%d 次），本次放行；未验证项已记录，请人工确认。\n"
            % MAX_BLOCKS)
        write_count(count_path, 0)
        return EXIT_OK

    write_count(count_path, n + 1)

    # 已在阻断循环中 或 接近上限 → 温和反馈（不计阻断次数，避免撞 8 次上限）
    if in_loop or n >= MAX_BLOCKS - 1:
        emit_context(body)
        return EXIT_OK

    sys.stderr.write("[touchstone] %s\n" % body)
    return EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
