#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""model_profile.py —— 模型能力分档与核查策略推荐

为什么需要它：**同一套核查策略不能套在所有模型上。**

核心差异不是"谁更聪明"，而是"谁能被信任做自我核查"：
  - S/A 档（强模型）：有足够元认知与指令遵循，可以用模型内验证
    （CoVe 隔离验证、自一致性、原生引用）
  - B/C 档（弱模型）：**自我核查不可靠** —— 它分不清自己错没错，
    甚至会把错误答案再确认一遍。必须全部走外部确定性脚本，
    并把单次输出缩短、把风险等级判定收紧

本脚本做的两件事：
  1. 根据模型名（启发式）判定能力档位 → 输出该档位的核查策略
  2. 把档位写入 .touchstone/model.json，供 pipeline / claim_lint 读取

重要边界：
  - 档位是**启发式默认值**，不是官方能力声明。型号迭代很快，
    请以官方 model card 为准；可用 --override-tier 手动指定
  - 联网能力属于**运行环境**而非模型本身，单独用 --net 声明
  - 未知模型一律按 **B 档**（保守默认），不会按 A 档放松

用法：
  python3 scripts/model_profile.py --list
  python3 scripts/model_profile.py --model claude-opus-4 --json
  python3 scripts/model_profile.py --model gpt-4o-mini --net on --json
  python3 scripts/model_profile.py --model deepseek-r1 --set      # 写入项目配置
  python3 scripts/model_profile.py --show                          # 读当前项目配置

退出码：0=成功 1=未找到/配置缺失 3=用法错误
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
from _common import (  # noqa: E402
    ArgParser, _force_utf8, atomic_write_json, emit, err,
    load_json_object,
)

EXIT_OK, EXIT_MISSING, EXIT_USAGE = 0, 1, 3

CONFIG_PATH = os.path.join(".touchstone", "model.json")

# ---------------------------------------------------------------------------
# 档位定义：trust_selfcheck 是分档的**核心变量**
# ---------------------------------------------------------------------------
TIERS = {
    "S": {
        "name": "S · 前沿强模型",
        "trust_selfcheck": True,
        "native_citations": True,
        "long_context": True,
        "instruction_following": "high",
        "max_claims_per_pass": 40,
        "strategy": "模型内验证可用：CoVe 隔离验证 + 自一致性；优先用原生引用能力",
        "notes": [
            "可用原生 Citations / 结构化输出做强制溯源",
            "自我核查可信，但仍需外部硬核查兜底（URL/文件/命令）",
        ],
    },
    "A": {
        "name": "A · 主力模型",
        "trust_selfcheck": True,
        "native_citations": None,  # 视平台而定
        "long_context": True,
        "instruction_following": "high",
        "max_claims_per_pass": 25,
        "strategy": "CoVe 隔离验证可用；低置信才上多模型交叉",
        "notes": [
            "自我核查基本可信，但复杂推理链仍需外部验证",
            # 推理型提示由 build_profile() 统一追加，此处不重复写
        ],
    },
    "B": {
        "name": "B · 轻量/中端模型",
        "trust_selfcheck": False,
        "native_citations": False,
        "long_context": None,
        "instruction_following": "medium",
        "max_claims_per_pass": 12,
        "strategy": "**不依赖自我核查**：全部走外部确定性脚本 + 强制引用 + 缩短单次输出",
        "notes": [
            "禁止把'再检查一遍'当验证 —— 它可能把错误答案再确认一遍",
            "单次产出声明数压到 12 条以内，分批核查",
            "无源即删执行得更严格：拿不出来源就直接删，不给'推断'留口子",
            "禁止 self-critique / '反思一下'：实证有害（arXiv 2601.00513，d=-0.14~-0.33）；"
            "替代为给证据(RAG, d=0.23~0.93) + 外部轻量验证器",
        ],
    },
    "C": {
        "name": "C · 小模型/边缘模型",
        "trust_selfcheck": False,
        "native_citations": False,
        "long_context": False,
        "instruction_following": "low",
        "max_claims_per_pass": 5,
        "strategy": "**只做可判定项核查**：存在性检查为主，禁止开放式事实结论",
        "notes": [
            "不适合做事实核查主体，只适合做格式化抽取与存在性判断",
            "任何事实性结论必须有外部证据，否则输出 unknown",
            "长文档场景禁用（上下文不足会静默丢信息）",
        ],
    },
}

