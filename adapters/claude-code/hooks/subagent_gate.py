#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""subagent_gate.py —— Claude Code SubagentStop hook：子 agent 报告闸门

设计依据（本套件铁律之一）：**子 agent 的报告也是声明，默认按 hearsay 处理。**
子 agent 说"已完成/已验证/已修复"，如果没附可追溯证据，主 agent 不该直接采信。

这个 hook 做的事很窄：
  子 agent 报告里出现"完成类断言"，但没有"证据标记" → 阻断，要求补证据。

稳定性优先：
  - 拿不到报告文本 / 字段结构不认识 → 一律放行（绝不断案于猜测）
  - 只做"窄面判定"：断言词 + 证据标记，两者都是字符串匹配，可解释
  - 不调用网络、不执行子 agent 的命令，纯文本判定，毫秒级

退出码：0=放行 2=阻断（stderr 回喂给子 agent）
"""

import json
import os
import re
import sys

EXIT_OK = 0
EXIT_BLOCK = 2

# 完成类断言：出现这些词，说明子 agent 在声称"事情办成了"
CLAIM_WORDS = [
    "已完成", "已完成全部", "已创建", "已修复", "已验证", "已通过", "测试通过",
    "已写入", "已修改", "已删除", "已安装", "已提交", "已部署", "已发送",
    "all done", "completed", "finished", "tests pass", "tests passed",
    "verified", "fixed", "created successfully",
]

# 证据标记：出现任一，视为"有可追溯证据"
EVIDENCE_MARKS = [
    "exit=", "exit code", "返回码", "$ ", "```", "http://", "https://",
    "BUILD SUCCESSFUL", "passed", "failed", "ok)", "Tests:", "tests,",
    "commit", "hash", "diff --git", "traceback", "Traceback",
    "ls -la", "git status", "curl", "npm test", "pytest", "gradlew",
]


def _utf8():
    for s in (sys.stdin, sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def extract_text(event):
    """从不同字段名里尽力取出报告文本；取不到返回空串（调用方按放行处理）。"""
    for key in ("tool_response", "result", "output", "message", "content",
                "text", "response", "transcript"):
        v = event.get(key)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            for k2 in ("content", "text", "output"):
                v2 = v.get(k2)
                if isinstance(v2, str) and v2.strip():
                    return v2
    # 兜底：把整个事件序列化后取（避免漏掉嵌套结构里的文本）
    try:
        return json.dumps(event, ensure_ascii=False)
    except Exception:
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
        return EXIT_OK  # 解析失败一律放行

    text = extract_text(event)
    if not text:
        return EXIT_OK

    claims = [w for w in CLAIM_WORDS if w.lower() in text.lower()]
    if not claims:
        return EXIT_OK  # 没在完成类断言，不管

    has_evidence = any(m.lower() in text.lower() for m in EVIDENCE_MARKS)
    if has_evidence:
        return EXIT_OK

    sys.stderr.write(
        "[touchstone] 子 agent 报告含完成类断言（%s），但没有可追溯证据。\n"
        "请在报告里补充：实际执行的命令 + 输出原文 / 文件路径 / 工具返回值。\n"
        "查不到就说「未验证」—— 子 agent 的自述不是证据。\n"
        % "、".join(claims[:5])
    )
    return EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
