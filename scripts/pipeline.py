#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""pipeline.py —— 一键跑完整条核查链

把散落的脚本串成一条流水线，避免"记得跑这个忘了跑那个"：

  [1] hardcheck  可判定项硬核查（URL/DOI/文件/命令/包版本）
  [2] dep_guard  依赖与符号幻觉防护（幻影 import / 包幻觉 / slopsquatting）
  [3] claim_lint 输出契约闸门
  [4] 汇总       → 一份报告 + 一个退出码

设计原则：
  - 每一步独立失败不影响其它步骤执行完（但最终退出码取最严重者）
  - 任何一步的脚本缺失/崩溃 → 记为该步 unverified，不静默跳过
  - 全程可 --offline

用法：
  python pipeline.py --root . --checks .touchstone/checks.json \\
                     --claims .touchstone/claims.json --level L1
  python pipeline.py --root . --offline --no-deps --json --report report.json

退出码：0=全通过 1=存在失败（不许交付） 2=存在未验证 3=用法错误
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
from _common import ArgParser, _force_utf8, emit, err  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_UNVERIFIED, EXIT_USAGE = 0, 1, 2, 3
SEVERITY = {0: 0, 2: 1, 1: 2, 3: 3}  # 数字越大越严重，用于取最严重结果


def run_step(args, stdin_data=None, cwd=None):
    """执行一个子脚本。返回 (退出码, stdout, stderr)。脚本崩了也如实上报。"""
    try:
        p = subprocess.run([sys.executable] + args, input=stdin_data, cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:  # noqa: BLE001
        return 3, "", "%s: %s" % (type(e).__name__, e)


def main(argv=None):
    _force_utf8()
    p = ArgParser(prog="pipeline.py", description="一键跑完整条反幻觉核查链")
    p.add_argument("--root", default=".", help="项目根目录")
    p.add_argument("--checks", help="hardcheck 批量配置 JSON")
    p.add_argument("--claims", help="输出契约 JSON（claim_lint 的输入）")
    p.add_argument("--level", default="L1", choices=["L0", "L1", "L2"], help="闸门等级")
    p.add_argument("--offline", action="store_true", help="全程不联网")
    p.add_argument("--no-deps", action="store_true", help="跳过依赖幻觉检查")
    p.add_argument("--strict-deps", action="store_true", help="依赖检查把可疑项也当失败")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--report", help="报告写入该 JSON 文件")
    a = p.parse_args(argv)

    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        err("项目根目录不存在：%s" % root)
        return EXIT_USAGE

    steps = []
    worst = 0

    # [1] 硬核查
    if a.checks:
        args = [os.path.join(HERE, "hardcheck.py"), "--batch", a.checks]
        if a.offline:
            args.append("--offline")
        args.append("--json")
        code, out, errout = run_step(args, cwd=root)
        data = None
        try:
            data = json.loads(out)
        except Exception:
            pass
        steps.append({"step": "hardcheck", "exit_code": code,
                      "summary": (data or {}).get("summary"),
                      "stderr": errout.strip()[:300]})
        worst = max(worst, SEVERITY.get(code, 3))
    else:
        steps.append({"step": "hardcheck", "exit_code": None, "skipped": "未提供 --checks"})

    # [2] 依赖幻觉防护
    if not a.no_deps:
        args = [os.path.join(HERE, "dep_guard.py"), "--root", root]
        if a.offline:
            args.append("--offline")
        if a.strict_deps:
            args.append("--strict")
        args.append("--json")
        code, out, errout = run_step(args, cwd=root)
        data = None
        try:
            data = json.loads(out)
        except Exception:
            pass
        steps.append({"step": "dep_guard", "exit_code": code,
                      "counts": (data or {}).get("counts"),
                      "stderr": errout.strip()[:300]})
        if code == 3:
            steps[-1]["note"] = "脚本执行失败（已如实记录，不是通过）"
        worst = max(worst, SEVERITY.get(code, 3))
    else:
        steps.append({"step": "dep_guard", "exit_code": None, "skipped": "--no-deps"})

    # [3] 输出契约闸门
    if a.claims:
        args = [os.path.join(HERE, "claim_lint.py"), "--input", a.claims,
                "--min-level", a.level, "--json"]
        code, out, errout = run_step(args, cwd=root)
        data = None
        try:
            data = json.loads(out)
        except Exception:
            pass
        steps.append({"step": "claim_lint", "exit_code": code,
                      "gate": (data or {}).get("gate"),
                      "errors": len((data or {}).get("errors") or []),
                      "stderr": errout.strip()[:300]})
        worst = max(worst, SEVERITY.get(code, 3))
    else:
        steps.append({"step": "claim_lint", "exit_code": None, "skipped": "未提供 --claims"})

    final = {v: k for k, v in SEVERITY.items()}[worst]
    verdict = {0: "PASSED", 1: "UNVERIFIED", 2: "BLOCKED", 3: "ERROR"}[worst]

    payload = {
        "tool": "pipeline.py",
        "root": root,
        "offline": a.offline,
        "steps": steps,
        "verdict": verdict,
        "hint": "BLOCKED = 不许交付；UNVERIFIED = 记为未验证，不许默认通过。",
    }

    if a.report:
        try:
            from _common import atomic_write_json
            atomic_write_json(a.report, payload)
        except Exception as e:  # noqa: BLE001
            err("写报告失败：%s" % e)

    if a.json:
        emit(payload, as_json=True)
    else:
        lines = ["=== pipeline：%s ===" % root]
        for s in steps:
            name = s["step"]
            if s.get("skipped"):
                lines.append("[SKIP] %s :: %s" % (name, s["skipped"]))
                continue
            extra = []
            if s.get("summary"):
                extra.append("pass=%(pass)d fail=%(fail)d unverified=%(unverified)d" % s["summary"])
            if s.get("counts"):
                extra.append("BLOCK=%d SUSPICIOUS=%d WARN=%d UNVERIFIED=%d" % (
                    s["counts"].get("BLOCK", 0), s["counts"].get("SUSPICIOUS", 0),
                    s["counts"].get("WARN", 0), s["counts"].get("UNVERIFIED", 0)))
            if s.get("gate"):
                extra.append("gate=%s errors=%d" % (s["gate"], s.get("errors", 0)))
            lines.append("[%s] %s :: exit=%s %s" % (
                "PASS" if s["exit_code"] == 0 else "FAIL", name, s["exit_code"],
                " | ".join(extra)))
        lines.append("")
        lines.append("总判定：%s" % verdict)
        if verdict == "BLOCKED":
            lines.append(">>> 不放行。修完失败项再交付。")
        elif verdict == "UNVERIFIED":
            lines.append(">>> 有未验证项：只能标 unverified，不能当通过。")
        emit(None, as_json=False, human_lines=lines)

    return final


if __name__ == "__main__":
    sys.exit(main())
