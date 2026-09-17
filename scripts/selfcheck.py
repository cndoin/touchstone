#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""selfcheck.py —— 采样一致性统计（无原文、不可检索时的兜底手段）

原理：同一问题多次采样，按语义聚类后看是否收敛。
  - 语义熵（Nature 2024, Farquhar et al.）：在语义层面而非 token 层面算熵
  - SelfCheckGPT（arXiv 2303.08896）：一致性低 = 疑似幻觉

重要边界：本脚本做的是**字面近似聚类**（归一化 + 相似度），
不是真正的语义聚类（那需要 embedding 或 NLI 模型）。
结论落在灰区且代价高时，请人工过一眼。

更重要的边界：一致性高 != 正确。模型可以稳定地重复同一个错误。
一致性低是危险信号，一致性高只是及格线。

用法：
  python selfcheck.py --samples samples.json
  echo '{"question":"...","samples":["A","B"]}' | python selfcheck.py --stdin
  python selfcheck.py --samples samples.json --json

samples.json:
  {"question": "...", "samples": ["答案1", "答案2", "答案3"]}

退出码：0=高一致(>=0.8) 2=灰区(0.6~0.8) 4=低一致(<0.6) 3=用法/输入错误
（低一致用 4 而不是 3，是为了让 3 统一表示"用法/输入错误"，与其他脚本的退出码语义一致）
"""

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    ArgParser,  # noqa: E402
    EXIT_OK,
    _force_utf8,
    emit,
    err,
    load_json_file,
    load_json_object,
)

EXIT_GRAY = 2
EXIT_LOW = 4
EXIT_ERROR = 3  # 用法/输入错误，与全局约定一致

HIGH_THRESHOLD = 0.8
GRAY_THRESHOLD = 0.6
SIMILARITY = 0.72


def normalize(text):
    """归一化：去空白、去标点、小写。用于近似语义聚类。"""
    s = str(text or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[，。、；：！？,.;:!?()（）\[\]【】\"'`「」]", "", s)
    return s


def similar(a, b, threshold):
    """判断两个归一化文本是否同义（近似）。

    三重判定，逐层放宽：
      1. 完全相同
      2. 子串包含（"hilt" in "使用hilt做依赖注入"）
      3. 字面相似度 >= threshold（difflib）
      4. token 集合 Jaccard >= 0.5（"dagger hilt" vs "hilt"）
    """
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    # 短答案（如数字、单词）放宽：允许子串包含，避免 "5" 与 "等于5" 被拆成两簇
    if short in long_ and (len(short) >= 2 or len(long_) <= 8):
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() >= threshold:
        return True
    ta, tb = set(re.split(r"[^0-9a-z\u4e00-\u9fff]+", a)) - {""}, \
             set(re.split(r"[^0-9a-z\u4e00-\u9fff]+", b)) - {""}
    if ta and tb:
        inter = len(ta & tb)
        union = len(ta | tb)
        if union and inter / float(union) >= 0.5:
            return True
    return False


def cluster(samples, threshold=SIMILARITY):
    """贪心聚类：与已有簇中任一成员相似即归入该簇。"""
    clusters = []
    for raw in samples:
        n = normalize(raw)
        placed = False
        for c in clusters:
            if any(similar(n, m, threshold) for m in c["norms"]):
                c["members"].append(raw)
                c["norms"].append(n)
                placed = True
                break
        if not placed:
            clusters.append({"norms": [n], "members": [raw]})
    for c in clusters:
        c["norm"] = c["norms"][0]
    return clusters


def analyze(payload, threshold=None):
    """threshold 为 None 时沿用命令行（或默认）设定的 SIMILARITY。"""
    thr = SIMILARITY if threshold is None else threshold
    question = payload.get("question", "")
    samples = payload.get("samples") or []
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples 必须是非空数组")

    clusters = cluster(samples, thr)
    clusters.sort(key=lambda c: len(c["members"]), reverse=True)
    top = clusters[0]
    consistency = len(top["members"]) / float(len(samples))

    if consistency >= HIGH_THRESHOLD:
        verdict, label, action = "high", "observed", (
            "可标 observed（单次观测）；若要 confirmed 仍需 >=2 个独立一手源 + 主动找过反证")
        code = EXIT_OK
    elif consistency >= GRAY_THRESHOLD:
        verdict, label, action = "gray_zone", "assumed", (
            "升级：定向检索 或 子 agent 隔离验证（禁止在同一上下文里复查）")
        code = EXIT_GRAY
    else:
        verdict, label, action = "low", "assumed", (
            "危险信号：降级为 assumed，必须附反例解释；L2 场景交给人")
        code = EXIT_LOW

    return {
        "tool": "selfcheck.py",
        "question": question,
        "n": len(samples),
        "clusters": len(clusters),
        "consistency": round(consistency, 3),
        "dominant": top["members"][0],
        "cluster_sizes": [len(c["members"]) for c in clusters],
        "all_variants": [c["members"][0] for c in clusters],
        "verdict": verdict,
        "recommended_label": label,
        "action": action,
        "caveat": "字面近似聚类，非真语义聚类；一致性高不等于正确。",
    }, code


def main(argv=None):
    _force_utf8()

    p = ArgParser(prog="selfcheck.py", description="采样一致性统计")
    p.add_argument("--samples", help="samples JSON 文件路径")
    p.add_argument("--stdin", action="store_true", help="从 stdin 读 JSON")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--threshold", type=float, default=SIMILARITY,
                   help="聚类相似度阈值（默认 0.72）")
    a = p.parse_args(argv)

    try:
        if a.stdin:
            raw = sys.stdin.read()
            payload = json.loads(raw)
        elif a.samples:
            payload = load_json_object(a.samples, "samples")
        else:
            err("需要 --samples 或 --stdin")
            p.print_usage(sys.stderr)
            return EXIT_ERROR
    except Exception as e:
        err("读取输入失败：%s" % e)
        return EXIT_ERROR

    try:
        result, code = analyze(payload, threshold=a.threshold)
    except ValueError as e:
        err(str(e))
        return EXIT_ERROR

    if a.json:
        emit(result, as_json=True)
    else:
        lines = [
            "问题：%s" % result["question"],
            "样本 %d 条 → %d 个语义簇：%s" % (
                result["n"], result["clusters"], result["cluster_sizes"]),
            "一致度：%.2f（主簇：%s）" % (result["consistency"], result["dominant"]),
            "判读：%s → 建议标签 %s" % (result["verdict"], result["recommended_label"]),
            "动作：%s" % result["action"],
            "注意：%s" % result["caveat"],
        ]
        emit(None, as_json=False, human_lines=lines)
    return code


if __name__ == "__main__":
    sys.exit(main())
