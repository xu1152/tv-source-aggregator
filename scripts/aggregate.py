#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
家用电视直播聚合器（纯直播单列表版）
设计目标：
1. 只做老人看电视需要的直播，不再混入点播 / 复杂 TVBox 外壳。
2. 先输出 50-100 个常用频道，优先央视 / 主流卫视 / 黑龙江本地台。
3. 同时保留多种输出格式，方便给不同盒子入口测试。
4. 将“源整理”和“输出适配”分开，后续盒子兼容只改输出层。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 12
MAX_WORKERS = 6
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ElderLive/1.0)"}
LIVE_GROUP = "电视直播"

OUTPUT_LIVE_TXT = "live.txt"
OUTPUT_LIVE_M3U = "live.m3u"
OUTPUT_CHANNELS_DEBUG = "channels-debug.json"
OUTPUT_BOX_LIVE = "box-live.json"
OUTPUT_TEST_TXT = "live-test.txt"
OUTPUT_TEST_M3U = "live-test.m3u"
OUTPUT_LEGACY_SOURCES_TXT = "sources.txt"
OUTPUT_LEGACY_SOURCES_M3U = "sources.m3u"
OUTPUT_LEGACY_SOURCES_JSON = "sources.json"
OUTPUT_LEGACY_TVBOX_JSON = "tvbox.json"
OUTPUT_DATASOURCE = "datasource.json"

SOURCE_URLS = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
]

PRIORITY_CHANNELS = [
    ("CCTV-1", ["CCTV-1", "CCTV1", "CCTV1综合"]),
    ("CCTV-2", ["CCTV-2", "CCTV2"]),
    ("CCTV-3", ["CCTV-3", "CCTV3"]),
    ("CCTV-4", ["CCTV-4", "CCTV4"]),
    ("CCTV-5", ["CCTV-5", "CCTV5"]),
    ("CCTV-5+", ["CCTV-5+", "CCTV5+", "CCTV5PLUS"]),
    ("CCTV-6", ["CCTV-6", "CCTV6"]),
    ("CCTV-7", ["CCTV-7", "CCTV7"]),
    ("CCTV-8", ["CCTV-8", "CCTV8"]),
    ("CCTV-9", ["CCTV-9", "CCTV9"]),
    ("CCTV-10", ["CCTV-10", "CCTV10"]),
    ("CCTV-11", ["CCTV-11", "CCTV11"]),
    ("CCTV-12", ["CCTV-12", "CCTV12"]),
    ("CCTV-13", ["CCTV-13", "CCTV13"]),
    ("CCTV-14", ["CCTV-14", "CCTV14"]),
    ("CCTV-15", ["CCTV-15", "CCTV15"]),
    ("黑龙江卫视", ["黑龙江卫视"]),
    ("黑龙江都市", ["黑龙江都市"]),
    ("黑龙江影视", ["黑龙江影视"]),
    ("黑龙江文体", ["黑龙江文体"]),
    ("哈尔滨综合", ["哈尔滨综合", "哈尔滨新闻综合"]),
    ("湖南卫视", ["湖南卫视"]),
    ("浙江卫视", ["浙江卫视"]),
    ("江苏卫视", ["江苏卫视"]),
    ("东方卫视", ["东方卫视", "DRAGONTV"]),
    ("北京卫视", ["北京卫视"]),
    ("安徽卫视", ["安徽卫视"]),
    ("山东卫视", ["山东卫视"]),
    ("广东卫视", ["广东卫视"]),
    ("深圳卫视", ["深圳卫视"]),
    ("辽宁卫视", ["辽宁卫视"]),
    ("河南卫视", ["河南卫视"]),
    ("湖北卫视", ["湖北卫视"]),
    ("江西卫视", ["江西卫视"]),
    ("四川卫视", ["四川卫视"]),
    ("重庆卫视", ["重庆卫视"]),
    ("天津卫视", ["天津卫视"]),
    ("河北卫视", ["河北卫视"]),
    ("东南卫视", ["东南卫视", "福建卫视"]),
    ("广西卫视", ["广西卫视"]),
    ("山西卫视", ["山西卫视"]),
    ("陕西卫视", ["陕西卫视"]),
    ("海南卫视", ["海南卫视"]),
    ("贵州卫视", ["贵州卫视"]),
    ("云南卫视", ["云南卫视"]),
    ("甘肃卫视", ["甘肃卫视"]),
    ("吉林卫视", ["吉林卫视"]),
    ("内蒙古卫视", ["内蒙古卫视"]),
    ("宁夏卫视", ["宁夏卫视"]),
    ("新疆卫视", ["新疆卫视"]),
    ("西藏卫视", ["西藏卫视"]),
    ("青海卫视", ["青海卫视"]),
    ("卡酷少儿", ["卡酷少儿", "卡酷", "BTV卡酷少儿"]),
    ("优漫卡通", ["优漫卡通", "优漫"]),
    ("金鹰卡通", ["金鹰卡通", "金鹰"]),
    ("哈哈炫动", ["哈哈炫动", "哈哈"]),
    ("劲爆体育", ["劲爆体育"]),
    ("求索纪录", ["求索纪录"]),
    ("求索科学", ["求索科学"]),
]

