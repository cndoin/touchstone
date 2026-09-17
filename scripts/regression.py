#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""regression.py —— 幻觉案例回归集

为什么要有它：改 prompt / 改流程之后，按下葫芦浮起瓢是常态。
每个真实出错的案例都应该进回归集，改完之后跑一遍。

case 格式（assets/regression-cases.json）：
{
  "id": "case-001",
  "date": "2026-09-16",
  "source": "真实出错记录",
  "prompt": "用户当时的提问（脱敏）",
  "bad_output": "当时的错误输出",
  "error_type": "knowledge|tool|param|evidence|action",
  "why_wrong": "编造了什么",
  "expected_behavior": "正确行为",
  "output": "本次待检输出（可选；没有则 SKIP）",
  "output_file": "或指向输出文件（可选）",
  "check": {"type": "must_contain|must_not_contain|must_abstain|must_have_source",
            "value": "..."}
}

用法：
  python regression.py --cases assets/regression-cases.json
  python regression.py --cases cases.json --json --report report.json

退出码：0=无 FAIL 1=存在 FAIL 3=用法错误
注意：SKIP 不等于 PASS —— 无法自动判定的 case 必须人工过一遍。
"""

import argparse
import json
import os
import re
import sys

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
    write_json_file,
)

ABSTAIN_MARKERS = [
    "不知道", "不确定", "未找到", "没有找到", "资料里没提", "资料未提及",
    "需要核实", "需要查证", "无法确认", "unverified", "i don't know",
    "[]", "未验证", "没有可靠来源",
]

SOURCE_MARKERS = [
    "http://", "https://", "§", "source:", "来源", "根据", "见 ", "arxiv", "doi",
]


def load_output(case):
    """取待检输出：优先 output 字段，其次 output_file。都没有则返回 None → SKIP。"""
    if case.get("output"):
        return str(case["output"])
    path = case.get("output_file")
    if path:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as e:
            return None
    return None


def check_case(case):
    cid = case.get("id", "<no-id>")
    chk = case.get("check") or {}
    ctype = chk.get("type")
    value = chk.get("value", "")

    output = load_output(case)
    if output is None:
        return {"id": cid, "result": "SKIP", "reason": "无待检输出（output / output_file）"}
    if not ctype:
        return {"id": cid, "result": "SKIP", "reason": "未定义 check.type"}

    text = output.lower() if isinstance(output, str) else ""
    v = str(value).lower()

    if ctype == "must_contain":
        ok = v in text
        return {"id": cid, "result": "PASS" if ok else "FAIL",
                "reason": "必须包含 %r" % value}
    if ctype == "must_not_contain":
        ok = v not in text
        return {"id": cid, "result": "PASS" if ok else "FAIL",
                "reason": "不得包含 %r（这是当初编造的内容）" % value}
    if ctype == "must_abstain":
        ok = any(m.lower() in text for m in ABSTAIN_MARKERS)
        return {"id": cid, "result": "PASS" if ok else "FAIL",
                "reason": "应当明确表示不确定/未找到，而不是硬猜"}
    if ctype == "must_have_source":
        ok = any(m.lower() in text for m in SOURCE_MARKERS)
        return {"id": cid, "result": "PASS" if ok else "FAIL",
                "reason": "必须带来源标记（URL / 文件路径 / 章节）"}
    return {"id": cid, "result": "SKIP", "reason": "未知 check.type：%s" % ctype}


def main(argv=None):
    _force_utf8()

    p = ArgParser(prog="regression.py", description="幻觉案例回归集")
    p.add_argument("--cases", required=True, help="cases JSON 文件")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--report", help="报告写入该 JSON 文件")
    a = p.parse_args(argv)

    # 回归集支持两种形态：顶层数组，或 {"cases": [...]} 对象。
    # 这里不能用「必须是对象」的严格读法 —— 数组是合法输入。
    data = load_json_file(a.cases, "回归集")
    if isinstance(data, dict):
        cases = data.get("cases") or []
    elif isinstance(data, list):
        cases = data
    else:
        err("回归集格式不对：应为数组或含 cases 的对象")
        return EXIT_USAGE

    if not cases:
        err("回归集为空：%s（每个真实出错案例都应加一条）" % a.cases)
        return EXIT_USAGE

    results = [check_case(c) for c in cases]
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    by_type = {}
    for c, r in zip(cases, results):
        counts[r["result"]] = counts.get(r["result"], 0) + 1
        t = c.get("error_type", "unspecified")
        bucket = by_type.setdefault(t, {"total": 0, "pass": 0, "fail": 0, "skip": 0})
        bucket["total"] += 1
        bucket[r["result"].lower()] += 1

    payload = {
        "tool": "regression.py",
        "cases_file": a.cases,
        "total": len(cases),
        "counts": counts,
        "by_error_type": by_type,
        "results": results,
        "hint": "SKIP 不等于 PASS：无法自动判定的 case 需人工过一遍。",
    }

    if a.report:
        write_json_file(a.report, payload)

    if a.json:
        emit(payload, as_json=True)
    else:
        lines = ["=== 回归集：%s ===" % a.cases]
        for c, r in zip(cases, results):
            lines.append("[%s] %s :: %s" % (r["result"], r["id"], r["reason"]))
            if r["result"] == "FAIL":
                lines.append("       错误类型=%s | 应为：%s" % (
                    c.get("error_type", "-"), c.get("expected_behavior", "-")))
        lines.append("")
        lines.append("合计 %d：PASS=%d FAIL=%d SKIP=%d" % (
            len(cases), counts["PASS"], counts["FAIL"], counts["SKIP"]))
        for t, b in sorted(by_type.items()):
            lines.append("  %s: %d/%d 通过" % (t, b["pass"], b["total"]))
        if counts["SKIP"]:
            lines.append(">>> 有 SKIP：这些 case 无法自动判定，需人工确认。")
        if counts["FAIL"]:
            lines.append(">>> 有 FAIL：改流程后回归失败，先修再发布。")
        emit(None, as_json=False, human_lines=lines)

    return EXIT_FAIL if counts["FAIL"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
