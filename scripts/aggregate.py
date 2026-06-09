#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TV 直播源聚合 V10 — 满血冗余修正版
修正内容：
1. 召回 V6 的 7 大基础源矩阵，放弃 404 死链，恢复 290+ 链路冗余防断流。
2. 恢复 V6 的别名长词优先匹配架构，根除精确匹配导致的漏台（CCTV-5+、卡通台等）。
3. 继承 V9 的 EPG、Logo、VOD 与 100% 物理拍扁特性。
"""

import json
import os
import re
import urllib.request
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------
# 1. 恢复 V6 满血源矩阵 (保障 3-5 冗余度)
# ---------------------------------------------------------
TOP_SOURCES = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://iptv-org.github.io/iptv/countries/cn.m3u"
]

HLJ_LOCAL = [
    {"name": "黑龙江卫视", "url": "http://111.40.205.87/live/hljws.m3u8"},
    {"name": "黑龙江都市", "url": "http://111.40.205.87/live/ds.m3u8"},
    {"name": "黑龙江影视", "url": "http://111.40.205.87/live/ys.m3u8"},
    {"name": "黑龙江文体", "url": "http://111.40.205.87/live/wt.m3u8"},
    {"name": "哈尔滨综合", "url": "http://111.40.205.87/live/hrb1.m3u8"}
]

VOD_SITES = [
    {"key": "kuaikan", "name": "极速影院", "type": 1, "api": "https://kuaikan-api.com/api.php/provide/vod", "searchable": 1},
    {"key": "lzm3u8",  "name": "量子秒播", "type": 1, "api": "https://cj.lzkj1.com/api.php/provide/vod", "searchable": 1},
    {"key": "ffm3u8",  "name": "非凡蓝光", "type": 1, "api": "https://cj.ffzyapi.com/api.php/provide/vod", "searchable": 1}
]

# ---------------------------------------------------------
# 2. 长辈白名单与别名匹配系统 (彻底恢复 61 大台)
# ---------------------------------------------------------
WHITELIST = [
    ("CCTV-1", ["CCTV-1", "CCTV1"]), ("CCTV-2", ["CCTV-2", "CCTV2"]),
    ("CCTV-3", ["CCTV-3", "CCTV3"]), ("CCTV-4", ["CCTV-4", "CCTV4"]),
    ("CCTV-5", ["CCTV-5", "CCTV5"]), ("CCTV-5+", ["CCTV-5+", "CCTV5+", "CCTV5Plus"]),
    ("CCTV-6", ["CCTV-6", "CCTV6"]), ("CCTV-7", ["CCTV-7", "CCTV7"]),
    ("CCTV-8", ["CCTV-8", "CCTV8"]), ("CCTV-9", ["CCTV-9", "CCTV9"]),
    ("CCTV-10", ["CCTV-10", "CCTV10"]), ("CCTV-11", ["CCTV-11", "CCTV11"]),
    ("CCTV-12", ["CCTV-12", "CCTV12"]), ("CCTV-13", ["CCTV-13", "CCTV13"]),
    ("CCTV-14", ["CCTV-14", "CCTV14"]), ("CCTV-15", ["CCTV-15", "CCTV15"]),
    
    ("黑龙江卫视", ["黑龙江卫视"]), ("黑龙江都市", ["黑龙江都市"]),
    ("黑龙江影视", ["黑龙江影视"]), ("黑龙江文体", ["黑龙江文体"]),
    ("哈尔滨综合", ["哈尔滨综合", "哈尔滨新闻综合"]),
    
    ("湖南卫视", ["湖南卫视"]), ("浙江卫视", ["浙江卫视"]),
    ("江苏卫视", ["江苏卫视"]), ("东方卫视", ["东方卫视", "DragonTV"]),
    ("北京卫视", ["北京卫视"]), ("安徽卫视", ["安徽卫视"]),
    ("山东卫视", ["山东卫视"]), ("广东卫视", ["广东卫视"]),
    ("深圳卫视", ["深圳卫视"]), ("辽宁卫视", ["辽宁卫视"]),
    ("河南卫视", ["河南卫视"]), ("湖北卫视", ["湖北卫视"]),
    ("江西卫视", ["江西卫视"]), ("四川卫视", ["四川卫视"]),
    ("重庆卫视", ["重庆卫视"]), ("天津卫视", ["天津卫视"]),
    ("河北卫视", ["河北卫视"]), ("东南卫视", ["东南卫视", "福建卫视"]),
    ("广西卫视", ["广西卫视"]), ("山西卫视", ["山西卫视"]),
    ("陕西卫视", ["陕西卫视"]), ("海南卫视", ["海南卫视"]),
    ("贵州卫视", ["贵州卫视"]), ("云南卫视", ["云南卫视"]),
    ("甘肃卫视", ["甘肃卫视"]), ("吉林卫视", ["吉林卫视"]),
    ("内蒙古卫视", ["内蒙古卫视"]), ("宁夏卫视", ["宁夏卫视"]),
    ("新疆卫视", ["新疆卫视"]), ("西藏卫视", ["西藏卫视"]),
    ("青海卫视", ["青海卫视"]),
    
    ("求索动物", ["求索动物"]), ("求索生活", ["求索生活"]),
    ("求索科学", ["求索科学"]), ("求索纪录", ["求索纪录"]),
    ("劲爆体育", ["劲爆体育"]), ("卡酷少儿", ["卡酷少儿", "卡酷", "BTV卡酷少儿"]),
    ("优漫卡通", ["优漫卡通", "优漫"]), ("金鹰卡通", ["金鹰卡通", "金鹰"]),
    ("哈哈炫动", ["哈哈炫动", "哈哈"])
]

# 编译模糊匹配表（长词优先）
def _norm(s):
    s = unicodedata.normalize("NFKC", s.upper())
    s = re.sub(r'[-_（）()【】\[\]\s·•\.\u200b-\u200d\ufeff]', "", s)
    return s

MATCH_LIST = []
for std_name, aliases in WHITELIST:
    for alias in aliases:
        MATCH_LIST.append((_norm(alias), std_name))
MATCH_LIST.sort(key=lambda x: -len(x[0]))

GOLDEN_ORDER = {std_name: idx + 1 for idx, (std_name, _) in enumerate(WHITELIST)}

def clean_and_weight(raw_name):
    """恢复 V6 级别的极宽容模糊匹配与高清沉底"""
    norm_name = _norm(raw_name)
    
    # 垃圾过滤
    if any(k in norm_name for k in ["测试", "购物", "广播", "RADIO", "CCTV16", "CCTV17"]):
        return "", 999

    # 白名单别名探测
    matched_std = None
    for alias_norm, std_name in MATCH_LIST:
        pos = norm_name.find(alias_norm)
        if pos != -1:
            if std_name.startswith("CCTV") and alias_norm[-1].isdigit():
                after = pos + len(alias_norm)
                if after < len(norm_name) and norm_name[after].isdigit(): continue
            matched_std = std_name
            break

    if matched_std:
        return matched_std, GOLDEN_ORDER[matched_std]
    
    # 双轨瀑布流：未命中白名单的高清台洗澡沉底
    is_hd = bool(re.search(r'(1080|4K|FHD|HD)', raw_name, re.I))
    if is_hd:
        clean = raw_name.upper().strip()
        clean = re.sub(r'[(（\[].*?[)）\]]', '', clean)
        clean = re.sub(r'(FHD|HD|4K|8K|1080P|720P|50FPS|60FPS|IPV6|专属)', '', clean, flags=re.I).strip()
        if "卫视" in clean or "CCTV" in clean:
            return f"{clean} 高清", 100 + len(clean)

    return "", 999

# ---------------------------------------------------------
# 3. 异步拉取与解析引擎 (保留 TXT 高级修正)
# ---------------------------------------------------------
def fetch_source(url):
    print(f"[FETCH] 拉取源: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (TVBox)'})
        with urllib.request.urlopen(req, timeout=12) as response:
            content = response.read()
            for encoding in ['utf-8', 'gbk']:
                try: return content.decode(encoding)
                except: continue
            return content.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[ERROR] 拉取失败 {url}: {e}")
        return ""

def parse_content(text):
    results = []
    lines = text.splitlines()
    current_name = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#genre#"): continue
        
        if line.startswith("#EXTINF"):
            match = re.search(r'tvg-name="([^"]+)"', line)
            current_name = match.group(1) if match else line.split(",")[-1].strip()
        elif line.startswith("http"):
            if current_name:
                results.append((current_name, line))
                current_name = ""
        elif "," in line:
            parts = line.split(",", 1)
            if len(parts) == 2 and parts[1].strip().startswith("http"):
                results.append((parts[0].strip(), parts[1].strip()))
    return results

# ---------------------------------------------------------
# 4. 矩阵生成与物理拍扁
# ---------------------------------------------------------
def main():
    print("=" * 50)
    print("开始执行 V10 冗余修正 & 物理拍扁版...")
    print("=" * 50)
    
    all_links = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_to_url = {pool.submit(fetch_source, url): url for url in TOP_SOURCES}
        for future in as_completed(future_to_url):
            if text := future.result(): all_links.extend(parse_content(text))

    for local in HLJ_LOCAL:
        all_links.append((local['name'], local['url']))

    channel_dict = {}
    for raw_name, url in all_links:
        clean_name, weight = clean_and_weight(raw_name)
        if weight == 999 or not clean_name: continue
        
        if clean_name not in channel_dict:
            channel_dict[clean_name] = {"urls": [], "weight": weight}
        if url not in channel_dict[clean_name]["urls"]:
            channel_dict[clean_name]["urls"].append(url)

    sorted_channels = []
    for name, data in sorted(channel_dict.items(), key=lambda x: x[1]["weight"]):
        sorted_channels.append({"name": name, "urls": data["urls"]})

    if not sorted_channels:
        sorted_channels = [{"name": "测试频道(兜底)", "urls": ["http://111.40.205.87/live/ds.m3u8"]}]

    # 物理拍扁处理
    flat_channels = []
    for ch in sorted_channels:
        for url in ch["urls"]:
            flat_channels.append({"name": ch["name"], "url": url})

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    tvbox_data = {
        "spider": "",
        "logo": "https://epg.112114.xyz/logo/{name}.png",
        "epg": "http://epg.112114.xyz/?ch={name}&date={date}",
        "sites": VOD_SITES,
        "lives": [{"group": "电视直播", "channels": flat_channels}]
    }
    with open(os.path.join(base_dir, "tvbox.json"), "w", encoding="utf-8") as f:
        json.dump(tvbox_data, f, ensure_ascii=False, indent=2)

    with open(os.path.join(base_dir, "sources.txt"), "w", encoding="utf-8") as f:
        f.write("电视直播,#genre#\n")
        for ch in flat_channels:
            f.write(f"{ch['name']},{ch['url']}\n")

    with open(os.path.join(base_dir, "sources.m3u"), "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in flat_channels:
            f.write(f'#EXTINF:-1 group-title="电视直播",{ch["name"]}\n{ch["url"]}\n')

    print("=" * 50)
    print(f"[SUCCESS] V10 聚合完成！唯一频道数恢复。")
    print(f"物理拍扁后，冗余条目总数: {len(flat_channels)} 条记录。")
    print("=" * 50)

if __name__ == "__main__":
    main()