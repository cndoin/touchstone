#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""claim_lint.py —— 输出契约闸门（交付前最后一道）

它校验的不是 JSON 格式，是**逻辑一致性**：
  - confirmed 是否真有 >=2 个独立源？是否主动找过反证？
  - observed 是否带了观测时间？
  - 低置信是否附了反例解释？
  - 是否存在无源却以事实口吻呈现的声明？
  - L2 风险是否走了人工闸门？
  - 声称"已完成"的每条是否都有证据？

用法：
  python claim_lint.py --input claims.json
  python claim_lint.py --input claims.json --min-level L2 --json
  python claim_lint.py --input claims.json --report report.json

退出码：0=通过 1=闸门不放行 3=用法/输入错误
"""

import argparse
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
    load_json_object,
    write_json_file,
)

VALID_LABELS = {"confirmed", "observed", "assumed", "hearsay", "unknown"}
VALID_CONTEXT = {"accurate_context", "noisy_context", "zero_context", "accurate", "noisy", "zero"}
VALID_RISK = {"L0", "L1", "L2"}
LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2}

# 分级：哪些检查在哪个 min-level 下启用
RULES = {
    "structure": "L0",
    "label_valid": "L0",
    "unknown_not_filled": "L0",
    "observed_has_time": "L1",
    "confirmed_two_sources": "L1",
    "confirmed_counter_evidence": "L1",
    "hearsay_has_source": "L1",
    "low_confidence_alternative": "L1",
    "hard_checks_clean": "L1",
    "execution_claims_verified": "L1",
    "risk_l2_human_review": "L2",
    "zero_context_must_retrieve": "L2",
}


class Issue(object):
    def __init__(self, rule, level, severity, message, path=""):
        self.rule = rule
        self.level = level
        self.severity = severity  # error | warn
        self.message = message
        self.path = path

    def as_dict(self):
        return {
            "rule": self.rule,
            "level": self.level,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }

    def __str__(self):
        mark = "[ERROR]" if self.severity == "error" else "[WARN ]"
        loc = (" " + self.path) if self.path else ""
        return "%s%s %s :: %s" % (mark, loc, self.rule, self.message)


def rule_enabled(rule, min_level):
    need = RULES.get(rule, "L0")
    return LEVEL_ORDER[min_level] >= LEVEL_ORDER[need]


def add(issues, rule, min_level, severity, message, path=""):
    if rule_enabled(rule, min_level):
        issues.append(Issue(rule, RULES.get(rule, "L0"), severity, message, path))


def parse_ratio(value):
    """解析 '3/3' 这类比例字符串，返回 (分子, 分母)。解析不出返回 None。"""
    if not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def independent_sources(sources):
    """判定独立源数量：按 ref 去重（同一 ref 的多个引用仍算 1 个）。

    注意：脚本只能做"字面去重"，无法判断两个源之间是否存在转述关系
    （博客引博客 = 1 个源）。这类语义独立性需要人工判断，故此处仅做下限拦截。
    """
    refs = set()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        ref = s.get("ref") or s.get("url") or s.get("quote") or s.get("type")
        if ref:
            refs.add(str(ref).strip().lower())
    return len(refs)


def lint_claim(claim, idx, min_level, issues):
    path = "claims[%d]" % idx

    text = claim.get("text")
    if not text or not str(text).strip():
        add(issues, "structure", min_level, "error", "声明文本为空", path)
        return

    label = claim.get("label")
    if label not in VALID_LABELS:
        add(issues, "label_valid", min_level, "error",
            "label 非法或缺失：%r（应为 %s）" % (label, "/".join(sorted(VALID_LABELS))), path)
        return

    sources = claim.get("sources") or []
    n_src = independent_sources(sources)

    if label == "confirmed":
        if n_src < 2:
            add(issues, "confirmed_two_sources", min_level, "error",
                "confirmed 需要 >=2 个独立一手源，当前独立源数=%d（注意：博客引博客只算 1 个）" % n_src,
                path)
        if not claim.get("counter_evidence_checked"):
            add(issues, "confirmed_counter_evidence", min_level, "error",
                "confirmed 必须主动找过反证（counter_evidence_checked=true）", path)

    if label == "observed":
        if not (claim.get("verified_at") or claim.get("observed_at")):
            add(issues, "observed_has_time", min_level, "error",
                "observed 必须带观测时间（verified_at）", path)

    if label == "hearsay" and n_src == 0:
        add(issues, "hearsay_has_source", min_level, "error",
            "hearsay 必须点名来源（sources 不可为空）", path)

    if label == "unknown":
        # unknown 不允许被"填空"：若有 sources 却标 unknown，多半是标签贴错
        if n_src > 0:
            add(issues, "unknown_not_filled", min_level, "warn",
                "标为 unknown 却带来源：要么升级标签，要么说明为何仍不可信", path)

    conf = claim.get("confidence")
    if conf is not None:
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            add(issues, "structure", min_level, "error", "confidence 不是数字：%r" % conf, path)
            conf = None
        if conf is not None and not (0.0 <= conf <= 1.0):
            add(issues, "structure", min_level, "error",
                "confidence 超出 [0,1]：%s" % conf, path)
        if conf is not None and conf < 0.6 and label in ("confirmed", "observed"):
            add(issues, "low_confidence_alternative", min_level, "error",
                "置信度 %.2f < 0.6 却标为 %s：自相矛盾，应降级或补充核查" % (conf, label), path)
        if conf is not None and conf < 0.6 and not claim.get("alternative"):
            add(issues, "low_confidence_alternative", min_level, "error",
                "置信度 %.2f < 0.6 必须附反例解释（alternative）" % conf, path)


def lint_document(doc, min_level):
    issues = []

    if not isinstance(doc, dict):
        add(issues, "structure", min_level, "error", "顶层必须是 JSON 对象")
        return issues, {}

    ctx = doc.get("context_setting")
    if ctx and ctx not in VALID_CONTEXT:
        add(issues, "structure", min_level, "warn",
            "context_setting 取值非常规：%r" % ctx)

    risk = doc.get("risk_level", "L1")
    if risk not in VALID_RISK:
        add(issues, "structure", min_level, "error", "risk_level 非法：%r" % risk)
        risk = "L1"

    claims = doc.get("claims")
    if claims is None:
        claims = []
        add(issues, "structure", min_level, "warn", "没有 claims 字段（最低要求应列出声明）")
    if not isinstance(claims, list):
        add(issues, "structure", min_level, "error", "claims 必须是数组")
        claims = []

    for i, c in enumerate(claims):
        if isinstance(c, dict):
            lint_claim(c, i, min_level, issues)
        else:
            add(issues, "structure", min_level, "error",
                "声明必须是对象：%r" % (c,), "claims[%d]" % i)

    # 硬核查结果
    hc = doc.get("hard_checks") or {}
    if isinstance(hc, dict):
        for key, val in hc.items():
            if key in ("summary", "removed", "notes"):
                continue
            ratio = parse_ratio(val)
            if ratio is None:
                continue
            got, total = ratio
            if got < total:
                add(issues, "hard_checks_clean", min_level, "error",
                    "硬核查未全过：%s = %s（未通过项对应的声明必须删除或降级）" % (key, val),
                    "hard_checks")

    # 执行声明
    execs = doc.get("execution_claims") or []
    for i, e in enumerate(execs):
        if not isinstance(e, dict):
            add(issues, "execution_claims_verified", min_level, "error",
                "执行声明必须是对象：%r" % (e,), "execution_claims[%d]" % i)
            continue
        if e.get("verified") is not True:
            add(issues, "execution_claims_verified", min_level, "error",
                "声称完成但 verified != true：%r" % e.get("claim"), "execution_claims[%d]" % i)
        elif not (e.get("evidence") or "").strip():
            add(issues, "execution_claims_verified", min_level, "error",
                "verified=true 但没有 evidence（工具输出/命令回执），自报状态不是证据",
                "execution_claims[%d]" % i)

    # 风险路由
    if risk == "L2":
        if doc.get("needs_human_review") is not True:
            add(issues, "risk_l2_human_review", min_level, "error",
                "risk_level=L2 必须走人工闸门（needs_human_review=true）")
        if not doc.get("retrieval_performed") and not doc.get("sources_consulted"):
            add(issues, "zero_context_must_retrieve", min_level, "warn",
                "L2 场景建议强制外部检索；若确未检索请显式说明（retrieval_performed=false）")

    if ctx in ("zero_context", "zero") and not doc.get("retrieval_performed"):
        add(issues, "zero_context_must_retrieve", min_level, "warn",
            "Zero Context 必须外部检索；未检索的结论不能作为事实输出")

    stats = {
        "claims": len(claims),
        "by_label": {},
        "with_sources": 0,
        "execution_claims": len(execs),
    }
    for c in claims:
        if isinstance(c, dict):
            lab = c.get("label", "?")
            stats["by_label"][lab] = stats["by_label"].get(lab, 0) + 1
            if independent_sources(c.get("sources")) > 0:
                stats["with_sources"] += 1

    return issues, stats


def main(argv=None):
    _force_utf8()

    p = ArgParser(prog="claim_lint.py", description="输出契约闸门：交付前最后一道")
    p.add_argument("--input", required=True, help="claims JSON 文件路径")
    p.add_argument("--min-level", default="L1", choices=["L0", "L1", "L2"],
                   help="最低检查等级（默认 L1；L2 会追加人工闸门等强约束）")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--report", help="把报告写入该 JSON 文件")
    p.add_argument("--strict-warn", action="store_true",
                   help="把 WARN 也当作失败（默认只有 ERROR 拦截）")
    a = p.parse_args(argv)

    doc = load_json_object(a.input, "claims")
    issues, stats = lint_document(doc, a.min_level)

    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warn"]
    blocked = len(errors) > 0 or (a.strict_warn and len(warns) > 0)

    payload = {
        "tool": "claim_lint.py",
        "input": a.input,
        "min_level": a.min_level,
        "stats": stats,
        "errors": [i.as_dict() for i in errors],
        "warnings": [i.as_dict() for i in warns],
        "gate": "BLOCKED" if blocked else "PASSED",
        "hint": "闸门 BLOCKED = 不许交付；先修 ERROR 再重跑。",
    }

    if a.report:
        write_json_file(a.report, payload)

    if a.json:
        emit(payload, as_json=True)
    else:
        lines = ["=== claim_lint 报告 (%s) ===" % a.input]
        lines.append("声明数 %d | 有源声明 %d | 执行声明 %d" % (
            stats["claims"], stats["with_sources"], stats["execution_claims"]))
        if stats["by_label"]:
            lines.append("标签分布：" + ", ".join(
                "%s=%d" % (k, v) for k, v in sorted(stats["by_label"].items())))
        lines.append("")
        if errors:
            lines.append("--- ERROR (%d) ---" % len(errors))
            lines.extend(str(i) for i in errors)
        if warns:
            lines.append("--- WARN (%d) ---" % len(warns))
            lines.extend(str(i) for i in warns)
        if not errors and not warns:
            lines.append("无问题。")
        lines.append("")
        lines.append("闸门：%s" % payload["gate"])
        if blocked:
            lines.append(">>> 不放行。修完 ERROR 再交付。")
        emit(None, as_json=False, human_lines=lines)

    return EXIT_FAIL if blocked else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
