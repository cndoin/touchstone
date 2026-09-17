#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""hardcheck.py —— 可判定项硬核查（M3）

把「这个 URL 存不存在」「这个文件在不在」「这条命令跑出来是什么」
从"凭印象"变成"实际执行"。这是整套流程里性价比最高的一步。

v3 稳定性与效率增强：
  - 缓存：同一 URL/DOI/包版本默认缓存 6 小时（TOUCHSTONE_CACHE_DIR 可改位置）
  - 并发：网络项默认 4 并发（--jobs），受限环境自动退化为串行
  - 重试：疑似瞬时故障重试 1 次（--retries）
  - 预算：--max-checks 防止一次性核查失控
  - 原子写：--json-out 先写 .tmp 再 replace，不会留下半截文件

用法示例：
  python hardcheck.py --url https://example.com
  python hardcheck.py --doi 10.1038/s41586-024-07500-0
  python hardcheck.py --file ./src/Main.kt
  python hardcheck.py --cmd "git status --porcelain"
  python hardcheck.py --pypi requests 2.30.0
  python hardcheck.py --npm react 18.3.1
  python hardcheck.py --batch checks.json --json-out result.json --json
  python hardcheck.py --batch checks.json --offline --jobs 8 --max-checks 200

退出码：0=全部通过 1=存在失败 2=存在未验证(网络失败等) 3=用法错误
原则：查不到 = 不成立（fail）；工具/网络出错 = 未验证（unverified），绝不默认通过。
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    ArgParser,  # noqa: E402
    DEFAULT_UA,
    FAIL,
    PASS,
    UNVERIFIED,
    atomic_write_json,
    cache_get,
    cache_set,
    default_cache_dir,
    emit,
    err,
    exit_code_for,
    load_json_file,
    load_json_object,
    make_result,
    map_parallel,
    run_with_retry,
    status_symbol,
    summarize,
)
from _common import EXIT_USAGE  # noqa: E402

DEFAULT_TIMEOUT = 8.0
DEFAULT_JOBS = 4


def http_check(url, timeout=DEFAULT_TIMEOUT, method="HEAD", accept=None):
    """轻量 HTTP 检查。返回 (status, detail, evidence)。

    失败一律 UNVERIFIED —— 网络不通不是"这条声明成立"的证据。
    """
    headers = {"User-Agent": DEFAULT_UA}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return PASS, "HTTP %s" % resp.status, url
    except urllib.error.HTTPError as e:
        if method == "HEAD" and e.code in (403, 405, 501):
            # 很多站点不接受 HEAD，退回 GET
            return http_check(url, timeout=timeout, method="GET", accept=accept)
        return FAIL, "HTTP %s" % e.code, url
    except Exception as e:  # 超时 / DNS / SSL / 断网
        return UNVERIFIED, "%s: %s" % (type(e).__name__, e), url


def _net(kind, target, fn, cfg):
    """网络检查统一外壳：缓存 → 重试 → 存缓存；异常降级为 UNVERIFIED。"""
    cache_dir = cfg.get("cache_dir")
    key = "%s|%s" % (kind, target)
    hit = cache_get(cache_dir, kind, key)
    if hit is not None:
        r = dict(hit)
        r["detail"] = str(r.get("detail", "")) + " [缓存]"
        return r
    try:
        result = run_with_retry(fn, retries=cfg.get("retries", 1))
    except Exception as e:  # noqa: BLE001
        result = make_result(kind, target, UNVERIFIED, "%s: %s" % (type(e).__name__, e))
    cache_set(cache_dir, kind, key, result)
    return result


def check_url(target, cfg):
    if cfg.get("offline"):
        return make_result("url", target, UNVERIFIED, "--offline 已跳过网络检查")
    timeout = cfg.get("timeout", DEFAULT_TIMEOUT)

    def fn():
        status, detail, ev = http_check(target, timeout=timeout)
        return make_result("url", target, status, detail, ev)

    return _net("url", target, fn, cfg)