# 启发式匹配：型号迭代快，这里只做保守默认，可用 --override-tier 覆盖
MODEL_RULES = [
    (r"claude-opus|claude-4-.*opus", "S"),
    (r"claude-sonnet|claude-3-7-sonnet|claude-4-.*sonnet", "A"),
    (r"claude-haiku", "B"),
    (r"gpt-5|o[1345](-.*)?$|gpt-5\.[0-9]", "A"),
    (r"gpt-4o(?!-mini)|gpt-4-turbo", "B"),
    (r"gpt-4o-mini|gpt-3\.5", "C"),
    (r"deepseek-r1|deepseek-reasoner", "A"),
    (r"deepseek-v3|deepseek-chat", "B"),
    (r"gemini-.*ultra|gemini-3-pro", "A"),
    (r"gemini-.*flash", "B"),
    (r"qwen-max|qwen-plus|qwen2\.5-72b|qwen3-.*235b", "B"),
    (r"qwen-turbo|qwen-small|qwen2-7b|qwen3-8b", "C"),
    (r"glm-4|glm-4\.5", "B"),
    (r"llama-3-70b|llama3\.1-70b|llama-4", "B"),
    (r"llama-3-8b|llama3-8b|mistral-7b|phi-3", "C"),
    (r"unknown|local|ollama|custom", "B"),
]

# ---------------------------------------------------------------------------
# 与模型能力无关的共同机制：谄媚诱导型幻觉 + 自一致性天花板
# ---------------------------------------------------------------------------
# 一手证据（见 references/17-vendor-and-induction.md）：
#   * Science 391(6792), DOI 10.1126/science.aec8352
#     11 模型比人类多肯定用户行为 49%；涉及欺骗/违法时仍背书 47%
#   * arXiv 2602.19141  即使理想贝叶斯用户也会中招；告知用户/禁止造假两种缓解均失效
#   * arXiv 2607.11414  8/8 采样全部一致的答案里仍有 15–23% 是错的
UNIVERSAL_CONTROLS = [
    "前提剥离：核查前必须把待验问题中性重述（剥掉'我觉得/肯定是/难道不是'），"
    "只把中性版本交给验证者 —— 用户的立场不得进入证据链",
    "同源即非独立：多次采样 / 多个 agent 说同一句话，先查是否共享同一来源或上下文；"
    "共享则只算 1 条证据",
    "自一致性天花板：8/8 一致仍有 15–23% 错误（arXiv 2607.11414，FinQA）；"
    "selfcheck.py 高一致只是及格线，不是确认依据",
    "禁止用'提醒自己别谄媚'对付谄媚：一手证据显示自我提醒与告知用户均无效，"
    "只有中性重述 + 上下文隔离这两步结构性动作有效",
]

# 官方机制备忘（v3.4 已回溯一手来源，见 references/17-vendor-and-induction.md）
VENDOR_MECHANISMS = {
    "anthropic": "一手：官方文档《Reduce hallucinations》(platform.claude.com/docs/en/test-and-evaluate/"
                 "strengthen-guardrails/reduce-hallucinations)。三条基础策略：① 明确给'说不知道'的权限 "
                 "② 长文档(>20k tokens)先逐字抽引文再作答 ③ 每条 claim 找支撑引文，找不到就撤回并留 []。"
                 "四条高级技巧：CoT verification / Best-of-N / iterative refinement / external knowledge "
                 "restriction。另有原生 Citations API（声明锚定到源文档 char/page 区间）。"
                 "官方原话：这些技术显著减少但不能完全消除幻觉",
    "openai": "一手：openai.com/index/why-language-models-hallucinate/ (2025-09-05, arXiv 2509.04664)。"
              "核心是评测激励：只看 accuracy 会奖励猜测、惩罚弃权。SimpleQA 对照 "
              "(gpt-5-thinking-mini 弃权 52%/错误 26% vs o4-mini 弃权 1%/错误 75%) 证明"
              "'更高准确率'与'更少幻觉'可以是相反方向",
    "google": "Grounding with Google Search + 结构化输出/函数声明",
    "deepseek": "推理型(R1/reasoner)长思维链不等于更可靠；思维链不是证据；"
                "中文语料强但中文二手来源密度高，更需回溯一手",
    "open-source-small": "一手实证 arXiv 2601.00513：7–9B 模型 50–69% 的正确答案推理链本身是错的；"
                         "self-critique 有害 (d=-0.14~-0.33)，RAG 有益 (d=0.23~0.93)。"
                         "→ 给它资料，别让它反思；用外部/蒸馏验证器",
}


