#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""verifiers.py —— 可插拔检测器桥接（OpenFactCheck 三插槽的落地）

设计来自 OpenFactCheck 的可插拔架构：claim processor / evidence retriever / verifier
应当可以自由替换，才能适配"离线 / 在线 / 有库 / 没库"各种环境。

本套件**默认零依赖**，内置 verifier 是确定性的脚本（hardcheck / dep_guard / claim_lint）。
但当本地装有更强的检测器时，可以在**灰区**升级使用它们 —— 这就是这个脚本的作用。

重要边界：
  - 只做**探测**（importlib.util.find_spec），绝不 import 它们
    （避免副作用、避免拖慢、避免在缺失时崩溃）
  - 不自动调用任何外部检测器：调用行为差异太大，且可能烧 token。
    它只回答"哪些可用"，由人或上层流程决定是否升级
  - 缺失不是错误：默认路径永远可用

用法：
  python3 scripts/verifiers.py --list
  python3 scripts/verifiers.py --list --json
  python3 scripts/verifiers.py --require ragas        # 缺失则退出 1（CI 门禁用）

退出码：0=满足 1=要求未满足 3=用法错误
"""

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
from _common import ArgParser, _force_utf8, emit, err  # noqa: E402

EXIT_OK, EXIT_MISSING, EXIT_USAGE = 0, 1, 3

# (检测名, 导入名, 用途, 适用插槽)
CATALOG = [
    ("deepeval", "deepeval", "LLM-as-judge 评测：HallucinationMetric / FaithfulnessMetric", "verifier"),
    ("ragas", "ragas", "RAG 忠实度：把答案拆 claim 对照检索上下文", "verifier"),
    ("cleanlab", "cleanlab", "不确定性打分 + 反例解释（TLM 需 API key）", "verifier"),
    ("trulens", "trulens", "RAG 三元组归因：分清检索错还是生成错", "verifier"),
    ("sentence-transformers", "sentence_transformers", "语义聚类所需的 embedding（真语义熵）", "evidence_retriever"),
    ("transformers", "transformers", "NLI 蕴含模型（DeBERTa-NLI / HHEM 类）", "verifier"),
    ("nltk", "nltk", "文本处理（部分检测器依赖）", "claim_processor"),
    ("spacy", "spacy", "实体与句法（声明抽取）", "claim_processor"),
]


def probe(import_name):
    """探测模块是否可导入。任何异常都视为不可用（不崩）。"""
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError, AttributeError):
        return False
    except Exception:  # noqa: BLE001
        return False


def scan():
    items = []
    for name, import_name, purpose, slot in CATALOG:
        items.append({
            "name": name,
            "import": import_name,
            "available": probe(import_name),
            "slot": slot,
            "purpose": purpose,
        })
    return items


def main(argv=None):
    _force_utf8()
    p = ArgParser(prog="verifiers.py", description="可插拔检测器桥接（探测本机可用的外部检测器）")
    p.add_argument("--list", action="store_true", help="列出外部检测器可用情况")
    p.add_argument("--require", help="要求某个检测器可用（缺失则退出码 1）")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    a = p.parse_args(argv)

    if not a.list and not a.require:
        p.print_usage(sys.stderr)
        err("需要 --list 或 --require <name>")
        return EXIT_USAGE

    items = scan()
    by_name = {i["name"]: i for i in items}
    available = [i["name"] for i in items if i["available"]]
    missing = [i["name"] for i in items if not i["available"]]

    payload = {
        "tool": "verifiers.py",
        "note": "本套件默认零依赖；这些是可选升级项，仅在置信度灰区时使用。",
        "available": available,
        "missing": missing,
        "items": items,
        "builtin_verifiers": ["hardcheck.py", "dep_guard.py", "claim_lint.py", "selfcheck.py"],
        "hint": "缺失不是错误 —— 内置确定性脚本永远可用。",
    }

    if a.json:
        emit(payload, as_json=True)
    else:
        lines = ["=== 外部检测器探测 ==="]
        for i in items:
            mark = "[可用]  " if i["available"] else "[缺失]  "
            lines.append("%s%-20s %-18s %s" % (mark, i["name"], i["slot"], i["purpose"]))
        lines.append("")
        lines.append("可用 %d / 共 %d" % (len(available), len(items)))
        lines.append("内置（始终可用）：%s" % ", ".join(payload["builtin_verifiers"]))
        lines.append("提示：缺失不是错误 —— 本套件默认零依赖，内置脚本永远可跑。")
        emit(None, as_json=False, human_lines=lines)

    if a.require:
        target = a.require
        if target not in by_name:
            err("未知检测器：%s（可选：%s）" % (target, ", ".join(sorted(by_name))))
            return EXIT_USAGE
        if not by_name[target]["available"]:
            err("要求 %s 可用，但未安装 —— 请 pip install %s 后重试" % (target, target))
            return EXIT_MISSING
        return EXIT_OK

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
