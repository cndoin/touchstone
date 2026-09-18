#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""selftest.py —— 套件自检（一键验证"能不能稳定跑"）

跑完所有脚本的关键路径：通过路径、失败路径、用法错误路径。
任何一项不符预期就报 FAIL 并返回非零退出码。

用法：
  python scripts/selftest.py            # 人类可读
  python scripts/selftest.py --json     # JSON（CI 用）

退出码：0=全部通过 1=存在失败
设计：全部用离线/本地用例，不依赖网络；临时文件写在系统临时目录，不污染项目。
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# --- guard_bash 拦截/放行语料 -------------------------------------------------
# 放行侧必须包含「长得像危险命令、其实无害」的输入。只测 `git status` 这种与
# 危险模式毫无相似度的命令等于没测：历史 bug（rm -rf /tmp/x 误伤、
# rm -fr ./dist 误伤、git push --force-with-lease 误伤）全部发生在这个空白区。
#
# 漏放侧的教训是「同义写法必须同时覆盖」：`rm -rf ~/*` 一开始就拦，
# 但语义完全一样的 `rm -rf $HOME/*`、`rm -rf ${HOME}/*` 却放行；
# `rm -rf ~/.*`（清空家目录全部点文件，含 .ssh）同样漏放。
# 补规则时请按「同一件事的所有写法」而不是「我想到的那种写法」来列用例。
GUARD_BLOCK = [
    ("根目录", "rm -rf /"),
    ("根目录通配", "rm -rf /*"),
    ("家目录", "rm -rf ~"),
    ("家目录全部内容", "rm -rf ~/*"),
    ("家目录点文件", "rm -rf ~/.*"),
    ("家目录全部内容（变量写法）", "rm -rf $HOME/*"),
    ("家目录全部内容（花括号写法）", "rm -rf ${HOME}/*"),
    ("带引号的变量目标", 'rm -rf "$HOME"'),
    ("当前目录通配", "rm -rf *"),
    ("当前目录", "rm -rf ."),
    ("当前目录点文件", "rm -rf ./.*"),
    ("上级目录", "rm -rf .."),
    ("上级目录跳级", "rm -fr ../.."),
    ("上级目录跳级全部内容", "rm -rf ../../*"),
    ("变量目标（静态不可求值）", "rm -rf $HOME"),
    ("旗标分开写", "rm -r -f /"),
    ("长旗标写法", "rm --recursive --force /"),
    ("强制推送 -f", "git push -f"),
    ("强制推送 --force", "git push --force origin main"),
    ("无 WHERE 的删表", 'psql -c "DROP TABLE users"'),
]

