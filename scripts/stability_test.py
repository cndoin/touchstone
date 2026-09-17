#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""stability_test.py —— 工程一致性 / 稳定性测试（发版前跑）。

与另外两个测试脚本的分工：

  - selftest.py        = 快速冒烟（38 项，正常路径 + 关键失败路径），秒级
  - robustness_test.py = 深度健壮性（70 项，边界 / 异常 / 编码 / 性能 / 幂等）
  - **stability_test.py = 工程一致性**（编译 / 幂等 / 并发 / fuzz / 环境 /
                         文档与版本一致性 / 资产合法性 / 安装目录同步）

前两个回答"脚本能不能跑对"，这一个回答"整个技能包有没有烂掉"——
比如某个 hook 被改出语法错误、文档里写的版本号和 VERSION 文件不一致、
文档引用的文件其实不存在、工作区改了没同步到安装目录。

核心断言：
  1. 任何 .py 都能编译（防止"改完没跑就发版"）
  2. 同样输入跑 N 次结果完全一致；并发写不产出损坏 JSON
  3. 垃圾输入 / 垃圾 stdin 下不出现 Traceback
  4. 非 UTF-8 环境、离线、只读目录、非 ASCII 路径都不崩
  5. 文档与代码不脱节（版本号、铁律条数、引用的文件路径）
  6. 工作区与安装目录逐字节一致（忘了同步就报警）

用法：
  python scripts/stability_test.py
  python scripts/stability_test.py --json
  python scripts/stability_test.py --no-install-check   # 跳过安装目录比对

环境变量：
  TOUCHSTONE_INSTALLED   安装目录路径；不存在时 G 组自动跳过