def match_tier(model):
    """按模型名启发式判定档位。无匹配 → B（保守默认，绝不放松）。"""
    m = (model or "").strip().lower()
    if not m:
        return "B", "未提供模型名，按 B 档（保守默认）"
    for pattern, tier in MODEL_RULES:
        try:
            if re.search(pattern, m):
                return tier, "匹配规则 /%s/ → %s 档" % (pattern, tier)
        except re.error:
            continue
    return "B", "未匹配已知型号，按 B 档（保守默认）"


def is_reasoning_model(model):
    m = (model or "").lower()
    return bool(re.search(r"r1|reasoner|o[1345](-|$)|thinking|reasoning", m))


def build_profile(model, tier_override=None, net="unknown", override_reason=""):
    if tier_override:
        tier = tier_override.upper()
        reason = override_reason or "手动指定 --override-tier"
        if tier not in TIERS:
            return None, "未知档位：%s（可选 S/A/B/C）" % tier
    else:
        tier, reason = match_tier(model)
    spec = dict(TIERS[tier])

    reasoning = is_reasoning_model(model)
    profile = {
        "model": model or "(未指定)",
        "tier": tier,
        "tier_name": spec["name"],
        "match_reason": reason,
        "reasoning_model": reasoning,
        "net": net,
        "capabilities": {
            "trust_selfcheck": spec["trust_selfcheck"],
            "native_citations": spec["native_citations"],
            "long_context": spec["long_context"],
            "instruction_following": spec["instruction_following"],
        },
        "recommended": {
            "strategy": spec["strategy"],
            "max_claims_per_pass": spec["max_claims_per_pass"],
            "require_external_evidence": not spec["trust_selfcheck"],
            "use_model_selfcheck": spec["trust_selfcheck"],
            "retrieval": "required" if net == "off" else "required_for_zero_context",
            "risk_level_default": "L2" if tier in ("B", "C") and net == "off" else "L1",
        },
        "notes": list(spec["notes"]),
        # 与档位无关：谄媚与自一致性天花板对所有模型都成立
        "universal_controls": list(UNIVERSAL_CONTROLS),
    }

    # 按运行环境与推理型做增量调整
    if reasoning:
        profile["notes"].append(
            "推理型模型：思维链/推理内容**不作为证据**，仅用于生成验证问题；"
            "长推理会引入中间步骤编造")
    if net == "off":
        profile["notes"].append(
            "无联网环境：Zero Context 下无法核查外部事实 —— 只能标 unknown，禁止下事实结论")
        profile["recommended"]["require_external_evidence"] = True
    if net == "on":
        profile["notes"].append("有联网：优先用检索替代参数记忆（FACTS 数据显示检索切片显著强于闭卷）")
    if tier in ("B", "C"):
        profile["notes"].append(
            "弱模型档位：禁止在同一上下文里'再检查一遍'——那不是核查，是重复确认")

    profile["vendor_notes"] = VENDOR_MECHANISMS
    return profile, None


