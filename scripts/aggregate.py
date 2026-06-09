#!/usr/bin/env python3
"""
TV 直播源聚合 V6 — 创维 22C 物理拍扁终极版
设计哲学：
1. 排序暴政：严格遵守 CCTV -> 黑龙江系 -> 顶流卫视 -> 地方卫视 -> 解闷台
2. 物理拍扁：JSON 输出彻底消灭 urls 数组，全部转化为独立的 {name, url} 对象
3. 零转义：强锁定 UTF-8 和 ensure_ascii=False，彻底根除老盒子乱码
4. 绝对零测速：只抓取，全放行
"""

import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.request import Request, urlopen

# ╔══════════════════════════════════════════════════════════════╗
# ║ 全局配置 ║
# ╚══════════════════════════════════════════════════════════════╝
OUTPUT_M3U = "sources.m3u"
OUTPUT_TXT = "sources.txt"
OUTPUT_JSON = "sources.json"
OUTPUT_TVBOX = "tvbox.json"
SINGLE_GROUP = "电视直播"
TIMEOUT = 15
MAX_WORKERS = 8
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TVBox/V6)"}

SOURCE_URLS = [
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", "m3u"),
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u", "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u", "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt", "txt"),
    ("https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u", "m3u"),
    ("https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u", "m3u"),
    ("https://iptv-org.github.io/iptv/countries/cn.m3u", "m3u"),
]

# 硬编码：黑龙江广电直连本地源（黄金位置空降，永不丢弃）
HLJ_LOCAL = [
    ("黑龙江都市", "http://111.40.205.87/live/ds.m3u8"),
    ("黑龙江影视", "http://111.40.205.87/live/ys.m3u8"),
    ("黑龙江文体", "http://111.40.205.87/live/wt.m3u8"),
    ("哈尔滨综合", "http://111.40.205.87/live/hrb1.m3u8"),
]

# ╔══════════════════════════════════════════════════════════════╗
# ║ 白名单（列表顺序 = 最终长辈视觉绝对排序） ║
# ╚══════════════════════════════════════════════════════════════╝
WHITELIST = [
    # ── 1. 央视全阵列 ──
    ("cctv1", ["CCTV-1", "CCTV1"]),
    ("cctv2", ["CCTV-2", "CCTV2"]),
    ("cctv3", ["CCTV-3", "CCTV3"]),
    ("cctv4", ["CCTV-4", "CCTV4"]),
    ("cctv5", ["CCTV-5", "CCTV5"]),
    ("cctv6", ["CCTV-6", "CCTV6"]),
    ("cctv7", ["CCTV-7", "CCTV7"]),
    ("cctv8", ["CCTV-8", "CCTV8"]),
    ("cctv9", ["CCTV-9", "CCTV9"]),
    ("cctv10", ["CCTV-10", "CCTV10"]),
    ("cctv11", ["CCTV-11", "CCTV11"]),
    ("cctv12", ["CCTV-12", "CCTV12"]),
    ("cctv13", ["CCTV-13", "CCTV13"]),
    ("cctv14", ["CCTV-14", "CCTV14"]),
    ("cctv15", ["CCTV-15", "CCTV15"]),
    ("cctv5plus", ["CCTV-5+", "CCTV5+", "CCTV5Plus"]),

    # ── 2. 黑龙江黄金阵营 ──
    ("hlj_ws", ["黑龙江卫视"]),
    ("hlj_ds", ["黑龙江都市"]),
    ("hlj_ys", ["黑龙江影视"]),
    ("hlj_wt", ["黑龙江文体"]),
    ("hrb_zh", ["哈尔滨综合", "哈尔滨新闻综合"]),

    # ── 3. 一线王牌卫视 ──
    ("hunan", ["湖南卫视"]),
    ("zhejiang", ["浙江卫视"]),
    ("jiangsu", ["江苏卫视"]),
    ("dongfang", ["东方卫视", "DragonTV"]),
    ("beijing", ["北京卫视"]),

    # ── 4. 其他 26 省级卫视 ──
    ("anhui", ["安徽卫视"]),
    ("shandong", ["山东卫视"]),
    ("guangdong", ["广东卫视"]),
    ("shenzhen", ["深圳卫视"]),
    ("liaoning", ["辽宁卫视"]),
    ("henan", ["河南卫视"]),
    ("hubei", ["湖北卫视"]),
    ("jiangxi", ["江西卫视"]),
    ("sichuan", ["四川卫视"]),
    ("chongqing", ["重庆卫视"]),
    ("tianjin", ["天津卫视"]),
    ("hebei", ["河北卫视"]),
    ("fujian", ["东南卫视", "福建卫视"]),
    ("guangxi", ["广西卫视"]),
    ("shanxi", ["山西卫视"]),
    ("shan3xi", ["陕西卫视"]),
    ("hainan", ["海南卫视"]),
    ("guizhou", ["贵州卫视"]),
    ("yunnan", ["云南卫视"]),
    ("gansu", ["甘肃卫视"]),
    ("jilin", ["吉林卫视"]),
    ("neimenggu", ["内蒙古卫视"]),
    ("ningxia", ["宁夏卫视"]),
    ("xinjiang", ["新疆卫视"]),
    ("xizang", ["西藏卫视"]),
    ("qinghai", ["青海卫视"]),

    # ── 5. 末尾解闷台 ──
    ("qiusuodw", ["求索动物"]),
    ("qiusuosh", ["求索生活"]),
    ("qiusuokx", ["求索科学"]),
    ("qiusuo", ["求索纪录"]),
    ("jingbao", ["劲爆体育"]),
    ("kaku", ["卡酷少儿", "卡酷", "BTV卡酷少儿"]),
    ("youman", ["优漫卡通", "优漫"]),
    ("jinying", ["金鹰卡通", "金鹰"]),
    ("haha", ["哈哈炫动", "哈哈"]),
]

