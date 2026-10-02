#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""tool_guard.py —— 工具调用链核查（20-tool-mode 闸门）

它查的不是"这次任务做得对不对"，是**调用链本身的结构一致性** ——
也就是"有没有调到一半忘记前面在干什么"。这类问题的麻烦在于：
结果可能碰巧是对的，但过程已经失控，下次必然翻车，而且翻车时无从复盘。

记录格式见 `assets/tool-trace-schema.json`。

八个检查器（详见 references/20-tool-mode.md 第 7 节）：

  schema     记录结构与枚举值（seq/tool/status 必填，status 枚举）
  order      链的完整性：seq 递增 / 无重复 / 无跳号（跳号 = 有调用没进记录）
  closure    started 没有后续终态（开了头没下文，正是"忘了一半"）
  duplicate  非幂等操作在同一 target 上重复（重复推送 / 重复发送）
  retry      同一失败原样重试超限（没看懂失败原因就盲试）
  prereq     前置依赖缺失：改前未读、发前未存
  plan       目标漂移：goal 或步骤总数中途改变却没声明 rescope
  result     结果误读：status=ok 却 exit_code≠0 或带 error

用法：
  python3 tool_guard.py --file trace.json
  python3 tool_guard.py --file a.json --file b.json --only order,closure
  python3 tool_guard.py --file trace.json --strict --max-retry 2 --json

**边界（不要拿它干别的）：**
  - 不判"调用该不该发生"（那是任务设计问题，人判）
  - 不判"声明有没有证据"（那是 claim_lint.py）
  - 不判"依赖包是真是假"（那是 dep_guard.py）
  - 不判"URL/DOI/文件是否存在"（那是 hardcheck.py）
  它只判：**记录下来的这条链，结构上说不说得通。**

退出码：0=全部通过 1=存在失败 2=存在需人工确认项 3=用法错误
原则：**链不完整时不能给"通过"** —— 证明不了没忘，就不是没忘。
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    ArgParser,
    EXIT_USAGE,
    FAIL,
    PASS,
    UNVERIFIED,
    emit,
    err,
    exit_code_for,
    make_result,
    summarize,
    _force_utf8,
)

# ── 状态 ──────────────────────────────────────────────────────────────
S_OK = "ok"
S_FAIL = "fail"
S_SKIPPED = "skipped"
S_STARTED = "started"
S_ABORTED = "aborted"
STATUSES = (S_OK, S_FAIL, S_SKIPPED, S_STARTED, S_ABORTED)
# started 是唯一非终态：其余四种都代表这次调用已经结束了
TERMINAL = (S_OK, S_FAIL, S_SKIPPED, S_ABORTED)

# ── 工具分类（按小写比对）──────────────────────────────────────────────
# 读类天然幂等：重复调用不产生副作用，不该被 duplicate 拦
READ_TOOLS = frozenset("""
read view get cat list ls grep glob search query find head tail stat diff
check verify show inspect fetch download open
""".split())

# 写/改类：改前必须先读过同一 target，否则是凭印象改。
# 注意：**新建资源不需要先读** —— 由记录显式声明 `creates: true` 免责，
# 与 idempotent / rescope 同一套「举证责任在记录方」的设计。
# 不做「工具名叫 create 就自动放行」：那样 write 既能建新也能覆盖，
# 会同时漏掉「覆盖了旧文件却没读过」这个真问题。
WRITE_TOOLS = frozenset("""
write edit patch update delete remove rename move overwrite create append
set_cell modify mutate
""".split())

# 对外动作类：发前必须有落盘动作，否则推出去的不是你以为的东西
PUBLISH_TOOLS = frozenset("""
push publish release submit send deploy upload post email merge
publish_site deploy_site
""".split())

# 落盘类：能作为"发前已存"的前置
SAVE_TOOLS = frozenset("commit save write stash snapshot".split())

RE_STEP = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def _low(v):
    return (v or "").strip().lower()


def _args_key(v):
    """把 args 归一成字符串，用于判断'是不是换了策略再试'。"""
    if v is None:
        return ""
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return repr(v)


def _label(path, rec, idx):
    """给一条记录一个可定位的名字：文件#序号。"""
    seq = rec.get("seq")
    tag = ("seq=%s" % seq) if isinstance(seq, int) else ("idx=%d" % idx)
    return "%s#%s" % (path, tag)


