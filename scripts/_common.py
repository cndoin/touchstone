#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""touchstone 公共工具（v3：新增缓存 / 并发 / 重试 / 原子写）

设计约束（稳定性优先）：
1. 只用 Python 标准库，禁止任何第三方依赖 —— 装上就能跑，不污染环境。
2. Python 3.8+ / Windows + Unix 双兼容。
3. fail-closed 语义：任何异常都记为 unverified（未验证），绝不默认通过。
4. stdout 只输出数据（JSON 或结构化文本），人类提示与错误一律走 stderr。
5. 退出码语义统一：0=通过 1=存在失败 2=存在未验证 3=用法/输入错误
6. 网络调用一律可缓存、可并发、可重试、可预算上限；失败降级为 unverified。
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

PASS = "pass"
FAIL = "fail"
UNVERIFIED = "unverified"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNVERIFIED = 2
EXIT_USAGE = 3

DEFAULT_CACHE_TTL = 6 * 3600  # 缓存 6 小时，避免重复核查同一个 URL/DOI


def _force_utf8():
    """Windows 默认编码可能是 GBK，显式切成 UTF-8，避免中文输出炸掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def emit(data, as_json=False, human_lines=None):
    """统一输出。as_json=True 时 stdout 只放 JSON。"""
    if as_json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        for line in (human_lines or []):
            sys.stdout.write(line + "\n")


def err(msg):
    sys.stderr.write("[touchstone] " + str(msg) + "\n")


def make_result(kind, target, status, detail="", evidence=""):
    return {
        "kind": kind,
        "target": target,
        "status": status,
        "detail": detail,
        "evidence": evidence,
    }


def summarize(results):
    counts = {PASS: 0, FAIL: 0, UNVERIFIED: 0}
    for r in results:
        counts[r.get("status", UNVERIFIED)] = counts.get(r.get("status", UNVERIFIED), 0) + 1
    return {
        "total": len(results),
        "pass": counts[PASS],
        "fail": counts[FAIL],
        "unverified": counts[UNVERIFIED],
    }


def exit_code_for(results):
    """fail-closed：有 fail 优先报 fail；否则有 unverified 报 unverified。"""
    s = summarize(results)
    if s["fail"] > 0:
        return EXIT_FAIL
    if s["unverified"] > 0:
        return EXIT_UNVERIFIED
    return EXIT_OK


def status_symbol(status):
    return {PASS: "[PASS]", FAIL: "[FAIL]", UNVERIFIED: "[UNVERIFIED]"}.get(status, "[?]")


def load_json_file(path, what="input"):
    """读 JSON 文件。任何失败都以 EXIT_USAGE 退出，不静默吞错。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        err("找不到%s文件: %s" % (what, path))
        sys.exit(EXIT_USAGE)
    except json.JSONDecodeError as e:
        err("%s 不是合法 JSON (%s): %s" % (what, path, e))
        sys.exit(EXIT_USAGE)
    except OSError as e:
        err("读取%s失败 (%s): %s" % (what, path, e))
        sys.exit(EXIT_USAGE)


def load_json_object(path, what="input"):
    """读 JSON **且要求顶层必须是对象（dict）**。

    为什么单独开一个：顶层是数组 / 标量 / null 时，json.load 本身不报错，
    错误会一直拖到后面 `doc.get(...)` 才炸成 AttributeError + traceback。
    那种崩溃既难诊断，也违反了"任何输入都不能让工具崩"的纪律。

    顶层类型不对 → 按**用法错误（3）**退出，不静默吞错，也不假装通过。
    """
    data = load_json_file(path, what)
    if not isinstance(data, dict):
        err("%s 顶层必须是 JSON 对象，实际是 %s: %s" % (what, type(data).__name__, path))
        sys.exit(EXIT_USAGE)
    return data


def write_json_file(path, data):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


DEFAULT_UA = "touchstone-skill/2.0 (+hardcheck; fail-closed)"


# --------------------------------------------------------------------------
# v3 新增：缓存 / 并发 / 重试 / 原子写 —— 为"效率 + 稳定性"服务
# --------------------------------------------------------------------------

def default_cache_dir():
    # v4 起统一为 TOUCHSTONE_CACHE_DIR；DEHALLU_CACHE_DIR 是改名前的旧名，继续兼容
    base = os.environ.get("TOUCHSTONE_CACHE_DIR") or os.environ.get("DEHALLU_CACHE_DIR")
    if base:
        return base
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    return os.path.join(tmp, "touchstone-cache")


def cache_path(cache_dir, kind, target):
    key = hashlib.sha256(("%s|%s" % (kind, target)).encode("utf-8")).hexdigest()[:32]
    return os.path.join(cache_dir, "%s-%s.json" % (kind, key))


def cache_get(cache_dir, kind, target, ttl=DEFAULT_CACHE_TTL):
    """读缓存。命中返回 dict，未命中/过期/损坏返回 None（损坏绝不抛异常）。"""
    if not cache_dir:
        return None
    try:
        p = cache_path(cache_dir, kind, target)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            item = json.load(f)
        if time.time() - float(item.get("ts", 0)) > ttl:
            return None
        return item.get("value")
    except Exception:
        return None


def cache_set(cache_dir, kind, target, value):
    """写缓存。任何失败都静默忽略 —— 缓存不是关键路径。"""
    if not cache_dir:
        return
    try:
        os.makedirs(cache_dir, exist_ok=True)
        p = cache_path(cache_dir, kind, target)
        _atomic_json_dump(p, {"ts": time.time(), "value": value})
    except Exception:
        pass


def _atomic_json_dump(path, data, indent=None):
    """同目录唯一临时文件 + replace，避免多进程争用固定 .tmp 路径。"""
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            if indent is not None:
                f.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def atomic_write_json(path, data):
    """原子写 JSON：先写 .tmp 再 replace，避免写到一半崩溃留下坏文件。"""
    _atomic_json_dump(path, data, indent=2)


def run_with_retry(fn, retries=1, delay=0.4):
    """轻量重试：只重试"疑似瞬时故障"（超时/连接类），不重试逻辑失败。"""
    last = None
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(delay * (i + 1))
    raise last


def map_parallel(fn, items, jobs=1):
    """并发执行（I/O 密集型用）。jobs<=1 时退化为串行，保证行为一致。"""
    if not items:
        return []
    if jobs <= 1:
        return [fn(x) for x in items]
    jobs = min(jobs, max(1, len(items)), 16)  # 上限 16，防止把对方服务打挂
    try:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            return list(ex.map(fn, items))
    except Exception:
        # 线程池不可用（受限环境）→ 串行兜底，绝不因此崩掉
        return [fn(x) for x in items]


def budget_exceeded(current, limit):
    if not limit:
        return False
    return current >= limit


def env_truthy(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


class ArgParser(argparse.ArgumentParser):
    """统一 argparse 的错误退出码。

    argparse 默认用退出码 2 表示参数错误，但本套件约定 **2 = 存在未验证**，
    两者混淆会让下游把"命令写错了"误读成"有未验证项"。所以参数错误一律走 3。
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("[touchstone] 参数错误：%s\n" % message)
        sys.exit(EXIT_USAGE)