# 构建匹配系统
def _norm(s):
    s = unicodedata.normalize("NFKC", s.upper())
    s = re.sub(r'[-_（）()【】\[\]\s·•\.\u200b-\u200d\ufeff]', "", s)
    return s

def _name_key(name):
    return _norm(name)

MATCH_LIST = []
for wid, keywords in WHITELIST:
    for kw in keywords:
        MATCH_LIST.append((_norm(kw), wid))
MATCH_LIST.sort(key=lambda x: -len(x[0]))
WHITELIST_ORDER = {wid: i for i, (wid, _) in enumerate(WHITELIST)}
WHITELIST_DICT = {wid: keywords for wid, keywords in WHITELIST}

# 无情封杀的垃圾渠道
BLACKLIST_KEYS = {_norm(s) for s in ["CCTV16", "CCTV-16", "CCTV17", "CCTV-17", "CCTV-9(I)", "CCTV9I", "DRAGONTVINTERNATIONAL"]}
JUNK_KW = ["免费订阅", "公告说明", "维护", "请勿贩卖", "#佛系维护", "删除", "IPV6暂无", "测试", "TEST", "购物", "SHOPPING", "电视购物", "轮播", "循环", "广播", "RADIO"]

def clean_name(raw):
    name = raw.strip()
    if len(name) < 2:
        return ""
    for jk in JUNK_KW:
        if jk.upper() in name.upper():
            return ""
    name = re.sub(r'\s*[\[\(]?\d{3,4}[pP][\]\)]?\s*', '', name)
    name = re.sub(r'\s*-\s*\d{3,4}[pP]?\s*', '', name)
    name = re.sub(r'\s*(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|1080|720|2160|576|HEVC|50FPS|60FPS)\s*', '', name)
    for tag in ["[Not24/7]", "[Geo-blocked]", "[Offline]", "[Geo-block]"]:
        name = name.replace(tag, "")
    return name.strip() if len(name.strip()) >= 2 else ""

def match_whitelist(name):
    key = _name_key(name)
    for kw_norm, wid in MATCH_LIST:
        pos = key.find(kw_norm)
        if pos == -1:
            continue
        if wid.startswith("cctv") and kw_norm[-1].isdigit():
            after = pos + len(kw_norm)
            if after < len(key) and key[after].isdigit():
                continue
        return wid
    return None