def main(argv=None):
    _force_utf8()
    p = ArgParser(prog="model_profile.py",
                  description="模型能力分档与核查策略推荐（适配不同强度的模型）")
    p.add_argument("--model", help="模型名（如 claude-opus-4、gpt-4o-mini、deepseek-r1）")
    p.add_argument("--override-tier", choices=["S", "A", "B", "C"], help="手动指定档位")
    p.add_argument("--net", choices=["on", "off", "unknown"], default="unknown",
                   help="运行环境是否可联网（联网能力属于环境，不属于模型）")
    p.add_argument("--list", action="store_true", help="列出档位定义与厂商官方机制")
    p.add_argument("--set", action="store_true", help="写入 .touchstone/model.json")
    p.add_argument("--show", action="store_true", help="显示当前项目已保存的档位")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    a = p.parse_args(argv)

    if a.list:
        payload = {
            "tool": "model_profile.py",
            "tiers": TIERS,
            "model_rules": [{"pattern": pat, "tier": t} for pat, t in MODEL_RULES],
            "vendor_mechanisms": VENDOR_MECHANISMS,
            "universal_controls": UNIVERSAL_CONTROLS,
            "caveat": "档位为启发式默认，型号迭代快，以官方 model card 为准；未知模型按 B 档（不放松）。",
        }
        if a.json:
            emit(payload, as_json=True)
        else:
            lines = ["=== 模型能力档位 ==="]
            for k in ("S", "A", "B", "C"):
                t = TIERS[k]
                lines.append("")
                lines.append("%s  自我核查可信=%s  单次声明上限=%d" % (
                    t["name"], t["trust_selfcheck"], t["max_claims_per_pass"]))
                lines.append("   策略：%s" % t["strategy"])
                for n in t["notes"]:
                    lines.append("   - %s" % n)
            lines.append("")
            lines.append("=== 厂商官方机制（备忘，v3.4 已回溯一手）===")
            for k, v in VENDOR_MECHANISMS.items():
                lines.append("  %-18s %s" % (k, v))
            lines.append("")
            lines.append("=== 全档位共同控制项（与模型强弱无关）===")
            for c in UNIVERSAL_CONTROLS:
                lines.append("  - %s" % c)
            lines.append("")
            lines.append(payload["caveat"])
            emit(None, as_json=False, human_lines=lines)
        return EXIT_OK

    if a.show:
        path = CONFIG_PATH
        if not os.path.exists(path):
            err("尚无项目配置：%s（先用 --model ... --set 写入）" % path)
            return EXIT_MISSING
        data = load_json_object(path, "model 配置")
        if a.json:
            emit(data, as_json=True)
        else:
            emit(None, as_json=False, human_lines=[
                "=== 当前项目模型档位（%s）===" % path,
                "模型：%s" % data.get("model"),
                "档位：%s（%s）" % (data.get("tier"), data.get("tier_name")),
                "判定依据：%s" % data.get("match_reason"),
                "策略：%s" % (data.get("recommended") or {}).get("strategy"),
            ])
        return EXIT_OK

    if not a.model and not a.override_tier:
        err("需要 --model（或 --override-tier），或用 --list / --show")
        return EXIT_USAGE

    profile, perr = build_profile(a.model, a.override_tier, a.net)
    if perr:
        err(perr)
        return EXIT_USAGE

    if a.set:
        atomic_write_json(CONFIG_PATH, profile)

    if a.json:
        emit(profile, as_json=True)
    else:
        rec = profile["recommended"]
        lines = [
            "=== 模型档位：%s ===" % profile["model"],
            "档位：%s" % profile["tier_name"],
            "判定：%s" % profile["match_reason"],
            "推理型：%s | 联网：%s" % (profile["reasoning_model"], profile["net"]),
            "",
            "推荐策略：%s" % rec["strategy"],
            "单次声明上限：%d" % rec["max_claims_per_pass"],
            "是否信任自我核查：%s" % rec["use_model_selfcheck"],
            "是否强制外部证据：%s" % rec["require_external_evidence"],
            "默认风险等级：%s" % rec["risk_level_default"],
            "",
            "注意：",
        ]
        lines += ["  - %s" % n for n in profile["notes"]]
        lines += ["", "全档位共同控制项（与模型强弱无关）："]
        lines += ["  - %s" % c for c in profile["universal_controls"]]
        emit(None, as_json=False, human_lines=lines)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