退出码：0=全部通过 1=存在失败 3=用法错误
设计：只用标准库，离线可跑；临时文件全部落在系统临时目录。
"""

import filecmp
import glob
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


def _force_utf8():
    """Windows 控制台默认 GBK，直接 print 中文会 UnicodeEncodeError。

    这里独立于 _common 实现一份，避免测试脚本依赖被测代码。
    """
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 允许出现的退出码：0 通过 / 1 存在未验证或失败 / 2 有未验证项 / 3 用法错误
OK_CODES = (0, 1, 2, 3)

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}

results = []
tmp = None


def rec(group, name, ok, detail=""):
    results.append((group, name, bool(ok), detail))
    if not ok:
        sys.stdout.write("FAIL [%s] %s :: %s\n" % (group, name, detail))


def run(args, cwd=None, env=None, timeout=180, stdin_data=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run([PY] + args, cwd=cwd, env=e, input=stdin_data,
                           capture_output=True, timeout=timeout)
        # 故意用 replace：模拟管道里出现非 UTF-8 字节的场景
        return (p.returncode,
                p.stdout.decode("utf-8", "replace"),
                p.stderr.decode("utf-8", "replace"))
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "", ""


def S(*p):
    return os.path.join(HERE, *p)


def section(text, heading_re):
    """截取从 heading_re 匹配到的标题开始、到下一个同级标题为止的正文。"""
    m = re.search(heading_re, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


# ---------------------------------------------------------------------------
# A · 编译与入口
# ---------------------------------------------------------------------------
def group_a():
    pys = sorted(glob.glob(os.path.join(HERE, "*.py")))
    pys += sorted(glob.glob(os.path.join(ROOT, "adapters", "*", "hooks", "*.py")))
    for f in pys:
        if os.path.basename(f) == "stability_test.py":
            continue  # 自身正在运行，编译自己没意义
        try:
            py_compile.compile(f, doraise=True, cfile=os.path.join(tmp, "c.pyc"))
            rec("A", "compile %s" % os.path.basename(f), True)
        except Exception as ex:
            rec("A", "compile %s" % os.path.basename(f), False, str(ex))

    for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        name = os.path.basename(f)
        if name.startswith("_") or name == "stability_test.py":
            continue
        rc, out, err = run([f, "--help"], cwd=ROOT)
        rec("A", "help %s" % name, rc == 0,
            "rc=%s err=%s" % (rc, (err or "")[:120]))


# ---------------------------------------------------------------------------
# B · 幂等与并发
# ---------------------------------------------------------------------------
def group_b(good_claims):
    sigs = set()
    for _ in range(5):
        rc, out, err = run([S("claim_lint.py"), "--input", good_claims,
                            "--min-level", "L1"])
        sigs.add((rc, out.strip()))
    rec("B", "claim_lint 连续 5 次结果完全一致", len(sigs) == 1, "sigs=%d" % len(sigs))

    sigs = set()
    for _ in range(3):
        rc, out, err = run([S("model_profile.py"), "--model", "deepseek-r1",
                            "--net", "on", "--json"])
        try:
            sigs.add(json.dumps(json.loads(out), sort_keys=True, ensure_ascii=False))
        except Exception:
            sigs.add("UNPARSEABLE:" + out[:80])
    rec("B", "model_profile JSON 3 次一致且可解析", len(sigs) == 1,
        "sigs=%d" % len(sigs))

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(run, [S("hardcheck.py"), "--file", S("claim_lint.py"),
                                "--offline"]) for _ in range(16)]
        rcs = [f.result()[0] for f in futs]
    rec("B", "hardcheck 16 次并发全部返回 0", set(rcs) == {0},
        "rcs=%s" % sorted(set(map(str, rcs))))

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(run, [S("claim_lint.py"), "--input", good_claims,
                                "--min-level", "L1"]) for _ in range(16)]
        rcs = [f.result()[0] for f in futs]
    rec("B", "claim_lint 16 次并发全部返回 0", set(rcs) == {0},
        "rcs=%s" % sorted(set(map(str, rcs))))

    # 并发写账本：验证原子写真的原子（不能产出半截 JSON）
    ledger_dir = os.path.join(tmp, "ledger_race")
    os.makedirs(ledger_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(run, [S("ledger.py"), "add", "--kind", "decision",
                                "--subject", "k%d" % i, "--value", "v%d" % i,
                                "--source", "x#1"], cwd=ledger_dir)
                for i in range(16)]
        rcs = [f.result()[0] for f in futs]
    lp = os.path.join(ledger_dir, ".touchstone", "ledger.json")
    ok_json = False
    if os.path.exists(lp):
        try:
            with open(lp, encoding="utf-8") as fh:
                ok_json = isinstance(json.load(fh), (list, dict))
        except Exception:
            ok_json = False
    rec("B", "ledger 并发 16 写后 JSON 仍可解析（原子写）", ok_json,
        "rcs=%s exists=%s" % (sorted(set(map(str, rcs))), os.path.exists(lp)))


# ---------------------------------------------------------------------------
# C · 异常输入 fuzz
# ---------------------------------------------------------------------------
def group_c(good_claims):
    JUNK = [
        ("空文件", b""),
        ("纯空白", b"   \n\t\n"),
        ("非法 JSON", b"{not json"),
        ("JSON 顶层数组", b"[1,2,3]"),
        ("JSON 顶层 null", b"null"),
        ("字段类型错乱", b'{"claims": "not-a-list", "risk_level": 123}'),
        ("超长字符串", b'{"answer": "' + b"A" * 200000 + b'"}'),
        ("Unicode 炸弹", '{"answer": "中文​零宽﻿混排😀́e"}'.encode("utf-8")),
        ("控制字符", b'{"answer": "a\x00b\x01c\x7f"}'),
        ("BOM", b"\xef\xbb\xbf" + b'{"answer":"x"}'),
    ]

    for label, payload in JUNK:
        p = os.path.join(tmp, "junk.json")
        with open(p, "wb") as fh:
            fh.write(payload)
        rc, out, err = run([S("claim_lint.py"), "--input", p, "--min-level", "L1"])
        rec("C", "claim_lint 抗垃圾输入：%s" % label,
            rc in OK_CODES and "Traceback" not in (out + err),
            "rc=%s tb=%s" % (rc, ("Traceback" in (out + err))))

        rc, out, err = run([S("hardcheck.py"), "--claims", p, "--offline"])
        rec("C", "hardcheck 抗垃圾输入：%s" % label,
            "Traceback" not in (out + err), "rc=%s" % rc)

    cases = [
        ("不存在的文件", [S("claim_lint.py"), "--input", os.path.join(tmp, "nope.json")]),
        ("目录当文件", [S("claim_lint.py"), "--input", tmp]),
        ("空 --input", [S("claim_lint.py"), "--input", ""]),
        ("非法 level", [S("claim_lint.py"), "--input", good_claims, "--min-level", "L9"]),
        ("hardcheck 无检查项", [S("hardcheck.py")]),
        ("hardcheck 空 cmd", [S("hardcheck.py"), "--cmd", ""]),
        # 注意：这里用 exit 1 而不是任何破坏性命令 —— 测试脚本绝不能带真危险操作
        ("hardcheck 退出码非 0 的 cmd", [S("hardcheck.py"), "--cmd", "exit 1"]),
        ("model_profile 空 model", [S("model_profile.py"), "--model", ""]),
        ("model_profile 非法档位", [S("model_profile.py"), "--model", "x",
                                    "--override-tier", "Z"]),
        ("ledger 无子命令", [S("ledger.py")]),
        ("regression 不存在用例", [S("regression.py"), "--cases",
                                   os.path.join(tmp, "nope.json")]),
        ("verifiers 未知检测器", [S("verifiers.py"), "--check", "__nope__"]),
    ]
    for label, args in cases:
        rc, out, err = run(args, cwd=ROOT)
        rec("C", "异常参数：%s" % label,
            rc != "TIMEOUT" and "Traceback" not in (out + err),
            "rc=%s tb=%s" % (rc, "Traceback" in (out + err)))

    hooks = sorted(glob.glob(os.path.join(ROOT, "adapters", "*", "hooks", "*.py")))
    for h in hooks:
        for label, data in [("空 stdin", b""), ("非法 JSON", b"{oops"),
                            ("非对象 JSON", b"[1,2]"), ("BOM+JSON", b"\xef\xbb\xbf{}")]:
            # cwd 必须指向 tmp：precompact_snapshot 会往 cwd/.touchstone 写快照，
            # 用默认 cwd 会把测试产物写进用户当前目录（真实踩过）。
            rc, out, err = run([h], stdin_data=data, cwd=tmp)
            rec("C", "hook %s / %s" % (os.path.basename(h), label),
                rc != "TIMEOUT" and "Traceback" not in (out + err),
                "rc=%s tb=%s" % (rc, "Traceback" in (out + err)))


# ---------------------------------------------------------------------------
# D · 环境
# ---------------------------------------------------------------------------
def group_d(good_claims):
    rc, out, err = run([S("model_profile.py"), "--model", "gpt-4o-mini",
                        "--net", "off", "--json"],
                       env={"PYTHONIOENCODING": "gbk"})
    ok = False
    if rc == 0:
        try:
            json.loads(out)
            ok = True
        except Exception as ex:
            out = str(ex) + " head=" + out[:80]
    rec("D", "GBK 输出环境下不崩溃且 stdout 仍是合法 JSON", ok,
        "rc=%s head=%s" % (rc, out[:80]))

    rc, out, err = run([S("claim_lint.py"), "--input", good_claims, "--min-level", "L1"],
                       env={"PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"})
    rec("D", "GBK 环境下 claim_lint 退出码仍为 0", rc == 0,
        "rc=%s err=%s" % (rc, (err or "")[:120]))

    offline_cases = [
        ("hardcheck --offline", [S("hardcheck.py"), "--file", S("claim_lint.py"),
                                 "--offline"]),
        ("dep_guard --offline", [S("dep_guard.py"), "--root", ROOT, "--offline"]),
        ("pipeline 全离线", [S("pipeline.py"), "--root", ROOT,
                             "--checks", os.path.join(ROOT, "assets", "templates",
                                                      "checks-template.json"),
                             "--claims", good_claims, "--level", "L1"]),
    ]
    for label, args in offline_cases:
        rc, out, err = run(args, cwd=ROOT)
        rec("D", "离线可用：%s" % label,
            rc in OK_CODES and "Traceback" not in (out + err), "rc=%s" % rc)

    # 只读目录（Windows 上 chmod 未必生效，生效失败就跳过而不是误报）
    ro_dir = os.path.join(tmp, "readonly")
    os.makedirs(os.path.join(ro_dir, ".touchstone"), exist_ok=True)
    try:
        os.chmod(ro_dir, 0o500)
        rc, out, err = run([S("ledger.py"), "add", "--kind", "decision",
                            "--subject", "x", "--value", "y", "--source", "z#1"],
                           cwd=ro_dir)
        rec("D", "只读目录写入不崩溃（优雅报错）",
            "Traceback" not in (out + err),
            "rc=%s tb=%s" % (rc, "Traceback" in (out + err)))
        os.chmod(ro_dir, 0o700)
    except Exception as ex:
        rec("D", "只读目录写入不崩溃（优雅报错）", True, "skip:%s" % ex)

    uni_dir = os.path.join(tmp, "路径 中文 привет")
    os.makedirs(uni_dir, exist_ok=True)
    rc, out, err = run([S("dep_guard.py"), "--root", uni_dir, "--offline"])
    rec("D", "非 ASCII 项目路径可用", "Traceback" not in (out + err), "rc=%s" % rc)


# ---------------------------------------------------------------------------
# E · 文档 / 版本一致性
# ---------------------------------------------------------------------------
def group_e():
    try:
        version_file = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except Exception as ex:
        rec("E", "VERSION 文件可读", False, str(ex))
        return
    rec("E", "VERSION 文件可读", True)

    try:
        skill_md = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    except Exception as ex:
        rec("E", "SKILL.md 可读", False, str(ex))
        return

    def front_ver(text):
        m = re.search(r"^version:\s*(\S+)\s*$", text, re.M)
        return m.group(1) if m else None

    rec("E", "SKILL.md version == VERSION 文件", front_ver(skill_md) == version_file,
        "%s vs %s" % (front_ver(skill_md), version_file))

    en_path = os.path.join(ROOT, "i18n", "en", "SKILL.md")
    if os.path.exists(en_path):
        en_md = open(en_path, encoding="utf-8").read()
        rec("E", "i18n/en/SKILL.md version == VERSION 文件",
            front_ver(en_md) == version_file,
            "%s vs %s" % (front_ver(en_md), version_file))

    # md 里引用的 references/ scripts/ assets/ examples/ 文件是否真实存在
    missing = []
    for md in glob.glob(os.path.join(ROOT, "**", "*.md"), recursive=True):
        if "_deprecated-v1" in md:
            continue
        try:
            text = open(md, encoding="utf-8").read()
        except Exception:
            continue
        for ref in re.findall(
                r"((?:references|scripts|assets|examples)/"
                r"[A-Za-z0-9_\-./]+\.(?:md|py|json|yml))", text):
            if not os.path.exists(os.path.join(ROOT, ref.replace("/", os.sep))):
                missing.append("%s -> %s" % (os.path.relpath(md, ROOT), ref))
    rec("E", "文档引用的文件全部存在", not missing, "; ".join(missing[:6]))

    # 铁律条数：只数「铁律」小节内部的编号项。
    # 早期版本用全文正则 `^\d+\.\s+\*\*`，会把其它小节的编号加粗行也算进来（数出 14 条）。
    sec = section(skill_md, r"^##\s+铁律[（(]")
    if not sec:
        rec("E", "SKILL.md 存在铁律小节", False, "未找到 `## 铁律（` 标题")
    else:
        rec("E", "SKILL.md 存在铁律小节", True)
        n_rules = len(re.findall(r"^\s*\d+\.\s+\*\*", sec, re.M))
        # 标题形如「## 铁律（九条，不可协商）」—— 只取前头的中文数字，
        # 后面的修饰语（"，不可协商"）不参与解析。
        m = re.search(r"^##\s+铁律[（(]([^）)]+)[）)]", skill_md, re.M)
        declared = m.group(1) if m else ""
        mn = re.match(r"^([一二三四五六七八九十]+)\s*条", declared)
        want = CN_NUM.get(mn.group(1)) if mn else None
        rec("E", "SKILL.md 铁律条数与标题声明一致",
            want is not None and n_rules == want,
            "标题声明 %s，小节内实际 %d 条" % (declared or "无", n_rules))


# ---------------------------------------------------------------------------
# F · 资产合法性
# ---------------------------------------------------------------------------
def group_f():
    bad_json = []
    for jf in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
        try:
            json.load(open(jf, encoding="utf-8"))
        except Exception as ex:
            bad_json.append("%s: %s" % (os.path.relpath(jf, ROOT), ex))
    rec("F", "所有 JSON 资产可解析", not bad_json, "; ".join(bad_json[:4]))

    yml_path = os.path.join(ROOT, "assets", "ci", "github-actions.yml")
    try:
        yml = open(yml_path, encoding="utf-8").read()
        rec("F", "CI yml 非空且含 selfcheck 步骤",
            "selftest.py" in yml and len(yml) > 200)
    except Exception as ex:
        rec("F", "CI yml 非空且含 selfcheck 步骤", False, str(ex))


# ---------------------------------------------------------------------------
# G · 安装目录与工作区同步（可跳过）
# ---------------------------------------------------------------------------
def group_g(installed):
    if not installed or not os.path.isdir(installed):
        sys.stdout.write("SKIP [G] 安装目录检查（未设置或不存在的路径）\n")
        return
    diff = []
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", ".touchstone")]
        rel = os.path.relpath(dirpath, ROOT)
        troo = installed if rel == "." else os.path.join(installed, rel)
        for f in files:
            # 临时文件 / 编辑器产物不参与同步比对
            if f.startswith(".") or f.endswith((".pyc", ".tmp", ".bak")):
                continue
            s, t = os.path.join(dirpath, f), os.path.join(troo, f)
            if not os.path.exists(t) or not filecmp.cmp(s, t, shallow=False):
                diff.append(os.path.join(rel, f))
    rec("G", "安装目录与工作区逐字节一致", not diff, "; ".join(diff[:8]))

    rc, out, err = run([os.path.join(installed, "scripts", "selftest.py")])
    rec("G", "从安装目录跑 selftest 通过", rc == 0, "rc=%s" % rc)


def main(argv=None):
    global tmp
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if [a for a in argv if a in ("-h", "--help")]:
        sys.stdout.write(__doc__ or "stability_test.py")
        return 0
    if [a for a in argv if a not in ("--json", "--no-install-check")]:
        sys.stderr.write("[touchstone] 参数错误：%s\n" % argv)
        return 3
    as_json = "--json" in argv
    no_install = "--no-install-check" in argv

    installed = (os.environ.get("TOUCHSTONE_INSTALLED")
                 or os.environ.get("DEHALLU_INSTALLED")  # v4 改名前的旧名，兼容
                 or os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", "touchstone"))

    tmp = tempfile.mkdtemp(prefix="touchstone-stability-")
    good_claims = os.path.join(ROOT, "examples", "claims-good.json")
    if not os.path.exists(good_claims):
        sys.stderr.write("[touchstone] 缺少样例文件：%s\n" % good_claims)
        shutil.rmtree(tmp, ignore_errors=True)
        return 3

    try:
        group_a()
        group_b(good_claims)
        group_c(good_claims)
        group_d(good_claims)
        group_e()
        group_f()
        if not no_install:
            group_g(installed)
        else:
            sys.stdout.write("SKIP [G] 安装目录检查（--no-install-check）\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    groups = {}
    for g, n, ok, d in results:
        groups.setdefault(g, [0, 0])
        groups[g][0] += 1
        groups[g][1] += 1 if ok else 0

    tot = sum(v[0] for v in groups.values())
    pas = sum(v[1] for v in groups.values())
    failed = [{"group": g, "name": n, "detail": d}
              for g, n, ok, d in results if not ok]

    if as_json:
        sys.stdout.write(json.dumps({
            "tool": "stability_test.py",
            "root": ROOT,
            "total": tot,
            "passed": pas,
            "failed": len(failed),
            "failures": failed,
            "groups": {g: {"total": v[0], "passed": v[1]}
                       for g, v in sorted(groups.items())},
        }, ensure_ascii=False, indent=2) + "\n")
    else:
        for g in sorted(groups):
            sys.stdout.write("%s：%d/%d\n" % (g, groups[g][1], groups[g][0]))
        sys.stdout.write("\n合计 %d：通过 %d，失败 %d\n" % (tot, pas, tot - pas))
        sys.stdout.write("判定：%s\n" % ("全部通过" if pas == tot else "存在失败"))
    return 0 if pas == tot else 1


if __name__ == "__main__":
    sys.exit(main())
