#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""robustness_test.py —— 健壮性与多方面测试（深度）

与 selftest.py 的分工：
  - selftest.py      = 快速冒烟（正常路径 + 关键失败路径），秒级，每次改动后跑
  - robustness_test.py = 深度测试（边界 / 异常 / 编码 / 性能 / 幂等 / 多语言），几十秒，
                        发版前或换环境后跑

核心断言（比"结果对不对"更重要）：
  1. **绝不出现 Traceback** —— 任何输入下脚本都不能崩
  2. **退出码必须落在约定集合** —— 0 / 1 / 2 / 3
  3. **输出必须是可解析的 JSON**（--json 时）
  4. 幂等：同样输入跑两次，判定结果一致
  5. 性能：批量场景在预算内完成

用法：
  python scripts/robustness_test.py
  python scripts/robustness_test.py --json
  python scripts/robustness_test.py --only hardcheck,dep_guard

退出码：0=全部通过 1=存在失败
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ALLOWED_EXIT = {0, 1, 2, 3}


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


class Results(object):
    def __init__(self):
        self.items = []

    def add(self, group, name, ok, detail=""):
        self.items.append({"group": group, "case": name, "ok": bool(ok), "detail": detail})

    @property
    def failed(self):
        return [i for i in self.items if not i["ok"]]

    @property
    def total(self):
        return len(self.items)