def check_doi(doi, cfg):
    if cfg.get("offline"):
        return make_result("doi", doi, UNVERIFIED, "--offline 已跳过网络检查")
    timeout = cfg.get("timeout", DEFAULT_TIMEOUT)
    api = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    headers = {"User-Agent": DEFAULT_UA}

    def fn():
        req = urllib.request.Request(api, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return make_result("doi", doi, FAIL, "Crossref 404：DOI 不存在", api)
            return make_result("doi", doi, UNVERIFIED, "HTTP %s" % e.code, api)
        except Exception as e:  # noqa: BLE001
            return make_result("doi", doi, UNVERIFIED, "%s: %s" % (type(e).__name__, e), api)
        item = data.get("message", {})
        title = (item.get("title") or [""])[0]
        if not title:
            return make_result("doi", doi, UNVERIFIED, "Crossref 返回但无标题", api)
        return make_result("doi", doi, PASS, "已解析：%s" % title, api)

    return _net("doi", doi, fn, cfg)


def check_file(path):
    try:
        exists = os.path.exists(path)
    except Exception as e:  # noqa: BLE001
        return make_result("file", path, UNVERIFIED, "%s: %s" % (type(e).__name__, e))
    if exists:
        kind = "目录" if os.path.isdir(path) else "文件"
        size = ""
        try:
            size = "，%d bytes" % os.path.getsize(path)
        except OSError:
            pass
        return make_result("file", path, PASS, "%s存在%s" % (kind, size))
    return make_result("file", path, FAIL, "路径不存在")


def check_command(cmd, cfg):
    timeout = cfg.get("timeout", DEFAULT_TIMEOUT)
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return make_result("cmd", cmd, UNVERIFIED, "执行超时（>%ss）" % timeout)
    except Exception as e:  # noqa: BLE001
        return make_result("cmd", cmd, UNVERIFIED, "%s: %s" % (type(e).__name__, e))
    out = (proc.stdout or "") + (proc.stderr or "")
    snippet = out.strip().replace("\n", " | ")[:400]
    status = PASS if proc.returncode == 0 else FAIL
    return make_result(
        "cmd", cmd, status,
        "exit=%d | %s" % (proc.returncode, snippet or "(无输出)"), out[:4000],
    )


def check_pypi(spec, cfg):
    name = spec.get("name")
    version = spec.get("version")
    target = "%s==%s" % (name, version) if version else name
    if cfg.get("offline"):
        return make_result("pypi", target, UNVERIFIED, "--offline 已跳过网络检查")
    timeout = cfg.get("timeout", DEFAULT_TIMEOUT)
    url = ("https://pypi.org/pypi/%s/%s/json" % (name, version)) if version \
        else ("https://pypi.org/pypi/%s/json" % (name))

    def fn():
        status, _d, ev = http_check(url, timeout=timeout, method="GET")
        if status == UNVERIFIED:
            return make_result("pypi", target, UNVERIFIED, "网络不可用", ev)
        return make_result("pypi", target, PASS if status == PASS else FAIL,
                           "PyPI 上存在" if status == PASS else "PyPI 上不存在该版本", ev)

    return _net("pypi", target, fn, cfg)


def check_npm(spec, cfg):
    name = spec.get("name")
    version = spec.get("version")
    target = "%s@%s" % (name, version) if version else name
    if cfg.get("offline"):
        return make_result("npm", target, UNVERIFIED, "--offline 已跳过网络检查")
    timeout = cfg.get("timeout", DEFAULT_TIMEOUT)
    url = ("https://registry.npmjs.org/%s/%s" % (name, version)) if version \
        else ("https://registry.npmjs.org/%s" % (name))

    def fn():
        status, _d, ev = http_check(url, timeout=timeout, method="GET")
        if status == UNVERIFIED:
            return make_result("npm", target, UNVERIFIED, "网络不可用", ev)
        return make_result("npm", target, PASS if status == PASS else FAIL,
                           "npm registry 上存在" if status == PASS
                           else "npm registry 上不存在该版本", ev)

    return _net("npm", target, fn, cfg)


def run_checks(cfg):
    """网络项并发（无副作用），文件/命令串行（有副作用，且顺序可预测）。"""
    results = []
    jobs = cfg.get("jobs", 1)
    limit = cfg.get("max_checks")

    def take(items):
        if not limit:
            return list(items)
        remain = max(0, limit - len(results))
        return list(items)[:remain]

    groups = [
        ("urls", lambda t: check_url(t, cfg), True),
        ("dois", lambda d: check_doi(d, cfg), True),
        ("pypi", lambda p: check_pypi(p, cfg), True),
        ("npm", lambda n: check_npm(n, cfg), True),
        ("files", lambda f: check_file(f), False),
        ("commands", lambda c: check_command(c, cfg), False),
    ]
    for group, fn, parallel in groups:
        items = take(cfg.get(group) or [])
        if not items:
            continue
        if parallel and len(items) > 1:
            results.extend(map_parallel(fn, items, jobs=jobs))
        else:
            results.extend([fn(x) for x in items])

    if limit and len(results) >= limit:
        results.append(make_result("budget", "max_checks=%d" % limit, UNVERIFIED,
                                   "预算耗尽，剩余检查项未执行"))
        err("达到 --max-checks=%d 上限，剩余项未核查（记为未验证，不是通过）" % limit)
    return results


def build_parser():
    p = ArgParser(
        prog="hardcheck.py",
        description="可判定项硬核查：URL / DOI / 文件 / 命令 / 包版本。fail-closed。",
    )
    p.add_argument("--url", action="append", default=[], help="要检查的 URL（可重复）")
    p.add_argument("--doi", action="append", default=[], help="要检查的 DOI（可重复）")
    p.add_argument("--file", action="append", default=[], help="要检查的文件/目录路径（可重复）")
    p.add_argument("--cmd", action="append", default=[], help="要实际执行的命令（可重复）")
    p.add_argument("--pypi", nargs=2, action="append", default=[], metavar=("NAME", "VERSION"),
                   help="PyPI 包与版本是否存在")
    p.add_argument("--npm", nargs=2, action="append", default=[], metavar=("NAME", "VERSION"),
                   help="npm 包与版本是否存在")
    p.add_argument("--batch", help="批量检查 JSON 文件路径")
    p.add_argument("--json-out", help="结果写入该 JSON 文件（原子写）")
    p.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p.add_argument("--offline", action="store_true", help="跳过所有网络检查（CI/无网环境）")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单项超时秒数（默认 8）")
    p.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="网络检查并发数（默认 4，1=串行）")
    p.add_argument("--retries", type=int, default=1, help="疑似瞬时故障重试次数（默认 1）")
    p.add_argument("--cache-dir", default=None, help="缓存目录（默认系统临时目录下）")
    p.add_argument("--no-cache", action="store_true", help="关闭缓存")
    p.add_argument("--max-checks", type=int, default=0, help="单次最多核查项数（0=不限）")
    return p


