#!/usr/bin/env python3
"""
直播源健康检查器 v1.1

功能：
1. 读取生成的 tvbox.json / sources.json / sources.txt / sources.m3u
2. 对每条 URL 做 HTTP HEAD 探活
3. 输出：可用率统计 + 失效列表 + 按频道分组报告
4. 支持本地运行和 GitHub Actions 两种模式

用法：
  python scripts/source-validator.py                    # 全量检查
  python scripts/source-validator.py --timeout 5         # 自定义超时（秒）
  python scripts/source-validator.py --json-only         # 只检查 JSON
  python scripts/source-validator.py --markdown          # 输出 Markdown 报告
"""

import json
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── 编码兼容 ──
def _safe(text):
    """Windows GBK 终端安全输出，替代 emoji 等不可编码字符"""
    if not text:
        return text
    try:
        return text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
    except Exception:
        return (text.replace("\u2705", "[OK]")
                    .replace("\u274c", "[X]")
                    .replace("\u26a0\ufe0f", "[!]")
                    .replace("\U0001f389", "[OK]"))

# ── 路径 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)

SOURCES = {
    "tvbox.json":    ("JSON (flat)",  None),
    "sources.json":  ("JSON (group)", None),
    "sources.txt":   ("TXT",          None),
    "sources.m3u":   ("M3U",          None),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TVSourceValidator/1.1)",
    "Accept":     "*/*",
}

HTTP_TIMEOUT = 10
MAX_WORKERS  = 20
GH_ANNOTATE  = os.environ.get("GITHUB_ACTIONS") == "true"


def parse_args():
    p = argparse.ArgumentParser(description="直播源健康检查器")
    p.add_argument("--timeout", type=int, default=HTTP_TIMEOUT, help="HTTP 超时秒数")
    p.add_argument("--json-only", action="store_true", help="只检查 JSON 格式文件")
    p.add_argument("--markdown", action="store_true", help="输出 Markdown 格式报告")
    return p.parse_args()


def load_entries(path, fmt):
    """从各种格式文件中提取 (name, url) 条目"""
    ext = os.path.splitext(path)[1].lower()
    entries = []

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lives = data.get("lives", [])
        for grp in lives:
            for ch in grp.get("channels", []):
                name = ch.get("name", "?")
                # 兼容 url 字符串 和 urls 数组
                urls = ch.get("urls", [])
                u = ch.get("url", "") or ""
                if isinstance(urls, list) and urls:
                    for url in urls:
                        if url:
                            entries.append((name, url))
                elif u:
                    entries.append((name, u))
        return entries

    elif ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2 and parts[1].startswith(("http", "rtmp")):
                    entries.append((parts[0].strip(), parts[1].strip()))
        return entries

    elif ext == ".m3u":
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        for block in content.split("#EXTINF")[1:]:
            lines = block.strip().splitlines()
            if len(lines) >= 2:
                name = ""
                m = re.search(r',([^,]+)$', lines[0])
                if m:
                    name = m.group(1).strip()
                url = lines[-1].strip()
                if url.startswith(("http", "rtmp")):
                    entries.append((name, url))
        return entries

    return entries


def check_url(name, url, timeout):
    """探活 URL

    对 .m3u8 等流媒体地址先用 HEAD 探，被拒则降级为 GET（只读前 1KB）。
    """
    result = {
        "name": name,
        "url": url,
        "status": "unknown",
        "code": 0,
        "elapsed": 0,
        "error": "",
    }
    is_stream = any(ext in url.lower() for ext in [".m3u8", ".ts", ".flv", ".mp4"])
    t0 = 0

    def _try(method):
        nonlocal t0
        req = Request(url, method=method, headers=HEADERS)
        t0 = time.time()
        resp = urlopen(req, timeout=timeout)
        # 对于流媒体，只读前 1KB 判断连接是否正常
        if is_stream and method == "GET":
            resp.read(1024)
        return resp

    for method in ("HEAD", "GET"):
        try:
            resp = _try(method)
            result["elapsed"] = round(time.time() - t0, 2)
            result["code"] = resp.status
            result["status"] = "ok" if resp.status < 400 else "fail"
            return result
        except HTTPError as e:
            if e.code == 405 and method == "HEAD":
                # 405 Method Not Allowed → 降级 GET
                continue
            result["elapsed"] = round(time.time() - t0, 2)
            result["code"] = e.code
            result["error"] = str(e)
            result["status"] = "fail"
            return result
        except URLError as e:
            result["elapsed"] = round(time.time() - t0, 2)
            result["error"] = str(e.reason)
            result["status"] = "error"
            return result
        except Exception as e:
            result["error"] = str(e)
            result["status"] = "error"
            return result
    return result


