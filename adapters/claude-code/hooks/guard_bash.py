#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""guard_bash.py —— Claude Code PreToolUse(Bash) hook：高危命令拦截

治的是"行动幻觉"：未经确认就执行不可逆操作（删库、强推、格式化、外发）。

Claude Code hook 约定（以官方文档为准）：
  - stdin 收到 JSON 事件，tool_input.command 是待执行命令
  - 退出码 0 = 放行；退出码 2 = 阻断并把 stderr 回喂给模型

稳定性原则（重要）：
  - stdin 解析失败 / 拿不到 command → **放行**（绝不能因为脚本 bug 卡住正常工作）
  - 只有明确命中高危模式才阻断
  - ALLOW 环境变量可临时放行：TOUCHSTONE_ALLOW_DANGEROUS=1
"""

import json
import os
import re
import sys

EXIT_OK = 0
EXIT_BLOCK = 2

# (正则, 说明)：命中即阻断，要求人工确认
DANGEROUS = [
    (r"\brm\s+-rf\s+(/|~|\*|$)", "递归删除根目录/家目录/当前目录"),
    (r"\brm\s+-rf\s+[^\s]*\s*;/", "删除后接绝对路径，风险极高"),
    (r"\brm\s+-fr\b", "rm -fr 递归强制删除"),
    (r"\bmkfs(\.[a-z0-9]+)?\b", "格式化文件系统"),
    (r"\bdd\s+if=", "dd 直接写设备"),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;", "fork 炸弹"),
    (r"\bgit\s+push\s+(-f|--force|--force-with-lease)\b", "强制推送（覆盖远端历史）"),
    (r"\bgit\s+reset\s+--hard\b", "硬重置（丢弃本地改动）"),
    (r"\bgit\s+clean\s+-fd", "强制清理未跟踪文件"),
    (r"\bchmod\s+-R\s+777\b", "全开权限"),
    (r"\bcurl\b[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b", "下载即执行"),
    (r"\bwget\b[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b", "下载即执行"),
    (r"\bDROP\s+(DATABASE|TABLE)\b", "删库删表"),
    (r"\bTRUNCATE\s+TABLE\b", "清空表"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "无 WHERE 的 DELETE"),
    (r"\b(shutdown|reboot|init\s+0)\b", "关机/重启"),
    (r">\s*/dev/sd[a-z]", "直接写磁盘设备"),
    (r"\bnpm\s+publish\b|\btwine\s+upload\b|\bgit\s+tag\s+-f\b", "对外发布动作"),
]


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main():
    _utf8()

    # v4 起环境变量统一为 TOUCHSTONE_*；DEHALLU_* 是改名前的旧名，继续兼容
    # （老用户的 settings.json 里可能还写着旧名，不能因为改个项目名就失效）
    if (os.environ.get("TOUCHSTONE_ALLOW_DANGEROUS") == "1"
            or os.environ.get("DEHALLU_ALLOW_DANGEROUS") == "1"):
        return EXIT_OK

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
        return EXIT_OK  # 解析失败一律放行，不阻断正常工作

    tool_input = event.get("tool_input") or {}
    cmd = tool_input.get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        return EXIT_OK

    hits = []
    for pattern, why in DANGEROUS:
        try:
            if re.search(pattern, cmd, re.IGNORECASE):
                hits.append((pattern, why))
        except re.error:
            continue

    if not hits:
        return EXIT_OK

    sys.stderr.write(
        "[touchstone] 拦截高危命令（行动幻觉防护）：\n")
    sys.stderr.write("  命令：%s\n" % cmd.strip()[:300])
    for _, why in hits:
        sys.stderr.write("  命中：%s\n" % why)
    sys.stderr.write(
        "这是不可逆操作。请先向用户确认（说明影响范围与回滚方式），"
        "确认后再执行；确需放行请设置 TOUCHSTONE_ALLOW_DANGEROUS=1。\n")
    return EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