def main(argv=None):
    from _common import _force_utf8
    _force_utf8()

    args = build_parser().parse_args(argv)

    cfg = {
        "urls": list(args.url),
        "dois": list(args.doi),
        "files": list(args.file),
        "commands": list(args.cmd),
        "pypi": [{"name": a, "version": b} for a, b in args.pypi],
        "npm": [{"name": a, "version": b} for a, b in args.npm],
    }

    if args.batch:
        batch = load_json_object(args.batch, "批量检查配置")
        if not isinstance(batch, dict):
            err("批量配置文件必须是 JSON 对象")
            return EXIT_USAGE
        for key in ("urls", "dois", "files", "commands"):
            cfg[key].extend(batch.get(key) or [])
        for key in ("pypi", "npm"):
            for item in batch.get(key) or []:
                if isinstance(item, str):
                    cfg[key].append({"name": item, "version": None})
                elif isinstance(item, dict) and item.get("name"):
                    cfg[key].append(item)

    if not any(cfg.values()):
        err("没有指定任何检查项。用法见 --help（例：--file ./README.md --cmd \"git status\"）")
        return EXIT_USAGE

    cfg.update({
        "offline": args.offline,
        "timeout": args.timeout,
        "jobs": args.jobs,
        "retries": args.retries,
        "cache_dir": None if (args.no_cache or args.offline)
                     else (args.cache_dir or default_cache_dir()),
        "max_checks": args.max_checks,
    })

    results = run_checks(cfg)
    summary = summarize(results)

    payload = {
        "tool": "hardcheck.py",
        "offline": args.offline,
        "timeout": args.timeout,
        "jobs": args.jobs,
        "cache": bool(cfg["cache_dir"]),
        "results": results,
        "summary": summary,
        "hint": "FAIL 项对应的声明必须删除或降级；UNVERIFIED 不等于通过。",
    }

    if args.json_out:
        atomic_write_json(args.json_out, payload)

    if args.json:
        emit(payload, as_json=True)
    else:
        lines = []
        for r in results:
            lines.append("%s %s %s :: %s" % (
                status_symbol(r["status"]), r["kind"], r["target"], r["detail"]))
        lines.append("")
        lines.append("合计 %d：pass=%d fail=%d unverified=%d" % (
            summary["total"], summary["pass"], summary["fail"], summary["unverified"]))
        if summary["fail"]:
            lines.append(">>> 存在失败项：相关声明必须删除或降级，不许交付。")
        elif summary["unverified"]:
            lines.append(">>> 存在未验证项：记为 unverified，不许默认通过。")
        emit(None, as_json=False, human_lines=lines)

    return exit_code_for(results)


if __name__ == "__main__":
    sys.exit(main())