LOCAL_CHANNELS = [
    ("黑龙江卫视", "http://111.40.205.87/live/hljws.m3u8"),
    ("黑龙江都市", "http://111.40.205.87/live/ds.m3u8"),
    ("黑龙江影视", "http://111.40.205.87/live/ys.m3u8"),
    ("黑龙江文体", "http://111.40.205.87/live/wt.m3u8"),
    ("哈尔滨综合", "http://111.40.205.87/live/hrb1.m3u8"),
]

TEST_CHANNELS = [
    ("CCTV-1", "http://101.66.195.125:9901/tsfile/live/0001_1.m3u8?key=txiptv&playlive=0&authid=0"),
    ("CCTV-2", "http://101.66.195.125:9901/tsfile/live/0002_1.m3u8?key=txiptv&playlive=0&authid=0"),
]

BOX_DATASOURCE = {
    "spider": "",
    "sites": [
        {
            "key": "dummy",
            "name": "占位数据源",
            "type": 3,
            "api": "",
            "searchable": 0,
            "quickSearch": 0,
            "filterable": 0,
        }
    ],
    "parses": [],
    "flags": [],
    "rules": [],
}

BOX_LIVE_WRAPPER = {
    "spider": "",
    "sites": [
        {
            "key": "dummy",
            "name": "占位防崩溃",
            "type": 3,
            "api": "",
            "searchable": 0,
        }
    ],
}

JUNK_KEYWORDS = [
    "测试", "购物", "广播", "RADIO", "试播", "试看", "导视", "轮播", "宣传", "推荐",
    "请勿贩卖", "维护", "公告", "免费订阅", "失效", "CCTV16", "CCTV17",
]

BAD_URL_KEYWORDS = [
    "$", "udp://", "mitv://", "p2p", "douyin", "youtube.com",
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.upper())
    return re.sub(r"[-_（）()【】\[\]\s·•\.]+", "", text)


ALIAS_TO_NAME: List[Tuple[str, str]] = []
for std_name, aliases in PRIORITY_CHANNELS:
    for alias in aliases:
        ALIAS_TO_NAME.append((_norm(alias), std_name))
ALIAS_TO_NAME.sort(key=lambda item: -len(item[0]))


JUNK_KEYS = [_norm(item) for item in JUNK_KEYWORDS]


def fetch_text(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read()
            for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"[WARN] fetch failed: {url} -> {exc}")
        return ""



def normalize_channel_name(raw_name: str) -> Optional[str]:
    name = raw_name.strip()
    if not name:
        return None
    key = _norm(name)
    if any(junk in key for junk in JUNK_KEYS):
        return None
    for alias_key, std_name in ALIAS_TO_NAME:
        pos = key.find(alias_key)
        if pos == -1:
            continue
        if std_name.startswith("CCTV-") and alias_key[-1].isdigit():
            after = pos + len(alias_key)
            if after < len(key) and key[after].isdigit():
                continue
        return std_name
    return None



def clean_url(url: str) -> Optional[str]:
    url = url.strip()
    if not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    if url.startswith("http://["):
        return None
    lower = url.lower()
    if any(keyword in lower for keyword in BAD_URL_KEYWORDS):
        return None
    return url



def parse_m3u(text: str) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    current_name: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            current_name = line.rsplit(",", 1)[-1].strip() if "," in line else None
            continue
        if line.startswith("#"):
            continue
        if current_name:
            results.append((current_name, line))
            current_name = None
    return results



def parse_txt(text: str) -> List[Tuple[str, str]]:
    results: List[Tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.endswith(",#genre#"):
            continue
        if "," not in line:
            continue
        name, url = line.split(",", 1)
        results.append((name.strip(), url.strip()))
    return results



def parse_source(text: str) -> List[Tuple[str, str]]:
    if "#EXTM3U" in text or "#EXTINF" in text:
        return parse_m3u(text)
    return parse_txt(text)



def collect_entries() -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_text, url): url for url in SOURCE_URLS}
        for future in as_completed(futures):
            text = future.result()
            if text:
                entries.extend(parse_source(text))
    entries.extend(LOCAL_CHANNELS)
    return entries