def print_report(results, elapsed_all, args):
    """输出报告"""
    total = len(results)
    ok    = sum(1 for r in results if r["status"] == "ok")
    fail  = sum(1 for r in results if r["status"] == "fail")
    error = sum(1 for r in results if r["status"] == "error")

    gbk = sys.stdout.encoding and sys.stdout.encoding.upper() == "GBK"
    ok_icon   = "[OK]" if gbk else "\u2705"
    fail_icon = "[X]"  if gbk else "\u274c"
    warn_icon = "[!]"  if gbk else "\u26a0\ufe0f"

    # 按频道分组
    by_channel = {}
    for r in results:
        by_channel.setdefault(r["name"], []).append(r)

    alive_channels = sum(1 for ch, chs in by_channel.items() if any(c["status"] == "ok" for c in chs))
    dead_channels  = sum(1 for ch, chs in by_channel.items() if all(c["status"] != "ok" for c in chs))

    if args.markdown or GH_ANNOTATE:
        # Markdown 模式
        now_str = time.strftime('%Y-%m-%d %H:%M')
        print(f"# 直播源健康报告 ({now_str})")
        print()
        print(f"**总检查** {total} 条 **可用** {ok} **失效** {fail} **错误** {error}")
        print(f"**有效频道** {alive_channels}/{len(by_channel)} 耗时 {elapsed_all:.1f}s")
        print()
        print("## 概览")
        print()
        print("| 状态 | 数量 | 占比 |")
        print("|------|------|------|")
        if total:
            print(f"| OK | {ok} | {ok/total*100:.1f}% |")
            print(f"| FAIL | {fail} | {fail/total*100:.1f}% |")
            print(f"| ERROR | {error} | {error/total*100:.1f}% |")
        print()
        print("## 失效频道详情")
        print()
        dead = [r for r in results if r["status"] != "ok"]
        if dead:
            print("| 频道 | URL | 状态 | 耗时 | 原因 |")
            print("|------|-----|------|------|------|")
            for r in dead[:30]:
                nm = r["name"][:20]
                ul = r["url"][:50]
                st = "X" if r["status"] == "fail" else "!"
                er = r["error"][:30]
                print(f"| {nm} | `{ul}...` | {st} | {r['elapsed']}s | {er} |")
            if len(dead) > 30:
                print(f"| ... 还有 {len(dead)-30} 条失效 ... |")
        else:
            print("**全部通过！**")
    else:
        # 终端模式
        print()
        print(_safe(f"{'='*60}"))
        now_str = time.strftime('%Y-%m-%d %H:%M')
        print(_safe(f"  直播源健康检查报告 ({now_str})"))
        print(_safe(f"{'='*60}"))
        print(_safe(f"  总检查: {total} 条  {ok_icon} {ok} 可用  {fail_icon} {fail} 失效  {warn_icon} {error} 错误"))
        print(_safe(f"  有效频道: {alive_channels}/{len(by_channel)}  耗时: {elapsed_all:.1f}s"))
        print(_safe(f"{'='*60}"))
        print()
        dead = [r for r in results if r["status"] != "ok"]
        if dead:
            print(_safe(f"  {fail_icon} 以下 {len(dead)} 条链路不可用:"))
            for r in dead[:20]:
                tag = "FAIL" if r["status"] == "fail" else "ERR"
                print(_safe(f"    [{tag}] {r['name'][:20]:20s} {r['error'][:40]}"))
            if len(dead) > 20:
                print(_safe(f"    ... 还有 {len(dead)-20} 条 ..."))
        else:
            print(_safe(f"  {ok_icon} 全部通过！所有源均可用"))
        print()

    return {
        "total": total,
        "ok": ok,
        "fail": fail,
        "error": error,
        "alive_channels": alive_channels,
        "total_channels": len(by_channel),
    }


def main():
    args = parse_args()
    timeout = args.timeout

    # 收集所有源目录
    all_entries = []
    file_source = {}

    for fname, (desc, _) in SOURCES.items():
        if args.json_only and not fname.endswith(".json"):
            continue
        fpath = os.path.join(REPO_ROOT, fname)
        if not os.path.isfile(fpath):
            print(_safe(f"  [SKIP] {fname} 不存在"), file=sys.stderr)
            continue
        entries = load_entries(fpath, desc)
        all_entries.extend(entries)
        file_source[desc] = len(entries)
        print(_safe(f"  [LOAD] {fname} ({desc}): {len(entries)} 条目"))

    # 去重
    seen = set()
    unique = []
    for name, url in all_entries:
        if url not in seen:
            seen.add(url)
            unique.append((name, url))

    print(_safe(f"\n  去重后: {len(unique)}/{len(all_entries)} 条 (去重 {len(all_entries)-len(unique)})"))
    if not unique:
        print(_safe("  WARN: 没有可检查的条目"))
        return

    # 并行探活
    print(_safe(f"\n  开始探活 (timeout={timeout}s, workers={MAX_WORKERS})..."))
    t0 = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        fut_map = {pool.submit(check_url, name, url, timeout): (name, url)
                   for name, url in unique}
        done = 0
        total = len(fut_map)
        for fut in as_completed(fut_map):
            done += 1
            results.append(fut.result())
            if done % 50 == 0:
                print(_safe(f"    [{done}/{total}]"), file=sys.stderr)

    elapsed = time.time() - t0

    # 输出报告
    stats = print_report(results, elapsed, args)

    # GitHub Actions Annotation
    if GH_ANNOTATE:
        if stats["fail"] > 0 and stats["total"]:
            rate = stats["ok"] / stats["total"] * 100
            print(f"::warning::直播源检查: {stats['fail']} 条失效, {stats['error']} 条错误, "
                  f"可用率 {stats['ok']}/{stats['total']} ({rate:.1f}%)")

    sys.exit(0 if stats["fail"] == 0 and stats["error"] == 0 else 1)


if __name__ == "__main__":
    main()