def normalize_display(name):
    m = re.search(r'CCTV[\s-]*(\d+)', name, re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= 15:
        return re.sub(r'CCTV[\s-]*\d+', f'CCTV-{m.group(1)}', name)
    return re.sub(r'^BRTV', '', name)

def fetch_text(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            for enc in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
                try:
                    return raw.decode(enc)
                except:
                    pass
            return raw.decode("utf-8", errors="replace")
    except:
        return None

def parse_m3u(text):
    results, cur = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            cur = {}
            m = re.search(r'tvg-name="([^"]*)"', line)
            name = line.rsplit(",", 1)[-1].strip() if "," in line else (m.group(1).strip() if m else "")
            if name and not re.match(r'^\d{4,}$', name):
                cn = clean_name(name)
                if cn:
                    cur["name"] = cn
        elif line and not line.startswith("#") and cur.get("name"):
            results.append({"name": cur["name"], "url": line})
            cur = {}
    return results

def parse_txt(text):
    results = []
    for line in text.splitlines():
        line = line.strip().replace(",#genre#", "")
        if not line or line.startswith("#"):
            continue
        p = line.split(",", 1)
        if len(p) != 2:
            continue
        name, url = clean_name(p[0].strip()), p[1].strip()
        if name and url and (url.startswith("http") or url.startswith("rtmp") or url.startswith("rtp")):
            results.append({"name": name, "url": url})
    return results

def merge_and_dedup(entries):
    cmap = {}
    for e in entries:
        name, url = e.get("name", "").strip(), e.get("url", "").strip()
        if not name or not url:
            continue
        if _name_key(name) in BLACKLIST_KEYS:
            continue
        wid = match_whitelist(name)
        if not wid:
            continue
        disp = re.sub(r'\s+', '', re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]', '', name))
        if wid not in cmap:
            cmap[wid] = {"name": disp, "urls": [], "_order": WHITELIST_ORDER.get(wid, 999)}
        if len(disp) < len(cmap[wid]["name"]):
            cmap[wid]["name"] = disp
        if url not in cmap[wid]["urls"]:
            cmap[wid]["urls"].append(url)
    return cmap

def sort_channels(merged):
    result = []
    for wid, data in merged.items():
        data["name"] = WHITELIST_DICT[wid][0] if wid in WHITELIST_DICT else normalize_display(data["name"])
        result.append(data)
    result.sort(key=lambda x: x.get("_order", 999))
    for r in result:
        r.pop("_order", None)
    return result

def inject_local(channels):
    for name, url in HLJ_LOCAL:
        wid = match_whitelist(name)
        found = False
        for ch in channels:
            if _name_key(ch["name"]) == _name_key(name) or (wid and match_whitelist(ch["name"]) == wid):
                if url not in ch["urls"]:
                    ch["urls"].append(url)
                found = True
                break
        if not found:
            channels.append({"name": name, "urls": [url]})

    for ch in channels:
        ch["_order"] = WHITELIST_ORDER.get(match_whitelist(ch["name"]), 999)
    channels.sort(key=lambda x: x.get("_order", 999))
    for ch in channels:
        ch.pop("_order", None)
    return channels

# ╔══════════════════════════════════════════════════════════════╗
# ║ 矩阵输出（严格确保零转义、物理拍扁） ║
# ╚══════════════════════════════════════════════════════════════╝
def _write_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_flat_list(channels):
    """物理拍扁核心：剥离所有 urls 数组"""
    flat = []
    for ch in channels:
        for u in ch.get("urls", []):
            flat.append({"name": ch["name"], "url": u})
    return flat

def write_json_flat(channels, path):
    _write_json({"spider": "", "sites": [], "lives": [{"group": SINGLE_GROUP, "channels": generate_flat_list(channels)}]}, path)

def write_tvbox(channels, path):
    data = {
        "spider": "",
        "sites": [{"key": "dummy", "name": "占位防崩溃", "type": 3, "api": "", "searchable": 0}],
        "lives": [{"group": SINGLE_GROUP, "channels": generate_flat_list(channels)}]
    }
    _write_json(data, path)

def write_m3u(channels, path):
    lines = ["#EXTM3U"]
    for ch in channels:
        for url in ch.get("urls", []):
            lines.append(f'#EXTINF:-1 group-title="{SINGLE_GROUP}",{ch["name"]}\n{url}')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def write_txt(channels, path):
    lines = [f'{ch["name"]},{url}' for ch in channels for url in ch.get("urls", [])]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def main():
    print("开始执行 TV 直播源聚合 V6 (创维22C专版)...")
    all_entries = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_text, url): (url, fmt) for url, fmt in SOURCE_URLS}
        for fut in as_completed(futures):
            text = fut.result()
            if text:
                parser = parse_m3u if futures[fut][1] == "m3u" else parse_txt
                all_entries.extend(parser(text))

    merged = merge_and_dedup(all_entries)
    sorted_ch = inject_local(sort_channels(merged))

    sd = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(sd) if os.path.basename(sd) == "scripts" else sd

    write_json_flat(sorted_ch, os.path.join(root, OUTPUT_JSON))
    write_tvbox(sorted_ch, os.path.join(root, OUTPUT_TVBOX))
    write_m3u(sorted_ch, os.path.join(root, OUTPUT_M3U))
    write_txt(sorted_ch, os.path.join(root, OUTPUT_TXT))
    print("聚合完毕：零测速拉取完成，物理拍扁成功，零转义 JSON 与纯文本矩阵已生成在根目录。")

if __name__ == "__main__":
    main()