def load_trace(path):
    """读入一份调用链记录。

    支持两种形态：整个文件是 JSON（对象带 trace 字段 / 直接是数组），
    或 JSONL（每行一个对象）—— 调用链常是边跑边追加的，JSONL 更顺手。

    返回 (records, meta, error)：解析不了时 error 非空，records 为 None。
    **不抛异常**：闸门不能因为输入难看就崩。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as ex:  # noqa: BLE001
        return None, {}, "读不到文件：%s: %s" % (type(ex).__name__, ex)
    try:
        text = raw.decode("utf-8-sig")
    except Exception:  # noqa: BLE001
        text = raw.decode("utf-8", "replace")

    if not text.strip():
        return None, {}, "文件为空"

    # 1) 整体 JSON
    try:
        doc = json.loads(text)
    except Exception:  # noqa: BLE001
        doc = None

    if isinstance(doc, dict) and isinstance(doc.get("trace"), list):
        meta = dict(doc)
        meta.pop("trace", None)
        return doc["trace"], meta, ""
    if isinstance(doc, list):
        return doc, {}, ""

    # 2) JSONL
    recs = []
    for ln, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("#"):
            continue
        try:
            recs.append(json.loads(s))
        except Exception as ex:  # noqa: BLE001
            return None, {}, "第 %d 行不是合法 JSON：%s" % (ln, ex)
    if not recs:
        return None, {}, "既不是 JSON（带 trace 数组）也不是 JSONL，一行记录都没解析出来"
    return recs, {}, ""


# ── 八个检查器 ─────────────────────────────────────────────────────────
# 每个签名：check_xxx(recs, path, cfg) -> [result, ...]
# 任何异常由调用方统一转成 UNVERIFIED，绝不当通过。

def check_schema(recs, path, cfg):
    """记录结构与枚举值。这条不过，后面七条的结论都不可信。"""
    out = []
    for i, r in enumerate(recs):
        lab = _label(path, r, i) if isinstance(r, dict) else "%s#idx=%d" % (path, i)
        if not isinstance(r, dict):
            out.append(make_result("schema", lab, FAIL,
                                   "记录不是对象", repr(r)[:120]))
            continue
        bad = []
        seq = r.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            bad.append("seq 必须是 >=1 的整数")
        tool = r.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            bad.append("tool 必须是非空字符串")
        st = r.get("status")
        if st not in STATUSES:
            bad.append("status 必须是 %s 之一，实得 %r" % ("/".join(STATUSES), st))
        if "consumes" in r:
            cs = r.get("consumes")
            if not isinstance(cs, list) or any(
                    not isinstance(x, int) or isinstance(x, bool) for x in cs):
                bad.append("consumes 必须是整数数组")
        if "exit_code" in r and r.get("exit_code") is not None:
            ec = r.get("exit_code")
            if not isinstance(ec, int) or isinstance(ec, bool):
                bad.append("exit_code 必须是整数或 null")
        if "step" in r and r.get("step") is not None:
            if not isinstance(r.get("step"), str):
                bad.append("step 必须是字符串或 null")
        if bad:
            out.append(make_result("schema", lab, FAIL, "；".join(bad),
                                   json.dumps(r, ensure_ascii=False)[:200]))
    return out


def check_order(recs, path, cfg):
    """链的完整性：seq 递增 / 无重复 / 无跳号。

    跳号不是小事：**记录不全 = 无法证明"没忘记前面"**。
    片段记录（meta.partial=true）降级为 unverified，但完整记录必须连续。
    """
    out = []
    partial = bool(cfg.get("partial"))
    weak = UNVERIFIED if partial else FAIL
    seqs = []
    for i, r in enumerate(recs):
        if isinstance(r, dict) and isinstance(r.get("seq"), int) \
                and not isinstance(r.get("seq"), bool):
            seqs.append((r["seq"], i))

    seen = {}
    for seq, i in seqs:
        if seq in seen:
            out.append(make_result("order", _label(path, recs[i], i), FAIL,
                                   "seq=%d 重复出现（第 %d 条），链的先后关系无法确定"
                                   % (seq, seen[seq] + 1), "seq=%d" % seq))
        else:
            seen[seq] = i

    for (a, ia), (b, ib) in zip(seqs, seqs[1:]):
        if b <= a:
            out.append(make_result("order", _label(path, recs[ib], ib), weak,
                                   "seq 没有递增：%d 出现在 %d 之后" % (b, a),
                                   "seq=%d -> seq=%d" % (a, b)))

    if seqs:
        lo, hi = min(s for s, _ in seqs), max(s for s, _ in seqs)
        missing = sorted(set(range(lo, hi + 1)) - {s for s, _ in seqs})
        if missing:
            out.append(make_result("order", path, weak,
                                   "seq 有跳号，缺 %s —— 这些调用没进记录，"
                                   "链从这里就断了" % _brief_ints(missing),
                                   "missing=%s" % _brief_ints(missing)))
        if lo != 1 and not partial:
            out.append(make_result("order", path, weak,
                                   "seq 从 %d 开始而不是 1，前面的调用没进记录" % lo,
                                   "first_seq=%d" % lo))
    return out


def _brief_ints(nums, cap=8):
    if len(nums) <= cap:
        return ",".join(str(x) for x in nums)
    return "%s,…共 %d 个" % (",".join(str(x) for x in nums[:cap]), len(nums))


def check_closure(recs, path, cfg):
    """started 之后必须有同一 target 的终态 —— 开了头没下文。"""
    out = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict) or r.get("status") != S_STARTED:
            continue
        tgt = _low(r.get("target"))
        tool = _low(r.get("tool"))
        closed = False
        for j in range(i + 1, len(recs)):
            o = recs[j]
            if not isinstance(o, dict) or o.get("status") not in TERMINAL:
                continue
            same = _low(o.get("target")) == tgt if tgt else _low(o.get("tool")) == tool
            if same:
                closed = True
                break
        if not closed:
            out.append(make_result(
                "closure", _label(path, r, i), FAIL,
                "status=started 之后没有终态记录 —— 这次调用开了头就没下文，"
                "正是「调到一半忘了」的典型症状",
                "tool=%s target=%s" % (r.get("tool"), r.get("target"))))
    return out


def check_duplicate(recs, path, cfg):
    """非幂等操作在同一 target 上重复。读类天然放行；其余要显式声明幂等。

    **只算 status=ok 的调用**：失败的调用没产生副作用，重复它是 retry
    检查器的事；在这里也报一遍就成了同一件事报两次，排障的人会以为
    有两处独立的问题。
    """
    out = []
    groups = {}
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        tool = _low(r.get("tool"))
        if not tool:
            continue
        if r.get("status") != S_OK:
            continue
        key = (tool, _low(r.get("target")))
        groups.setdefault(key, []).append(i)

    for (tool, tgt), idxs in groups.items():
        if len(idxs) < 2:
            continue
        if tool in READ_TOOLS:
            continue
        # 每条重复都要自己免责：显式声明幂等，或写明是对某条失败调用的重试
        for k in idxs[1:]:
            r = recs[k]
            if r.get("idempotent") is True:
                continue
            ro = r.get("retry_of")
            # retry_of 指向的那条要是 fail —— 失败后补一次是补救，不是重复副作用。
            # 注意要在**全部记录**里找它：分组里只剩 ok 的调用了。
            if isinstance(ro, int) and any(
                    isinstance(p, dict) and p.get("seq") == ro
                    and p.get("status") == S_FAIL for p in recs):
                continue
            out.append(make_result(
                "duplicate", _label(path, r, k), FAIL,
                "非幂等工具 %s 在同一 target 上重复出现（共 %d 次）——"
                "重复推送/发送/删除是真实事故；若确实是幂等重放，"
                "请在记录里写 idempotent:true" % (r.get("tool"), len(idxs)),
                "tool=%s target=%s" % (tool, tgt)))
    return out


def check_retry(recs, path, cfg):
    """同一失败原样重试超限：args 一字未改，说明没看懂失败原因。"""
    out = []
    limit = int(cfg.get("max_retry") or 3)
    run_key, run_start, run_len = None, -1, 0

    def flush(end_i):
        if run_len >= limit and run_key is not None:
            out.append(make_result(
                "retry", _label(path, recs[end_i], end_i), FAIL,
                "同一调用原样失败 %d 次仍未换策略（阈值 %d）——"
                "参数一字未改的重试只是在撞墙，不是在解决"
                % (run_len, limit),
                "key=%s|%s" % (run_key[0], run_key[1])))

    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            run_key, run_len = None, 0
            continue
        if r.get("status") != S_FAIL:
            flush(i - 1)
            run_key, run_start, run_len = None, -1, 0
            continue
        key = (_low(r.get("tool")), _low(r.get("target")), _args_key(r.get("args")))
        if key == run_key:
            run_len += 1
        else:
            flush(i - 1)
            run_key, run_start, run_len = key, i, 1
    flush(len(recs) - 1)
    return out


def check_prereq(recs, path, cfg):
    """改前必须读过、发前必须存过。

    这两条是"凭印象动手"的直接证据：没读就改 = 改的是记忆里的文件，
    没存就发 = 推出去的不是你以为的那份。
    """
    out = []
    seen_read = set()
    seen_save = False
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        tool = _low(r.get("tool"))
        tgt = _low(r.get("target"))
        if tool in WRITE_TOOLS and tgt and tgt not in seen_read \
                and r.get("creates") is not True:
            out.append(make_result(
                "prereq", _label(path, r, i), FAIL,
                "改前未读：%s 直接修改 %s，在此之前没有任何针对它的读取 —— "
                "改的是记忆里的内容而不是磁盘上的内容"
                "（若这是新建资源，请在记录里写 creates:true）"
                % (r.get("tool"), r.get("target")),
                "tool=%s target=%s" % (tool, tgt)))
        if tool in PUBLISH_TOOLS and not seen_save:
            out.append(make_result(
                "prereq", _label(path, r, i), FAIL,
                "发前未存：%s 之前没有任何落盘动作（commit/save/write）—— "
                "推出去的未必是刚改完的那份" % r.get("tool"),
                "tool=%s" % tool))
        if tool in READ_TOOLS:
            seen_read.add(tgt)
        if tool in SAVE_TOOLS or tool in WRITE_TOOLS:
            seen_save = True
    return out


def check_plan(recs, path, cfg):
    """目标漂移：goal 或步骤总数中途改变却没声明 rescope。"""
    out = []
    prev_goal, prev_total = None, None
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        rescope = r.get("rescope") is True
        g = r.get("goal")
        if isinstance(g, str) and g.strip():
            g = g.strip()
            if prev_goal is not None and g != prev_goal and not rescope:
                out.append(make_result(
                    "plan", _label(path, r, i), FAIL,
                    "目标中途变了（%s → %s）却没声明 rescope —— "
                    "换目标本身可以，但换了不说是「忘了原来在干什么」的典型表现"
                    % (prev_goal[:40], g[:40]),
                    "goal=%s" % g[:80]))
            # 声明过 rescope 之后，新目标就是新基准。不这么定的话，
            # 一次换目标之后每条记录都得再声明一遍 rescope 才算过 ——
            # 那是逼着记录造假，不是防"忘了"。
            prev_goal = g
        st = r.get("step")
        if isinstance(st, str):
            m = RE_STEP.match(st)
            if m:
                total = int(m.group(2))
                if prev_total is not None and total != prev_total and not rescope:
                    out.append(make_result(
                        "plan", _label(path, r, i), FAIL,
                        "计划总步数中途变了（%d → %d）却没声明 rescope —— "
                        "计划被悄悄改写，最后的「全部完成」就无法核对"
                        % (prev_total, total),
                        "step=%s" % st))
                # 同 goal：rescope 之后新总步数就是新基准
                prev_total = total
    return out


def check_result(recs, path, cfg):
    """结果误读：工具的返回被读成它没说的意思。"""
    out = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        st = r.get("status")
        ec = r.get("exit_code")
        err_txt = r.get("error")
        lab = _label(path, r, i)
        if st == S_OK and isinstance(ec, int) and not isinstance(ec, bool) and ec != 0:
            out.append(make_result(
                "result", lab, FAIL,
                "status=ok 但 exit_code=%d —— 工具报了失败却被记成成功，"
                "这是「工具成功 ≠ 做对了」最直接的形态" % ec,
                "exit_code=%d" % ec))
        if st == S_OK and isinstance(err_txt, str) and err_txt.strip():
            out.append(make_result(
                "result", lab, FAIL,
                "status=ok 却带着 error 字段 —— 成功的调用不该有错误信息",
                "error=%s" % err_txt.strip()[:120]))
        if st == S_FAIL and not (isinstance(err_txt, str) and err_txt.strip()) \
                and ec is None:
            out.append(make_result(
                "result", lab, UNVERIFIED,
                "status=fail 但既没写 error 也没写 exit_code —— "
                "失败原因没记录，下次只能盲试（这本身就是重试失控的源头）",
                "tool=%s" % r.get("tool")))
    return out


CHECKS = [
    ("schema", check_schema, "记录结构与枚举值"),
    ("order", check_order, "链的完整性：seq 递增 / 无重复 / 无跳号"),
    ("closure", check_closure, "started 没有后续终态"),
    ("duplicate", check_duplicate, "非幂等操作在同一 target 上重复"),
    ("retry", check_retry, "同一失败原样重试超限"),
    ("prereq", check_prereq, "前置依赖缺失：改前未读 / 发前未存"),
    ("plan", check_plan, "目标漂移：goal 或步骤总数中途改变"),
    ("result", check_result, "结果误读：ok 却 exit_code≠0 或带 error"),
]
CHECK_NAMES = [n for n, _f, _d in CHECKS]
CHECK_DESC = {n: d for n, _f, d in CHECKS}


def stats_of(recs):
    tools = {}
    sts = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        t = _low(r.get("tool")) or "(空)"
        tools[t] = tools.get(t, 0) + 1
        s = r.get("status")
        sts[s] = sts.get(s, 0) + 1
    return {
        "records": len(recs),
        "tools": tools,
        "statuses": sts,
    }


def main(argv=None):
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = ArgParser(
        prog="tool_guard.py",
        description="工具调用链核查（顺序 / 闭环 / 幂等 / 前置 / 目标漂移 / 结果误读）",
    )
    parser.add_argument("--file", action="append", default=[],
                        metavar="TRACE",
                        help="调用链记录文件（可重复）。JSON（带 trace 数组）或 JSONL")
    parser.add_argument("--only", help="只跑指定检查器，逗号分隔：" + ",".join(CHECK_NAMES))
    parser.add_argument("--max-retry", type=int, default=3, metavar="N",
                        help="retry 检查器的连续失败阈值（默认 3）")
    parser.add_argument("--offline", action="store_true", help="本闸门全程离线，此参数仅为兼容流水线")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：需人工确认项也按失败计")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    only = None
    if args.only:
        only = [x.strip() for x in args.only.split(",") if x.strip()]
        bad = [x for x in only if x not in CHECK_NAMES]
        if bad:
            err("未知检查器：%s；可用：%s" % (", ".join(bad), ", ".join(CHECK_NAMES)))
            return EXIT_USAGE
    if args.max_retry < 1:
        err("--max-retry 必须 >=1")
        return EXIT_USAGE

    if not args.file:
        err("没有待检查目标：至少给一份 --file 调用链记录")
        return EXIT_USAGE
    for f in args.file:
        if not os.path.isfile(f):
            err("文件不存在：%s" % f)
            return EXIT_USAGE

    results = []
    all_stats = {}
    for path in args.file:
        recs, meta, load_err = load_trace(path)
        if recs is None:
            # 记录本身读不出来 → 链无法核对。这是失败，不是"没查过"：
            # 一份坏掉的记录等于一份不完整的链。
            results.append(make_result("schema", path, FAIL,
                                       "调用链记录无法解析：" + load_err))
            continue
        all_stats[path] = stats_of(recs)
        cfg = {
            "strict": args.strict,
            "offline": args.offline,
            "max_retry": args.max_retry,
            "partial": bool(meta.get("partial")),
        }
        n_rec = len(recs)
        for name, fn, _desc in CHECKS:
            if only and name not in only:
                continue
            try:
                found = fn(recs, path, cfg) or []
                results.extend(found)
                if not found:
                    # 检查器没发现异常也要出一条 PASS —— 只报坏消息会让
                    # 干净的链显示「合计 0」，而「没把话说完」本身就是假信号
                    # （见 oss-readiness-audit 的教训）。每文件 × 每检查器
                    # 各算一条，合计数因此可核对。
                    results.append(make_result(
                        name, path, PASS,
                        "未发现异常（%d 条调用）" % n_rec))
            except Exception as e:  # noqa: BLE001
                # 检查器自身出错 → 记为未验证（fail-closed），绝不当通过
                results.append(make_result(name, path, UNVERIFIED,
                                           "检查器异常：%s: %s" % (type(e).__name__, e)))

    if args.strict:
        for r in results:
            if r.get("status") == UNVERIFIED:
                r["status"] = FAIL

    summary = summarize(results)
    code = exit_code_for(results)
    payload = {
        "tool": "tool_guard",
        "files": list(args.file),
        "results": results,
        "summary": summary,
        "stats": all_stats,
        "exit_code": code,
    }
    human = []
    for r in results:
        human.append("%s [%s] %s :: %s" % (
            _sym(r.get("status")), r.get("kind"), r.get("target"), r.get("detail")))
    human.append("合计 %d：pass=%d fail=%d unverified=%d"
                 % (summary["total"], summary["pass"],
                    summary["fail"], summary["unverified"]))
    emit(payload, as_json=args.json, human_lines=human)
    return code


def _sym(status):
    return {PASS: "PASS", FAIL: "FAIL", UNVERIFIED: "UNVERIFIED"}.get(status, "?")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        err("tool_guard 崩溃（这是 bug，请上报）：%s: %s" % (type(e).__name__, e))
        sys.exit(2)