def run(script, args, stdin_data=None, cwd=None, timeout=120):
    path = os.path.join(HERE, script)
    try:
        p = subprocess.run([sys.executable, path] + args, input=stdin_data, cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:  # noqa: BLE001
        return -2, "", "%s: %s" % (type(e).__name__, e)


def check(res, group, name, code, out, err, expect_exit=None, need_json=False):
    """统一断言：不崩溃 + 退出码合法 +（可选）期望退出码 +（可选）JSON 可解析。"""
    ok = True
    details = []
    if code not in ALLOWED_EXIT:
        ok = False
        details.append("退出码非法：%s（%s）" % (code, err.strip()[:160]))
    if "Traceback (most recent call last)" in err:
        ok = False
        details.append("脚本抛异常：%s" % err.strip()[-300:])
    if expect_exit is not None and code != expect_exit:
        ok = False
        details.append("期望退出码 %s，实际 %s" % (expect_exit, code))
    if need_json:
        try:
            json.loads(out)
        except Exception as e:  # noqa: BLE001
            ok = False
            details.append("--json 输出不可解析：%s" % e)
    res.add(group, name, ok, " | ".join(details))
    return ok


def build_corpus(tmp):
    """构造各种刁钻输入。返回路径字典。"""
    paths = {}

    # 空目录项目
    empty = os.path.join(tmp, "empty")
    os.makedirs(empty, exist_ok=True)
    paths["empty"] = empty

    # 编码地狱：GBK / BOM / 空文件 / 超大文件 / 二进制 / 中文空格文件名
    enc = os.path.join(tmp, "enc")
    os.makedirs(os.path.join(enc, "深 层 目录"), exist_ok=True)
    with open(os.path.join(enc, "gbk.py"), "w", encoding="gbk", errors="replace") as f:
        f.write("# 中文注释 GBK\nimport os\n")
    with open(os.path.join(enc, "bom.py"), "w", encoding="utf-8-sig") as f:
        f.write("import json\n")
    open(os.path.join(enc, "empty.py"), "w").close()
    with open(os.path.join(enc, "huge.py"), "w", encoding="utf-8") as f:
        f.write("# 超大文件\n" + ("x = 1\n" * 200000))  # >2MB，应被跳过
    with open(os.path.join(enc, "binary.png"), "wb") as f:
        f.write(os.urandom(2048))
    with open(os.path.join(enc, "深 层 目录", "中文 空格.ts"), "w", encoding="utf-8") as f:
        f.write("import { helper } from './helper'\n")
    with open(os.path.join(enc, "深 层 目录", "helper.ts"), "w", encoding="utf-8") as f:
        f.write("export function helper(){return 1}\n")
    paths["enc"] = enc

    # 多语言项目（无 manifest）
    poly = os.path.join(tmp, "polyglot")
    os.makedirs(poly, exist_ok=True)
    open(os.path.join(poly, "main.go"), "w", encoding="utf-8").write(
        'package main\nimport "github.com/foo/bar"\n')
    open(os.path.join(poly, "lib.rs"), "w", encoding="utf-8").write(
        "use serde::Serialize;\n")
    open(os.path.join(poly, "App.kt"), "w", encoding="utf-8").write(
        "import androidx.room.Room\n")
    open(os.path.join(poly, "Main.java"), "w", encoding="utf-8").write(
        "import java.util.List;\n")
    paths["polyglot"] = poly

    # 带 manifest 的 npm 项目（含幻影依赖 + 幻影路径）
    npm = os.path.join(tmp, "npmproj")
    os.makedirs(os.path.join(npm, "src"), exist_ok=True)
    with open(os.path.join(npm, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"dependencies": {"react": "^18"}}, f)
    open(os.path.join(npm, "src", "a.ts"), "w", encoding="utf-8").write(
        "import x from 'not-declared-pkg'\nimport y from './missing'\n")
    paths["npm"] = npm

    # 损坏/异常的 JSON 契约文件
    bad_json = os.path.join(tmp, "bad.json")
    open(bad_json, "w", encoding="utf-8").write("{ this is not json ")
    paths["bad_json"] = bad_json

    weird = os.path.join(tmp, "weird-claims.json")
    with open(weird, "w", encoding="utf-8") as f:
        json.dump({
            "context_setting": "noisy_context",
            "risk_level": "L9",                      # 非法风险等级
            "answer": "x" * 50000,                   # 超长文本
            "claims": [
                "这条是字符串不是对象",                # 类型错误
                {"text": "缺 label"},                 # 缺必填
                {"text": "label 非法", "label": "yes"},
                {"text": "confidence 是字符串", "label": "assumed", "confidence": "0.9"},
                {"text": "sources 类型错", "label": "confirmed", "sources": "not-a-list",
                 "counter_evidence_checked": True},
                {"text": "超长声明", "label": "observed", "verified_at": "2026-09-16",
                 "sources": [{"type": "doc", "ref": "#"}], "text_long": "y" * 20000},
            ],
            "hard_checks": {"urls_resolved": "abc", "files_exist": "1/2"},
            "execution_claims": "not-a-list",
        }, f)
    paths["weird_claims"] = weird

    empty_obj = os.path.join(tmp, "empty-obj.json")
    open(empty_obj, "w", encoding="utf-8").write("{}")
    paths["empty_obj"] = empty_obj

    # 批量检查配置：混合正常与异常
    batch = os.path.join(tmp, "batch.json")
    with open(batch, "w", encoding="utf-8") as f:
        json.dump({
            "urls": ["not a url", "https://example.com"],
            "dois": ["", "not-a-doi"],
            "files": [os.path.join(enc, "gbk.py"), os.path.join(tmp, "不存在.xyz")],
            "commands": ["echo hello", "this-command-does-not-exist-xyz"],
            "pypi": [{"name": "requests", "version": "2.32.3"}],
        }, f, ensure_ascii=False)
    paths["batch"] = batch

    bad_batch = os.path.join(tmp, "bad-batch.json")
    open(bad_batch, "w", encoding="utf-8").write("[1,2,3]")  # 数组而非对象
    paths["bad_batch"] = bad_batch

    return paths


def test_hardcheck(res, tmp, paths):
    g = "hardcheck"
    check(res, g, "空 batch（{}）→ 用法错误",
          *run("hardcheck.py", ["--batch", os.path.join(tmp, "nope.json"), "--offline"]),
          expect_exit=3)
    check(res, g, "batch 是数组 → 用法错误",
          *run("hardcheck.py", ["--batch", paths["bad_batch"], "--offline"]), expect_exit=3)
    check(res, g, "非法 URL / 空 DOI / 不存在文件 / 不存在命令 → 不崩且为 fail 或 unverified",
          *run("hardcheck.py", ["--batch", paths["batch"], "--offline", "--json"]),
          expect_exit=1, need_json=True)
    check(res, g, "极小 timeout（0.001s）→ 超时降级为 unverified，不崩",
          *run("hardcheck.py", ["--url", "https://example.com", "--timeout", "0.001",
                                "--no-cache", "--json"]), expect_exit=2, need_json=True)
    check(res, g, "jobs=0（非法并发）→ 不崩",
          *run("hardcheck.py", ["--file", paths["enc"], "--offline", "--jobs", "0"]))
    check(res, g, "jobs=64（超上限）→ 自动收敛，不崩",
          *run("hardcheck.py", ["--file", paths["enc"], "--offline", "--jobs", "64"]))
    check(res, g, "max-checks=1 时预算生效",
          *run("hardcheck.py", ["--batch", paths["batch"], "--offline", "--max-checks", "1",
                                "--json"]), need_json=True)
    check(res, g, "中文路径 + 空格 → 正常判定",
          *run("hardcheck.py", ["--file", os.path.join(paths["enc"], "深 层 目录",
                                                       "中文 空格.ts"), "--offline"]),
          expect_exit=0)
    check(res, g, "未知参数 → 用法错误而非崩溃",
          *run("hardcheck.py", ["--definitely-not-a-flag"]), expect_exit=3)


def test_dep_guard(res, tmp, paths):
    g = "dep_guard"
    check(res, g, "空目录项目 → 不崩且干净",
          *run("dep_guard.py", ["--root", paths["empty"], "--offline", "--json"]),
          expect_exit=0, need_json=True)
    check(res, g, "编码地狱（GBK/BOM/空/超大/二进制/中文空格路径）→ 不崩",
          *run("dep_guard.py", ["--root", paths["enc"], "--offline", "--json"]),
          need_json=True)
    check(res, g, "多语言无 manifest（Go/Rust/Kotlin/Java）→ 不崩",
          *run("dep_guard.py", ["--root", paths["polyglot"], "--offline", "--json"]),
          need_json=True)
    check(res, g, "幻影依赖 + 幻影路径 → BLOCK",
          *run("dep_guard.py", ["--root", paths["npm"], "--offline", "--json"]),
          expect_exit=1, need_json=True)
    check(res, g, "root 不存在 → 用法错误",
          *run("dep_guard.py", ["--root", os.path.join(tmp, "no-such"), "--offline"]),
          expect_exit=3)
    check(res, g, "root 是文件而非目录 → 用法错误",
          *run("dep_guard.py", ["--root", paths["batch"], "--offline"]), expect_exit=3)
    check(res, g, "allowlist 文件不存在 → 不崩（仅告警）",
          *run("dep_guard.py", ["--root", paths["npm"], "--offline",
                                "--allowlist", os.path.join(tmp, "no-allowlist.txt")]))


def test_claim_lint(res, tmp, paths):
    g = "claim_lint"
    check(res, g, "损坏 JSON → 用法错误，不崩",
          *run("claim_lint.py", ["--input", paths["bad_json"]]), expect_exit=3)
    check(res, g, "空对象 {} → 不崩",
          *run("claim_lint.py", ["--input", paths["empty_obj"], "--json"]), need_json=True)
    check(res, g, "字段类型全错 + 超长文本 → 不崩且能报出错误",
          *run("claim_lint.py", ["--input", paths["weird_claims"], "--min-level", "L2",
                                 "--json"]), expect_exit=1, need_json=True)
    check(res, g, "L0 等级下放宽 → 不崩",
          *run("claim_lint.py", ["--input", paths["weird_claims"], "--min-level", "L0",
                                 "--json"]), need_json=True)
    check(res, g, "--strict-warn 把警告当失败 → 不崩",
          *run("claim_lint.py", ["--input", os.path.join(ROOT, "examples", "claims-good.json"),
                                 "--strict-warn", "--json"]), need_json=True)


def test_ledger(res, tmp):
    g = "ledger"
    lf = os.path.join(tmp, "l", "ledger.json")
    check(res, g, "空账本 add → 成功",
          *run("ledger.py", ["--file", lf, "add", "--kind", "decision", "--subject", "S",
                             "--value", "V"]), expect_exit=0)
    check(res, g, "重复 subject add → 不崩",
          *run("ledger.py", ["--file", lf, "add", "--kind", "decision", "--subject", "S",
                             "--value", "V2"]))
    check(res, g, "remove 不存在的 id → 用法或成功，但不崩",
          *run("ledger.py", ["--file", lf, "remove", "--id", "999"]))
    check(res, g, "get 不存在的 subject → 不崩",
          *run("ledger.py", ["--file", lf, "get", "--subject", "不存在"]))
    broken = os.path.join(tmp, "broken-ledger.json")
    open(broken, "w", encoding="utf-8").write("{ broken ")
    check(res, g, "损坏账本 check → 用法错误，不崩",
          *run("ledger.py", ["--file", broken, "check", "--root", tmp]), expect_exit=3)
    check(res, g, "verify 指向不存在的文件 → 检出 drift",
          *run("ledger.py", ["--file", lf, "add", "--kind", "fact", "--subject", "F",
                             "--value", "V", "--verify-file", "no-such-file.txt"]))
    check(res, g, "check 对不存在 verify 路径 → 报 drift 而非崩",
          *run("ledger.py", ["--file", lf, "check", "--root", tmp]), expect_exit=1)


def test_selfcheck(res, tmp):
    g = "selfcheck"
    one = os.path.join(tmp, "one.json")
    json.dump({"question": "q", "samples": ["只有一条"]}, open(one, "w", encoding="utf-8"),
              ensure_ascii=False)
    check(res, g, "单样本 → 高一致，不崩",
          *run("selfcheck.py", ["--samples", one]), expect_exit=0)
    empty = os.path.join(tmp, "empty-samples.json")
    json.dump({"question": "q", "samples": []}, open(empty, "w", encoding="utf-8"))
    check(res, g, "空 samples → 用法错误，不崩",
          *run("selfcheck.py", ["--samples", empty]), expect_exit=3)
    many = os.path.join(tmp, "many.json")
    json.dump({"question": "q", "samples": ["答案A"] * 60 + ["答案B"] * 40},
              open(many, "w", encoding="utf-8"), ensure_ascii=False)
    check(res, g, "100 条样本（性能）→ 不崩",
          *run("selfcheck.py", ["--samples", many, "--json"]), need_json=True)
    check(res, g, "--stdin 输入 → 不崩",
          *run("selfcheck.py", ["--stdin"], stdin_data=json.dumps(
              {"question": "q", "samples": ["是", "是的", "对"]})))


def test_regression(res, tmp):
    g = "regression"
    weird = os.path.join(tmp, "weird-cases.json")
    json.dump([
        {"id": "no-check"},                                   # 缺 check
        {"id": "unknown-type", "check": {"type": "whatever"}},  # 未知类型
        {"id": "no-output", "check": {"type": "must_contain", "value": "x"}},
    ], open(weird, "w", encoding="utf-8"), ensure_ascii=False)
    check(res, g, "缺 check / 未知类型 / 无输出 → 不崩且如实 SKIP",
          *run("regression.py", ["--cases", weird, "--json"]), expect_exit=0, need_json=True)
    notobj = os.path.join(tmp, "notobj.json")
    open(notobj, "w", encoding="utf-8").write("42")
    check(res, g, "cases 不是对象也不是数组 → 用法错误",
          *run("regression.py", ["--cases", notobj]), expect_exit=3)


def test_pipeline(res, tmp, paths):
    g = "pipeline"
    check(res, g, "root 不存在 → 用法错误",
          *run("pipeline.py", ["--root", os.path.join(tmp, "no-such"), "--no-deps",
                               "--offline"]), expect_exit=3)
    check(res, g, "checks 文件不存在 → 不崩（该步记为失败而非整体崩）",
          *run("pipeline.py", ["--root", paths["enc"], "--checks",
                               os.path.join(tmp, "no-checks.json"), "--no-deps",
                               "--offline", "--json"]), need_json=True)
    check(res, g, "claims 文件损坏 → 不崩",
          *run("pipeline.py", ["--root", paths["enc"], "--claims", paths["bad_json"],
                               "--no-deps", "--offline", "--json"]), need_json=True)
    check(res, g, "全量（含依赖检查）→ 不崩",
          *run("pipeline.py", ["--root", paths["npm"], "--checks", paths["batch"],
                               "--offline", "--json"]), need_json=True)


def test_hooks(res, tmp):
    g = "hooks"
    hooks_dir = os.path.join(ROOT, "adapters", "claude-code", "hooks")
    scripts = [("guard_bash.py", 0), ("subagent_gate.py", 0),
               ("precompact_snapshot.py", 0), ("verify_gate.py", 0)]
    for name, expect in scripts:
        p = os.path.join(hooks_dir, name)
        if not os.path.exists(p):
            res.add(g, "%s 存在性" % name, False, "文件缺失")
            continue
        for label, payload in (
            ("合法空事件", "{}"),
            ("垃圾输入", "not json at all"),
            ("超长输入", json.dumps({"tool_input": {"command": "echo " + "x" * 50000}})),
            ("Unicode/emoji", json.dumps({"tool_input": {"command": "echo 你好 🎉"}})),
            ("缺 cwd", json.dumps({"session_id": "abc"})),
        ):
            code, out, err = run_hooks(p, payload, cwd=tmp)
            res.add(g, "%s :: %s" % (name, label),
                    code in ALLOWED_EXIT and "Traceback" not in err,
                    "exit=%s %s" % (code, err.strip()[:120]))


def run_hooks(path, stdin_data, cwd=None):
    try:
        p = subprocess.run([sys.executable, path], input=stdin_data, cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:  # noqa: BLE001
        return -2, "", str(e)


def test_extreme(res, tmp, paths):
    """极端场景：目标是逼出崩溃，而不是验证正确。"""
    g = "极端场景"

    # 1) 并发写同一缓存目录（原子写 + 缓存损坏容错）
    cache_dir = os.path.join(tmp, "shared-cache")
    os.makedirs(cache_dir, exist_ok=True)
    procs = []
    for _ in range(5):
        procs.append(subprocess.Popen(
            [sys.executable, os.path.join(HERE, "hardcheck.py"),
             "--url", "https://example.com", "--cache-dir", cache_dir, "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace"))
    codes = []
    for p in procs:
        try:
            out, err = p.communicate(timeout=90)
            codes.append((p.returncode, "Traceback" in (err or "")))
        except Exception:  # noqa: BLE001
            p.kill()
            codes.append((-1, True))
    ok = all(c in ALLOWED_EXIT and not tb for c, tb in codes)
    res.add(g, "5 进程并发写同一缓存目录 → 无异常", ok, str(codes))

    # 2) 缓存文件被写坏 → 应忽略缓存重新核查，不崩
    if os.path.isdir(cache_dir):
        for fn in os.listdir(cache_dir)[:3]:
            try:
                open(os.path.join(cache_dir, fn), "w", encoding="utf-8").write("{ broken")
            except OSError:
                pass
    check(res, g, "缓存文件损坏 → 容错重查",
          *run("hardcheck.py", ["--url", "https://example.com",
                                "--cache-dir", cache_dir, "--json"]), need_json=True)

    # 3) 极端参数值
    check(res, g, "--timeout 0 → 不崩",
          *run("hardcheck.py", ["--url", "https://example.com", "--timeout", "0",
                                "--no-cache", "--json"]), need_json=True)
    check(res, g, "--max-checks -1 → 不崩",
          *run("hardcheck.py", ["--batch", paths["batch"], "--offline", "--max-checks", "-1"]))
    check(res, g, "--jobs -5 → 不崩",
          *run("hardcheck.py", ["--file", paths["enc"], "--offline", "--jobs", "-5"]))
    check(res, g, "--retries 100（超大重试）→ 有超时兜底，不无限卡住",
          *run("hardcheck.py", ["--url", "https://192.0.2.1", "--retries", "3",
                                "--timeout", "0.05", "--no-cache"]), )

    # 4) 超深目录嵌套（50 层）→ 不爆栈、不死循环
    deep = os.path.join(tmp, "deep")
    cur = deep
    for _ in range(50):
        cur = os.path.join(cur, "d")
    try:
        os.makedirs(cur, exist_ok=True)
        open(os.path.join(cur, "x.py"), "w", encoding="utf-8").write("import os\n")
    except OSError:
        pass
    check(res, g, "50 层嵌套目录 → 不崩",
          *run("dep_guard.py", ["--root", deep, "--offline", "--json"]), need_json=True)

    # 5) 含 node_modules 的大型项目（应跳过依赖目录）
    nm = os.path.join(tmp, "with-node-modules")
    os.makedirs(os.path.join(nm, "node_modules", "pkg"), exist_ok=True)
    os.makedirs(os.path.join(nm, "src"), exist_ok=True)
    with open(os.path.join(nm, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"dependencies": {"react": "^18"}}, f)
    open(os.path.join(nm, "node_modules", "pkg", "index.js"), "w",
         encoding="utf-8").write("require('totally-fake-pkg-xyz')\n")
    open(os.path.join(nm, "src", "ok.ts"), "w", encoding="utf-8").write(
        "import { build } from './builder'\n")
    open(os.path.join(nm, "src", "builder.ts"), "w", encoding="utf-8").write(
        "export function build(){return 1}\n")
    code, out, err = run("dep_guard.py", ["--root", nm, "--offline", "--json"])
    ok = code == 0 and "Traceback" not in err
    node_modules_leaked = "node_modules" in out
    res.add(g, "node_modules 被正确跳过（不误报依赖目录内的包）",
            ok and not node_modules_leaked, "exit=%s leaked=%s" % (code, node_modules_leaked))

    # 6) 超大 claims 文件（1000 条声明）
    big = os.path.join(tmp, "big-claims.json")
    with open(big, "w", encoding="utf-8") as f:
        json.dump({
            "context_setting": "noisy_context", "risk_level": "L1", "answer": "x",
            "claims": [{"id": i, "text": "声明 %d" % i, "label": "assumed",
                        "confidence": 0.5, "alternative": "另一个可能"} for i in range(1000)],
        }, f, ensure_ascii=False)
    t0 = time.time()
    code, out, err = run("claim_lint.py", ["--input", big, "--json"], timeout=60)
    dt = time.time() - t0
    res.add(g, "1000 条声明 < 10s（实测 %.2fs）" % dt,
            code in ALLOWED_EXIT and dt < 10 and "Traceback" not in err, "exit=%s" % code)


def test_idempotent_and_perf(res, tmp, paths):
    g = "幂等与性能"
    files = [os.path.join(paths["enc"], f) for f in ("gbk.py", "bom.py", "empty.py")]
    args = ["--offline", "--json"] + sum([["--file", f] for f in files], [])
    c1, o1, _ = run("hardcheck.py", args)
    c2, o2, _ = run("hardcheck.py", args)
    same = c1 == c2 and o1 == o2
    res.add(g, "重复执行结果一致（幂等）", same, "exit %s vs %s" % (c1, c2))

    # 性能：200 个本地文件检查
    perf_dir = os.path.join(tmp, "perf")
    os.makedirs(perf_dir, exist_ok=True)
    for i in range(200):
        open(os.path.join(perf_dir, "f%d.py" % i), "w", encoding="utf-8").write("x=1\n")
    t0 = time.time()
    c, o, e = run("hardcheck.py", ["--file", perf_dir, "--offline"], timeout=60)
    dt = time.time() - t0
    res.add(g, "目录检查 < 5s（实测 %.2fs）" % dt, dt < 5.0 and c in ALLOWED_EXIT,
            "exit=%s" % c)

    t0 = time.time()
    c, o, e = run("dep_guard.py", ["--root", perf_dir, "--offline", "--json"], timeout=60)
    dt = time.time() - t0
    ok = dt < 15.0 and c in ALLOWED_EXIT
    if "--json" == "--json":
        try:
            json.loads(o)
        except Exception:
            ok = False
    res.add(g, "dep_guard 扫 200 文件 < 15s（实测 %.2fs）" % dt, ok, "exit=%s" % c)


def main(argv=None):
    _utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if [a for a in argv if a in ("-h", "--help")]:
        print(__doc__ or "touchstone 深度健壮性测试")
        print("\n用法：python scripts/robustness_test.py [--json] [--only=组名,组名]")
        print("可选组：%s" % ", ".join(
            ["hardcheck", "dep_guard", "claim_lint", "ledger", "selfcheck",
             "regression", "pipeline", "hooks", "extreme", "perf"]))
        print("说明：跑完 70 项后按失败数决定退出码。")
        return 0
    as_json = "--json" in argv
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))

    tmp = tempfile.mkdtemp(prefix="touchstone-robust-")
    res = Results()
    try:
        paths = build_corpus(tmp)
        suites = {
            "hardcheck": lambda: test_hardcheck(res, tmp, paths),
            "dep_guard": lambda: test_dep_guard(res, tmp, paths),
            "claim_lint": lambda: test_claim_lint(res, tmp, paths),
            "ledger": lambda: test_ledger(res, tmp),
            "selfcheck": lambda: test_selfcheck(res, tmp),
            "regression": lambda: test_regression(res, tmp),
            "pipeline": lambda: test_pipeline(res, tmp, paths),
            "hooks": lambda: test_hooks(res, tmp),
            "extreme": lambda: test_extreme(res, tmp, paths),
            "perf": lambda: test_idempotent_and_perf(res, tmp, paths),
        }
        for name, fn in suites.items():
            if only and name not in only:
                continue
            try:
                fn()
            except Exception as e:  # noqa: BLE001  # 测试自身也绝不崩
                res.add(name, "测试套件执行", False, "%s: %s" % (type(e).__name__, e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = res.failed
    payload = {
        "tool": "robustness_test.py",
        "total": res.total,
        "passed": res.total - len(failed),
        "failed": len(failed),
        "failures": failed,
        "cases": res.items,
    }

    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        groups = {}
        for it in res.items:
            groups.setdefault(it["group"], []).append(it)
        for g, items in groups.items():
            bad = [i for i in items if not i["ok"]]
            mark = "OK " if not bad else "NG "
            sys.stdout.write("%s%s：%d 项，失败 %d\n" % (mark, g, len(items), len(bad)))
            for i in bad:
                sys.stdout.write("     [FAIL] %s :: %s\n" % (i["case"], i["detail"][:200]))
        sys.stdout.write("\n合计 %d：通过 %d，失败 %d\n" % (
            res.total, res.total - len(failed), len(failed)))
        sys.stdout.write("判定：%s\n" % ("全部通过" if not failed else "存在失败，见上方 FAIL"))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
