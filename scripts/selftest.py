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
            s.reconfigure(encoding="utf-8", errors="replace")
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

    # --- v4.2.1 新增：命令执行 RCE 回归 -------------------------------
    # 历史：verify_gate 曾用 subprocess.run(cmd, shell=True, cwd=cwd) 执行
    # claims 文件里的 command。claims 文件在**项目目录内** —— clone 一个恶意
    # 仓库，Stop hook 就会以用户身份静默执行它写的任意命令，且完全绕过
    # guard_bash（hook 子进程不走 Bash 工具调用，PreToolUse 从不触发）。
    #
    # 这一组断言的是**副作用未发生**，不是退出码。只看退出码的测试在
    # 「修错了但恰好退出码对」时会给假绿，而安全回归恰恰最怕假绿。
    _PAYLOAD_LINES = ["import sys",
                      'open(sys.argv[1], "w").write("pwned")',
                      ""]

    def _write_payload(d):
        fp = os.path.join(d, "payload.py")
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(chr(10).join(_PAYLOAD_LINES))
        return fp, os.path.join(d, "PWNED.txt")

    if os.path.exists(vg):
        rce_dir = os.path.join(tmp, "rce")
        os.makedirs(os.path.join(rce_dir, ".touchstone"), exist_ok=True)
        _pl, marker = _write_payload(rce_dir)
        evil = '"%s" "%s" "%s"' % (sys.executable, _pl, marker)
        claims = os.path.join(rce_dir, ".touchstone", "execution_claims.json")

        def _claims(obj):
            with open(claims, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, ensure_ascii=False)

        # 1) 含 command 的声明：不执行、不阻断
        _claims({"execution_claims": [{"claim": "恶意 command", "evidence": "真实输出",
                                       "verified": True, "command": evil}]})
        case("hook verify_gate 含 command 的声明不阻断（command 不执行）", [vg], 0,
             stdin_data=json.dumps({"cwd": rce_dir}))
        results.append(Result(
            "RCE 回归：verify_gate 未触发 payload（副作用文件不存在）",
            not os.path.exists(marker), False, os.path.exists(marker),
            "marker=%s" % marker))

        # 2) 同一份含 command 的声明，若另有真实缺陷仍须阻断 ——
        #    证明删掉执行路径没有把闸门一起削掉
        _claims({"execution_claims": [{"claim": "没有证据", "verified": True,
                                       "command": evil}]})
        case("hook verify_gate 含 command 但缺 evidence 仍阻断（闸门未削弱）", [vg], 2,
             stdin_data=json.dumps({"cwd": rce_dir}))
        results.append(Result(
            "RCE 回归：阻断用例同样未触发 payload",
            not os.path.exists(marker), False, os.path.exists(marker),
            "marker=%s" % marker))

    # --- v4.2.1 新增：ledger 的 command verify 默认不执行 ----------------
    lg_dir = os.path.join(tmp, "ledger-rce")
    os.makedirs(os.path.join(lg_dir, ".touchstone"), exist_ok=True)
    _lpl, lg_marker = _write_payload(lg_dir)
    lg_evil = '"%s" "%s" "%s"' % (sys.executable, _lpl, lg_marker)
    lg_file = os.path.join(lg_dir, ".touchstone", "ledger.json")
    with open(lg_file, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "entries": [{
            "id": 1, "kind": "fact", "subject": "S", "value": "V",
            "status": "confirmed",
            "verify": {"type": "command", "cmd": lg_evil},
        }]}, f, ensure_ascii=False)

    case("ledger command verify 默认不执行（记 unverified，不当 drift）",
         [lg, "--file", lg_file, "check", "--root", lg_dir], 0)
    results.append(Result(
        "RCE 回归：ledger check 未触发 payload（副作用文件不存在）",
        not os.path.exists(lg_marker), False, os.path.exists(lg_marker),
        "marker=%s" % lg_marker))

    case("ledger command verify 显式 --allow-exec 后才执行",
         [lg, "--file", lg_file, "check", "--root", lg_dir, "--allow-exec"], 0)
    results.append(Result(
        "授权路径可用：--allow-exec 后 payload 确已执行",
        os.path.exists(lg_marker), True, os.path.exists(lg_marker),
        "marker=%s" % lg_marker))

    # --- v4.3 新增：生物医学模式声明核查（19-bio-mode / bio_guard.py）-----
    # 设计要点：**合规样本必须零告警**（会吵的闸门一定被绕过）；
    # 坏样本必须覆盖「沉默型」幻觉 —— KEGG 传学名、注释库与物种不配这两类，
    # cp_lint 会放行（参数名合法）、R 也不报错（静默返回空集），只能在这里拦。
    bg = os.path.join(HERE, "bio_guard.py")
    if os.path.exists(bg):
        bio = os.path.join(tmp, "bio")
        os.makedirs(bio, exist_ok=True)

        good_bio = os.path.join(bio, "good.md")
        with open(good_bio, "w", encoding="utf-8") as f:
            f.write(
                "# 分析报告\n\n"
                "物种：人类（Homo sapiens，GRCh38），基因符号按 HGNC 规范书写。\n"
                "校正方法为 Benjamini-Hochberg，报告 padj 与 log2FC（以 2 为底）。\n"
                "TP53（padj = 1.2e-05, log2FC = 2.31）显著上调。\n"
                "结论：TP53 与增殖表型相关，可能参与细胞周期调控，\n"
                "因果关系需孟德尔随机化进一步验证。\n"
                "本结论基于 TCGA-LUAD 队列（n = 512）的人肺腺癌组织，不适用于其他癌种。\n")
        case("bio_guard 合规报告零告警（不误报）", [bg, "--file", good_bio, "--offline"], 0)

        bad_bio = os.path.join(bio, "bad.md")
        with open(bad_bio, "w", encoding="utf-8") as f:
            f.write(
                "# 分析报告\n\n"
                "我们在小鼠模型中敲除了 TP53，发现 MT-ND1 上调。\n"
                "使用 org.Hs.eg.db 注释，富集到 hsa04115 通路。\n"
                "p < 0.05，logFC = 1.5。\n"
                "该结果证明了 TP53 导致肿瘤发生。\n"
                "GENE1 也上调。\n"
                "采用 t 检验分析 5000 个细胞。\n"
                "参考文献：PMID: 123\n")
        case("bio_guard 坏报告被拦（物种/注释库/口径/外推/文献）",
             [bg, "--file", bad_bio, "--offline"], 1)

        bad_r = os.path.join(bio, "bad.R")
        with open(bad_r, "w", encoding="utf-8") as f:
            f.write('library(clusterProfiler)\n'
                    'ego <- enrichKEGG(gene = entrez, organism = "Homo sapiens")\n'
                    'ego2 <- enrichWP(gene = entrez, organism = "hsa")\n'
                    'obj <- RunUMAP(obj, dims = 1:30)\n')
        case("bio_guard 脚本 organism 语义错误（cp_lint 放行的那一类）",
             [bg, "--file", bad_r, "--offline"], 1)

        cite_bio = os.path.join(bio, "cite.md")
        with open(cite_bio, "w", encoding="utf-8") as f:
            f.write("# 参考\nPMID: 34567890\nDOI: 10.1038/s41586-024-07500-0\n")
        case("bio_guard 合法 PMID/DOI 不误判（离线）",
             [bg, "--file", cite_bio, "--only", "citation", "--offline"], 0)

        case("bio_guard 目录不存在 → 用法错误",
             [bg, "--root", os.path.join(tmp, "no-such-dir"), "--offline"], 3)
        case("bio_guard 无目标 → 用法错误", [bg, "--offline"], 3)
        case("bio_guard 未知检查器 → 用法错误",
             [bg, "--file", good_bio, "--only", "not-a-check", "--offline"], 3)
        # --strict：格式合法但需人工确认的项，在严格模式下按失败计
        case("bio_guard --strict 将待确认项计为失败",
             [bg, "--file", cite_bio, "--only", "citation", "--strict"], 1)

        # --exclude：教学/规范文档必须能被排掉，否则扫描结果是一屏假红
        _c1, _o1, _ = run([bg, "--root", bio, "--offline", "--json", "--exclude", "*.R"])
        _c2, _o2, _ = run([bg, "--root", bio, "--offline", "--json"])
        try:
            n_excl = len(json.loads(_o1)["scanned"])
        except Exception:
            n_excl = -1
        try:
            n_full = len(json.loads(_o2)["scanned"])
        except Exception:
            n_full = -1
        results.append(Result(
            "bio_guard --exclude 生效（排除后目标减少）",
            n_excl == n_full - 1 and n_excl > 0, n_full - 1, n_excl,
            "excluded=%s full=%s" % (n_excl, n_full)))

        # ── 相关性门：非生物医学文件不该被生信检查（否则源码常量被当基因符号）
        # 这条正是本轮审计暴露的主缺陷：此前对任何 .py 都报 5 条，其中 1 条 FAIL。
        # 样本里刻意放 PASS / FAIL 这类独立大写 token —— 它们会被基因正则命中，
        # 从而证明"门内 0 条、强制全查 >0 条"这组差异是真实存在的。
        plain_py = os.path.join(bio, "plain_scan.py")
        with open(plain_py, "w", encoding="utf-8") as f:
            f.write("""# 一个普通工程脚本，不含任何生物医学内容
PASS = 'pass'
FAIL = 'fail'


def run(p):
    return p.stdout
""")
        case("bio_guard 相关性门：非生物医学脚本被跳过（不误报基因符号）",
             [bg, "--file", plain_py, "--offline"], 2)
        _cg, _og, _ = run([bg, "--file", plain_py, "--offline", "--json"])
        _cf, _of, _ = run([bg, "--file", plain_py, "--no-relevance-gate",
                           "--offline", "--json"])
        try:
            _n_gated = len(json.loads(_og)["results"])
            _n_forced = len(json.loads(_of)["results"])
        except Exception:
            _n_gated, _n_forced = -1, -1
        results.append(Result(
            "bio_guard --no-relevance-gate 才跑检查（门内 0 条 / 强制 >0 条）",
            _n_gated == 0 and _n_forced > 0,
            "门内 0 条、强制 >0 条",
            "gated=%s forced=%s" % (_n_gated, _n_forced)))

        # 中文注释里的全角标点必须被忽略（只查代码 token）。
        # 此前实现是"出现即 FAIL"，于是任何带中文注释的脚本必然报红 ——
        # 恒红的检查等于没有信号，和"无网必红"是同一类缺陷。
        cn_py = os.path.join(bio, "cn_comment.py")
        with open(cn_py, "w", encoding="utf-8") as f:
            f.write("""# 差异表达分析（DESeq2）：TCGA-LUAD 队列
# 注意：p 值需做多重检验校正，显著阈值为（0.05）
padj = 0.01
""")
        case("bio_guard 中文注释里的全角标点不误判（只查代码 token）",
             [bg, "--file", cn_py, "--only", "gene", "--offline"], 0)

        # UniProt accession（必含数字）与大写下划线常量必须区分开
        acc_py = os.path.join(bio, "acc.py")
        with open(acc_py, "w", encoding="utf-8") as f:
            f.write("""# 人类 TP53 蛋白（UniProt P04637）
EXIT_OK = 0
MAX_TARGETS = 10
""")
        _ca, _oa, _ = run([bg, "--file", acc_py, "--only", "gene", "--offline", "--json"])
        try:
            _fa = [x["detail"] for x in json.loads(_oa)["results"]]
        except Exception:
            _fa = []
        _hit_acc = any("P04637" in x for x in _fa)
        _hit_const = any(("EXIT_OK" in x) or ("MAX_TARGETS" in x) for x in _fa)
        results.append(Result(
            "bio_guard 真 UniProt accession 会提示、常量不误判",
            _hit_acc and not _hit_const, "含 P04637、不含 EXIT_OK",
            "acc=%s const=%s" % (_hit_acc, _hit_const)))

        # 输出契约：kind 必须落在检查器名上，下游才能按检查器聚合。
        # 此前 r() 把 kind 填成了文件路径，聚合结果全失真。
        _ck, _ok2, _ = run([bg, "--file", bad_bio, "--offline", "--json"])
        try:
            _kinds = sorted({x["kind"] for x in json.loads(_ok2)["results"]})
        except Exception:
            _kinds = []
        results.append(Result(
            "bio_guard JSON 的 kind 是检查器名（不是文件路径）",
            bool(_kinds) and set(_kinds) <= set(
                ["species", "gene", "id", "orgdb", "stat",
                 "numeric", "overclaim", "citation"]),
            "全为检查器名", ",".join(_kinds)))

        # --exclude 直接写目录名也要生效（此前只认 glob，目录名静默失效）
        _sub = os.path.join(bio, "sub_notes")
        os.makedirs(_sub, exist_ok=True)
        with open(os.path.join(_sub, "notes.md"), "w", encoding="utf-8") as f:
            f.write("""# 生信笔记
物种：人类（Homo sapiens）
""")
        _cd, _od, _ = run([bg, "--root", bio, "--offline", "--json",
                           "--exclude", "sub_notes"])
        try:
            _paths = json.loads(_od)["scanned"]
        except Exception:
            _paths = []
        results.append(Result(
            "bio_guard --exclude 支持直接写目录名",
            bool(_paths) and not any("sub_notes" in p for p in _paths),
            "scanned 不含 sub_notes/*",
            "scanned=%d 命中=%s" % (len(_paths),
                                    any("sub_notes" in p for p in _paths))))

        # pipeline 接入：生信步骤与其它步骤同等的"可选 / 失败即拦"
        case("pipeline --bio 串联生信核查（坏样本 → 拦）",
             [pl, "--root", tmp, "--no-deps", "--offline", "--bio", bad_bio], 1)
        case("pipeline --bio 串联生信核查（合规样本 → 放行）",
             [pl, "--root", tmp, "--no-deps", "--offline", "--bio", good_bio], 0)
        case("pipeline 不传 --bio 时该步跳过（不影响总判定）",
             [pl, "--root", tmp, "--no-deps", "--offline"], 0)

    # audit.py：发布前自检脚本，此前**零测试覆盖** —— 一个检查别人合规性的
    # 脚本自己不在任何检查范围内，是明显的结构性盲区。
    au = os.path.join(HERE, "audit.py")
    if os.path.exists(au):
        case("audit --json 在仓库自身可跑通", [au, "--json"], 0)
        case("audit --strict 在仓库自身无 ERROR/WARN", [au, "--strict"], 0)
        case("audit 未知参数 → 用法错误（退出码 3，不是 2）",
             [au, "--definitely-not-an-option"], 3)

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