GUARD_ALLOW = [
    ("临时目录清理", "rm -rf /tmp/build"),
    ("临时目录全部内容", "rm -rf /tmp/*"),
    ("家目录子目录清理", "rm -rf ~/cache"),
    ("家目录点目录清理", "rm -rf ~/.cache"),
    ("家目录普通子目录", "rm -rf ~/Documents"),
    # 实测 bash 不对 `~*` 做家目录展开（只 glob 当前目录里以 ~ 开头的文件名），
    # 它不是家目录，拦了属于误伤
    ("非家目录展开的波浪号", "rm -rf ~*"),
    ("相对路径清理（-fr 写法）", "rm -fr ./dist"),
    ("依赖目录清理", "rm -rf node_modules"),
    ("通配后缀清理", "rm -rf *.log"),
    ("上级子目录清理", "rm -rf ../build"),
    ("变量子目录清理", "rm -rf $HOME/cache"),
    ("路径中含跳级但目标安全", "rm -rf build/../dist"),
    ("安全强推（--force-with-lease）", "git push --force-with-lease origin main"),
    ("push 后接其他命令", "git push; ls -f"),
    ("普通查询", "git status"),
]


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def run(args, stdin_data=None, cwd=None):
    proc = subprocess.run([sys.executable] + args, input=stdin_data, cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


class Result(object):
    def __init__(self, name, ok, expected, actual, note=""):
        self.name = name
        self.ok = ok
        self.expected = expected
        self.actual = actual
        self.note = note

    def as_dict(self):
        return {"case": self.name, "ok": self.ok, "expected": self.expected,
                "actual": self.actual, "note": self.note}


def main(argv=None):
    _utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    # 本脚本不接任何参数；以前传 --help 会被静默忽略、直接跑全套，
    # 容易让人误以为"help 输出就是结果"。这里显式给出说明。
    if [a for a in argv if a in ("-h", "--help")]:
        print(__doc__ or "touchstone 自检")
        print("\n用法：python scripts/selftest.py [--json]")
        # 别在这里写死用例条数：加一条用例就会让这行变成假信息
        print("说明：无参数选项，跑完全部用例后按失败数决定退出码。")
        return 0
    as_json = "--json" in argv

    tmp = tempfile.mkdtemp(prefix="touchstone-selftest-")
    results = []

    def case(name, args, expected, stdin_data=None, cwd=None, note=""):
        code, out, err = run(args, stdin_data=stdin_data, cwd=cwd)
        ok = (code == expected)
        results.append(Result(name, ok, expected, code, note or (err.strip()[:120])))

    hc = os.path.join(HERE, "hardcheck.py")
    cl = os.path.join(HERE, "claim_lint.py")
    lg = os.path.join(HERE, "ledger.py")
    sc = os.path.join(HERE, "selfcheck.py")
    rg = os.path.join(HERE, "regression.py")

    # --- hardcheck ---
    case("hardcheck 通过路径（文件存在）", [hc, "--file", os.path.join(ROOT, "SKILL.md"), "--offline"], 0)
    case("hardcheck 失败路径（文件不存在）",
         [hc, "--file", os.path.join(ROOT, "definitely-not-exists.xyz"), "--offline"], 1)
    case("hardcheck 用法错误（无检查项）", [hc, "--offline"], 3)
    case("hardcheck 离线跳过网络项（记为 unverified）",
         [hc, "--url", "https://example.com", "--offline"], 2)

    # --- claim_lint ---
    case("claim_lint 闸门放行（合规样例）",
         [cl, "--input", os.path.join(ROOT, "examples", "claims-good.json")], 0)
    case("claim_lint 闸门拦截（故意做错的样例）",
         [cl, "--input", os.path.join(ROOT, "examples", "claims-bad.json"), "--min-level", "L2"], 1)
    case("claim_lint 输入不存在（用法错误）",
         [cl, "--input", os.path.join(tmp, "nope.json")], 3)

    # --- ledger ---
    ledger_file = os.path.join(tmp, ".touchstone", "ledger.json")
    probe = os.path.join(tmp, "README.md")
    with open(probe, "w", encoding="utf-8") as f:
        f.write("# probe\nuses Hilt for DI\n")

    case("ledger add", [lg, "--file", ledger_file, "add", "--kind", "decision",
                        "--subject", "DI 框架", "--value", "Hilt",
                        "--verify-file", "README.md", "--verify-pattern", "hilt"], 0)
    case("ledger check 一致", [lg, "--file", ledger_file, "check", "--root", tmp], 0)
    with open(probe, "w", encoding="utf-8") as f:
        f.write("# probe\nuses Koin for DI\n")
    case("ledger check 检出 drift", [lg, "--file", ledger_file, "check", "--root", tmp], 1)

    # --- selfcheck ---
    samples_file = os.path.join(tmp, "samples.json")
    with open(samples_file, "w", encoding="utf-8") as f:
        json.dump({"question": "2+3=?", "samples": ["5", "5", "等于5", "5"]},
                  f, ensure_ascii=False)
    case("selfcheck 高一致", [sc, "--samples", samples_file], 0)
    case("selfcheck 灰区（多样本分歧）",
         [sc, "--samples", os.path.join(ROOT, "examples", "samples.json")], 2)

    low_file = os.path.join(tmp, "samples-low.json")
    with open(low_file, "w", encoding="utf-8") as f:
        json.dump({"question": "这个项目用的什么框架？",
                   "samples": ["Hilt", "Koin", "Dagger", "没用 DI 框架"]}, f,
                  ensure_ascii=False)
    case("selfcheck 低一致（危险信号，退出码 4）", [sc, "--samples", low_file], 4)

    # --- regression ---
    case("regression 模板集（无 FAIL）",
         [rg, "--cases", os.path.join(ROOT, "assets", "regression-cases.json")], 0)

    # --- hooks ---
    gb = os.path.join(ROOT, "adapters", "claude-code", "hooks", "guard_bash.py")
    vg = os.path.join(ROOT, "adapters", "claude-code", "hooks", "verify_gate.py")
    if os.path.exists(gb):
        for label, cmd in GUARD_BLOCK:
            case("hook guard_bash 拦截：%s" % label, [gb], 2,
                 stdin_data=json.dumps({"tool_input": {"command": cmd}}))
        for label, cmd in GUARD_ALLOW:
            case("hook guard_bash 放行：%s" % label, [gb], 0,
                 stdin_data=json.dumps({"tool_input": {"command": cmd}}))
        case("hook guard_bash 垃圾输入不阻断", [gb], 0, stdin_data="not-json")
    if os.path.exists(vg):
        case("hook verify_gate 无声明文件时放行", [vg], 0,
             stdin_data=json.dumps({"cwd": tmp}))

    # --- v3 新增：依赖幻觉防护 ---
    dg = os.path.join(HERE, "dep_guard.py")
    clean = os.path.join(tmp, "clean")
    os.makedirs(os.path.join(clean, "src"), exist_ok=True)
    with open(os.path.join(clean, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"dependencies": {"react": "^18"}}, f)
    with open(os.path.join(clean, "src", "helper.ts"), "w", encoding="utf-8") as f:
        f.write("export function help(){return 1}\n")
    with open(os.path.join(clean, "src", "a.ts"), "w", encoding="utf-8") as f:
        f.write("import { help } from './helper'\n")
    case("dep_guard 干净项目（离线）", [dg, "--root", clean, "--offline"], 0)

    dirty = os.path.join(tmp, "dirty")
    os.makedirs(os.path.join(dirty, "src"), exist_ok=True)
    with open(os.path.join(dirty, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"dependencies": {}}, f)
    with open(os.path.join(dirty, "src", "b.ts"), "w", encoding="utf-8") as f:
        f.write("import X from 'totally-not-a-real-pkg'\nimport y from './nope'\n")
    case("dep_guard 检出幻影依赖/路径（离线）", [dg, "--root", dirty, "--offline"], 1)

    # --- v3 新增：pipeline 编排 ---
    pl = os.path.join(HERE, "pipeline.py")
    checks_file = os.path.join(tmp, "checks.json")
    with open(checks_file, "w", encoding="utf-8") as f:
        json.dump({"files": [os.path.join(clean, "src", "a.ts")]}, f)
    # --- v3.2 新增：可插拔检测器桥接（不依赖外部库，只探测）---
    vf = os.path.join(HERE, "verifiers.py")
    if os.path.exists(vf):
        case("verifiers --list（外部缺失也应正常返回）", [vf, "--list"], 0)
        case("verifiers 未知检测器名 → 用法错误", [vf, "--require", "definitely-not-real"], 3)
        # --- v3.3 新增：模型能力分档 ---
    mp = os.path.join(HERE, "model_profile.py")
    if os.path.exists(mp):
        case("model_profile --list", [mp, "--list"], 0)
        case("model_profile 强模型 → 允许自我核查",
             [mp, "--model", "claude-opus-4", "--net", "on", "--json"], 0)
        case("model_profile 弱模型 + 无联网 → 强制外部证据",
             [mp, "--model", "gpt-4o-mini", "--net", "off", "--json"], 0)
        case("model_profile 未知型号 → 保守默认（不放松）",
             [mp, "--model", "totally-unknown-model-xyz", "--json"], 0)
        case("model_profile 非法档位 → 用法错误",
             [mp, "--model", "x", "--override-tier", "Z"], 3)

    case("verifiers 无参数 → 用法错误", [vf], 3)

    # --- v3.2 新增：增量核查（需 git，缺失则跳过）---
    if os.path.exists(dg):
        probe = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                               cwd=ROOT, capture_output=True, text=True)
        if probe.returncode == 0:
            case("dep_guard 增量核查（仅 git 变更文件）",
                 [dg, "--root", ROOT, "--changed-only", "--offline"], 0)
        # 非 git 环境 → 明确的用法错误（不静默全量扫描）
        case("dep_guard 非 git 目录用 --changed-only → 用法错误",
             [dg, "--root", clean, "--changed-only", "--offline"], 3)

    case("pipeline 一键跑通（离线，跳过依赖）",
         [pl, "--root", clean, "--checks", checks_file, "--offline", "--no-deps"], 0)
    case("pipeline 根目录不存在（用法错误）",
         [pl, "--root", os.path.join(tmp, "no-such-dir"), "--no-deps", "--offline"], 3)

    # --- v3 新增：并发与缓存 ---
    case("hardcheck 并发模式",
         [hc, "--file", os.path.join(ROOT, "SKILL.md"), "--offline", "--jobs", "2"], 0)

    # --- v3 新增：子 agent 闸门 / 压缩快照 ---
    sg = os.path.join(ROOT, "adapters", "claude-code", "hooks", "subagent_gate.py")
    if os.path.exists(sg):
        case("hook subagent_gate 拦住无证据的完成断言", [sg], 2,
             stdin_data='{"tool_response":"已完成全部任务"}')
        case("hook subagent_gate 放行有证据的报告", [sg], 0,
             stdin_data='{"tool_response":"已完成，exit=0，输出：BUILD SUCCESSFUL"}')
        case("hook subagent_gate 空输入放行", [sg], 0, stdin_data="{}")

    ps = os.path.join(ROOT, "adapters", "claude-code", "hooks", "precompact_snapshot.py")
    if os.path.exists(ps):
        case("hook precompact_snapshot 生成快照", [ps], 0,
             stdin_data=json.dumps({"cwd": tmp}))
        snaps = os.path.join(tmp, ".touchstone", "snapshots")
        results.append(Result(
            "precompact 快照文件已落盘",
            os.path.isdir(snaps) and len(os.listdir(snaps)) > 0,
            True, os.path.isdir(snaps) and len(os.listdir(snaps)) > 0,
            ""))

    # --- v3 新增：verify_gate 的阻断循环保护（不撞 8 次上限）---
    if os.path.exists(vg):
        claims_dir = os.path.join(tmp, "gate")
        os.makedirs(os.path.join(claims_dir, ".touchstone"), exist_ok=True)
        with open(os.path.join(claims_dir, ".touchstone", "execution_claims.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"execution_claims": [{"claim": "测试已通过", "verified": True}]}, f)
        case("hook verify_gate 阻断循环内改用温和反馈（exit 0）", [vg], 0,
             stdin_data=json.dumps({"cwd": claims_dir, "stop_hook_active": True}))

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed

    payload = {
        "tool": "selftest.py",
        "python": sys.version.split()[0],
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "cases": [r.as_dict() for r in results],
    }

    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        for r in results:
            sys.stdout.write("%s %s (期望退出码 %s，实际 %s)%s\n" % (
                "[PASS]" if r.ok else "[FAIL]", r.name, r.expected, r.actual,
                ("  <- " + r.note) if (r.note and not r.ok) else ""))
        sys.stdout.write("\n合计 %d：pass=%d fail=%d\n" % (len(results), passed, failed))
        sys.stdout.write("自检：%s" % ("全部通过" if failed == 0 else "存在失败，请检查上方 FAIL 项"))
        sys.stdout.write("\n（深度健壮性测试请跑 scripts/robustness_test.py）\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