def build_channels(entries: Iterable[Tuple[str, str]]) -> List[Dict[str, object]]:
    merged: Dict[str, List[str]] = {}
    for raw_name, raw_url in entries:
        name = normalize_channel_name(raw_name)
        url = clean_url(raw_url)
        if not name or not url:
            continue
        merged.setdefault(name, [])
        if url not in merged[name]:
            merged[name].append(url)

    for name, url in LOCAL_CHANNELS:
        cleaned = clean_url(url)
        if not cleaned:
            continue
        merged.setdefault(name, [])
        if cleaned not in merged[name]:
            merged[name].insert(0, cleaned)

    channels: List[Dict[str, object]] = []
    for name, _aliases in PRIORITY_CHANNELS:
        urls = merged.get(name, [])[:3]
        if urls:
            channels.append({"name": name, "urls": urls})
    return channels



def flatten_channels(channels: Iterable[Dict[str, object]]) -> List[Dict[str, str]]:
    flat: List[Dict[str, str]] = []
    for channel in channels:
        name = str(channel["name"])
        for url in channel.get("urls", []):
            flat.append({"name": name, "url": str(url)})
    return flat



def write_json(path: str, data: object) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)



def write_txt(path: str, channels: Iterable[Dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(f"{LIVE_GROUP},#genre#\n")
        for item in flatten_channels(channels):
            file.write(f"{item['name']},{item['url']}\n")



def write_m3u(path: str, channels: Iterable[Dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write("#EXTM3U\n")
        for item in flatten_channels(channels):
            file.write(f'#EXTINF:-1 group-title="{LIVE_GROUP}",{item["name"]}\n{item["url"]}\n')



def write_box_json(path: str, channels: List[Dict[str, object]]) -> None:
    payload = {
        **BOX_LIVE_WRAPPER,
        "lives": [{"group": LIVE_GROUP, "channels": channels}],
    }
    write_json(path, payload)



def write_legacy_json(path: str, channels: List[Dict[str, object]]) -> None:
    payload = {
        "spider": "",
        "sites": [],
        "lives": [{"group": LIVE_GROUP, "channels": channels}],
    }
    write_json(path, payload)



def write_debug_json(path: str, channels: List[Dict[str, object]]) -> None:
    debug_payload = {
        "group": LIVE_GROUP,
        "channel_count": len(channels),
        "channels": channels,
    }
    write_json(path, debug_payload)



def write_test_files() -> None:
    test_channels = [{"name": name, "urls": [url]} for name, url in TEST_CHANNELS]
    write_txt(os.path.join(BASE_DIR, OUTPUT_TEST_TXT), test_channels)
    write_m3u(os.path.join(BASE_DIR, OUTPUT_TEST_M3U), test_channels)



def main() -> None:
    print("=" * 50)
    print("开始生成家用纯直播单列表...")
    print("=" * 50)
    entries = collect_entries()
    channels = build_channels(entries)

    if not channels:
        channels = [{"name": "测试频道(兜底)", "urls": [LOCAL_CHANNELS[1][1]]}]

    write_debug_json(os.path.join(BASE_DIR, OUTPUT_CHANNELS_DEBUG), channels)
    write_box_json(os.path.join(BASE_DIR, OUTPUT_BOX_LIVE), channels)
    write_txt(os.path.join(BASE_DIR, OUTPUT_LIVE_TXT), channels)
    write_m3u(os.path.join(BASE_DIR, OUTPUT_LIVE_M3U), channels)

    write_legacy_json(os.path.join(BASE_DIR, OUTPUT_LEGACY_SOURCES_JSON), channels)
    write_box_json(os.path.join(BASE_DIR, OUTPUT_LEGACY_TVBOX_JSON), channels)
    write_txt(os.path.join(BASE_DIR, OUTPUT_LEGACY_SOURCES_TXT), channels)
    write_m3u(os.path.join(BASE_DIR, OUTPUT_LEGACY_SOURCES_M3U), channels)
    write_json(os.path.join(BASE_DIR, OUTPUT_DATASOURCE), BOX_DATASOURCE)
    write_test_files()

    print(f"[SUCCESS] 常用频道数: {len(channels)}")
    print(f"[SUCCESS] 输出文件: {OUTPUT_BOX_LIVE}, {OUTPUT_LIVE_TXT}, {OUTPUT_LIVE_M3U}, {OUTPUT_CHANNELS_DEBUG}")


if __name__ == "__main__":
    main()
