#!/usr/bin/env python3
"""
TV 直播源聚合 v4 — 长辈极简版（零测速）
白名单匹配 → 去重 → 硬编码注入 → 强排序 → 多格式输出
不测速、不 ping、不验证 —— 名字匹配白名单即保留全部链路
"""
import json, re, os, sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT_JSON  = "sources.json"
OUTPUT_M3U   = "sources.m3u"
OUTPUT_TXT   = "sources.txt"
OUTPUT_TVBOX = "tvbox.json"

TIMEOUT = 15
MAX_WORKERS = 8

# ============================================================
# 公开直播源（仅拉取，不测速）
# ============================================================
SOURCE_URLS = [
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", "m3u"),
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u", "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u", "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt", "txt"),
    ("https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u", "m3u"),
    ("https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u", "m3u"),
    ("https://iptv-org.github.io/iptv/countries/cn.m3u", "m3u"),
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ============================================================
# 硬编码黑龙江本地源（广电直连，永不丢弃）
# ============================================================
LOCAL_SOURCES = [
    {"name": "黑龙江都市", "urls": ["http://111.40.205.87/live/ds.m3u8"]},
    {"name": "黑龙江影视", "urls": ["http://111.40.205.87/live/ys.m3u8"]},
    {"name": "黑龙江文体", "urls": ["http://111.40.205.87/live/wt.m3u8"]},
    {"name": "哈尔滨综合", "urls": ["http://111.40.205.87/live/hrb1.m3u8"]},
]

# ============================================================
# 唯一分类
# ============================================================
SINGLE_GROUP = "电视直播"

# ============================================================
# 白名单（按升序排列，索引即排序权重）
# ============================================================
WHITELIST = [
    # ── 第一顺位：央视阵列 ──
    ("cctv1",     ["CCTV-1", "CCTV1"]),
    ("cctv2",     ["CCTV-2", "CCTV2"]),
    ("cctv3",     ["CCTV-3", "CCTV3"]),
    ("cctv4",     ["CCTV-4", "CCTV4"]),
    ("cctv5",     ["CCTV-5", "CCTV5"]),
    ("cctv6",     ["CCTV-6", "CCTV6"]),
    ("cctv7",     ["CCTV-7", "CCTV7"]),
    ("cctv8",     ["CCTV-8", "CCTV8"]),
    ("cctv9",     ["CCTV-9", "CCTV9"]),
    ("cctv10",    ["CCTV-10", "CCTV10"]),
    ("cctv11",    ["CCTV-11", "CCTV11"]),
    ("cctv12",    ["CCTV-12", "CCTV12"]),
    ("cctv13",    ["CCTV-13", "CCTV13"]),
    ("cctv14",    ["CCTV-14", "CCTV14"]),
    ("cctv15",    ["CCTV-15", "CCTV15"]),
    ("cctv5plus", ["CCTV-5+", "CCTV5+", "CCTV5Plus"]),
    ("cetv1",     ["CETV-1", "CETV1", "中国教育1"]),
    ("cetv4",     ["CETV-4", "CETV4", "中国教育4"]),

    # ── 第二顺位：黑龙江阵营 ──
    ("hlj_ws", ["黑龙江卫视"]),
    ("hlj_ds", ["黑龙江都市"]),
    ("hlj_ys", ["黑龙江影视"]),
    ("hlj_wt", ["黑龙江文体"]),
    ("hrb_zh", ["哈尔滨综合", "哈尔滨新闻综合"]),

    # ── 第三顺位：一线卫视 ──
    ("hunan",    ["湖南卫视"]),
    ("zhejiang", ["浙江卫视"]),
    ("jiangsu",  ["江苏卫视"]),
    ("dongfang", ["东方卫视", "DragonTV"]),
    ("beijing",  ["北京卫视"]),

    # ── 第四顺位：其他省级卫视 ──
    ("anhui",     ["安徽卫视"]),
    ("shandong",  ["山东卫视"]),
    ("guangdong", ["广东卫视"]),
    ("shenzhen",  ["深圳卫视"]),
    ("liaoning",  ["辽宁卫视"]),
    ("henan",     ["河南卫视"]),
    ("hubei",     ["湖北卫视"]),
    ("jiangxi",   ["江西卫视"]),
    ("sichuan",   ["四川卫视"]),
    ("chongqing", ["重庆卫视"]),
    ("tianjin",   ["天津卫视"]),
    ("hebei",     ["河北卫视"]),
    ("fujian",    ["福建卫视", "东南卫视"]),
    ("guangxi",   ["广西卫视"]),
    ("shanxi",    ["山西卫视"]),
    ("shan3xi",   ["陕西卫视"]),
    ("hainan",    ["海南卫视"]),
    ("guizhou",   ["贵州卫视"]),
    ("yunnan",    ["云南卫视"]),
    ("gansu",     ["甘肃卫视"]),
    ("jilin",     ["吉林卫视"]),
    ("neimenggu", ["内蒙古卫视"]),
    ("ningxia",   ["宁夏卫视"]),
    ("xinjiang",  ["新疆卫视"]),
    ("xizang",    ["西藏卫视"]),
    ("qinghai",   ["青海卫视"]),

    # ── 第五顺位：精选数字/专题频道 ──
    ("qiusuodw",  ["求索动物"]),
    ("qiusuosh",  ["求索生活"]),
    ("qiusuokx",  ["求索科学"]),
    ("qiusuo",    ["求索纪录"]),
    ("fengyunzy", ["风云足球", "CCTV风云足球"]),
    ("fengyunjq", ["风云剧场", "CCTV风云剧场"]),
    ("fengyunyy", ["风云音乐", "CCTV风云音乐"]),
    ("dyjc",      ["第一剧场", "CCTV第一剧场"]),
    ("hxjc",      ["怀旧剧场", "CCTV怀旧剧场"]),
    ("shijiedl",  ["世界地理", "CCTV世界地理"]),
    ("guofang",   ["国防军事", "CCTV国防军事"]),
    ("nxss",      ["女性时尚", "CCTV女性时尚"]),
    ("xiangsyds", ["央视文化精品", "文化精品"]),
    ("zqjf",      ["早教频道", "早期教育"]),
    ("jjjy",      ["劲爆体育"]),
    ("chcjt",     ["CHC家庭影院"]),
    ("chcdz",     ["CHC动作电影"]),
    ("chcgq",     ["CHC高清电影"]),
    ("youman",    ["优漫卡通"]),
    ("jinying",   ["金鹰卡通"]),
    ("haha",      ["哈哈炫动"]),
    ("kaku",      ["卡酷少儿"]),
]

# ── 运行时构建 ──
def _build_match_list():
    items = []
    for wid, keywords in WHITELIST:
        for kw in keywords:
            norm = kw.upper().replace(" ", "").replace("·", "")
            norm = re.sub(r'[-_（）()【】\[\]]', '', norm)
            items.append((norm, wid))
    items.sort(key=lambda x: -len(x[0]))
    return items

MATCH_LIST = _build_match_list()
WHITELIST_ORDER = {wid: i for i, (wid, _) in enumerate(WHITELIST)}

# ============================================================
# 垃圾/黑名单
# ============================================================
JUNK_KW = [
    "免费订阅", "公告说明", "维护", "请勿贩卖", "#佛系维护",
    "删除", "IPV6暂无", "CCTV+", "TEST", "测试",
    "购物", "SHOPPING", "电视购物", "轮播", "循环",
    "广播", "RADIO",
]
BLACKLIST = {
    "CCTV16", "CCTV-16", "CCTV17", "CCTV-17",
    "CCTV-9(I)", "CCTV9I",
    "DRAGONTVINTERNATIONAL", "CCTV-",
}

# ============================================================
# 网络拉取
# ============================================================
def fetch_text(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        for enc in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
            try:
                return raw.decode(enc)
            except:
                continue
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] {url} -> {e}", file=sys.stderr)
        return None

# ============================================================
# 名称清洗
# ============================================================
def clean_name(raw_name):
    name = raw_name.strip()
    for jk in JUNK_KW:
        if jk.upper() in name.upper():
            return ""
    name = re.sub(r'\s*[\[\(]?\d{3,4}[pP][\]\)]?\s*', '', name)
    name = re.sub(r'\s*-\s*\d{3,4}[pP]?\s*', '', name)
    name = re.sub(r'\s*(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|1080|720|2160|576|HEVC|50FPS|60FPS)\s*', '', name)
    for tag in ['[Not24/7]', '[Geo-blocked]', '[Offline]', '[Geo-block]']:
        name = name.replace(tag, '')
    name = re.sub(r'\s+', '', name)
    return name

def name_to_key(name):
    import unicodedata
    n = unicodedata.normalize('NFKC', name.upper())
    n = re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]', '', n)
    n = re.sub(r'[\d０-９]+\s*[PＰpｐ]\b', '', n)
    n = re.sub(r'[-_（）()【】\[\]\s·•\.\u200b\u200c\u200d\ufeff]', '', n)
    return n

def match_whitelist(name):
    key = name_to_key(name)
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

# ============================================================
# 解析器
# ============================================================
def parse_m3u(text):
    results = []
    cur = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            cur = {}
            m = re.search(r'tvg-name="([^"]*)"', line)
            tvg_name = m.group(1).strip() if m else ""
            if "," in line:
                name = line.rsplit(",", 1)[-1].strip()
            else:
                name = tvg_name or ""
            if name and not re.match(r'^\d{4,}$', name):
                cn = clean_name(name)
                if cn:
                    cur["name"] = cn
        elif line and not line.startswith("#"):
            if cur.get("name"):
                results.append({"name": cur["name"], "urls": [line.strip()]})
            cur = {}
    return results

def parse_txt(text):
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace(",#genre#", "")
        p = line.split(",", 1)
        if len(p) == 2:
            name = clean_name(p[0].strip())
            url = p[1].strip()
            if name and url and (url.startswith("http") or url.startswith("rtmp")):
                results.append({"name": name, "urls": [url]})
    return results

# ============================================================
# 合并去重（保留全部 URL，不测速、不删链）
# ============================================================
def merge(entries):
    cmap = {}
    for e in entries:
        name = e.get("name", "").strip()
        if not name or len(name) < 2:
            continue
        nk = name_to_key(name)
        if nk in BLACKLIST:
            continue
        disp = re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]', '', name)
        disp = re.sub(r'\s+', '', disp)
        if nk not in cmap:
            cmap[nk] = {"name": disp if disp else name, "urls": []}
        ex = cmap[nk]
        if disp and disp != ex["name"] and re.search(r'[\d]+FPS', ex["name"], re.IGNORECASE):
            ex["name"] = disp
        for u in e.get("urls", []):
            if u not in ex["urls"]:
                ex["urls"].append(u)
    return list(cmap.values())

# ============================================================
# 排序 + 去重（白名单权重，同 ID 合并保留全部 URL）
# ============================================================
def sort_by_whitelist(channels):
    def norm_display(name):
        name = re.sub(r'^BRTV', '', name)
        m = re.search(r'CCTV[\s-]*(\d+)', name, re.IGNORECASE)
        if m:
            num = m.group(1)
            if 1 <= int(num) <= 17:
                return re.sub(r'CCTV[\s-]*\d+', f'CCTV-{num}', name)
        m2 = re.search(r'CETV[\s-]*(\d+)', name, re.IGNORECASE)
        if m2:
            num = m2.group(1)
            return re.sub(r'CETV[\s-]*\d+', f'CETV-{num}', name)
        return name

    for ch in channels:
        ch["name"] = norm_display(ch["name"])

    def sort_key(ch):
        wid = match_whitelist(ch["name"])
        return (WHITELIST_ORDER.get(wid, 999) if wid else 999, ch["name"])
    channels.sort(key=sort_key)

    by_wid = {}
    order = []
    for ch in channels:
        wid = match_whitelist(ch["name"]) or name_to_key(ch["name"])
        if wid in by_wid:
            prev = by_wid[wid]
            prev["urls"] = list(dict.fromkeys(prev.get("urls", []) + ch.get("urls", [])))
        else:
            by_wid[wid] = ch
            order.append(wid)
    return [by_wid[wid] for wid in order]

# ============================================================
# 输出生成
# ============================================================
def generate_m3u(channels, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in channels:
            name = ch["name"]
            for url in ch.get("urls", []):
                f.write(f'#EXTINF:-1 group-title="{SINGLE_GROUP}",{name}\n')
                f.write(f"{url}\n")

def generate_txt(channels, path):
    with open(path, "w", encoding="utf-8") as f:
        for ch in channels:
            for url in ch.get("urls", []):
                f.write(f'{ch["name"]},{url}\n')

def generate_tvbox_json(m3u_rel, path):
    RAW_BASE = "xu1152/tv-source-aggregator/master"
    nodes = [
        ("主线：极速加速节点",
         f"https://ghfast.top/https://raw.githubusercontent.com/{RAW_BASE}/{m3u_rel}",
         "http://epg.51zmt.top:8000/api/diyp/"),
        ("备用：稳定加速节点",
         f"https://raw.gitmirror.com/{RAW_BASE}/{m3u_rel}",
         ""),
        ("备用：GitHub 官方直连",
         f"https://raw.githubusercontent.com/{RAW_BASE}/{m3u_rel}",
         ""),
    ]
    config = {
        "spider": "",
        "sites": [{
            "key": "csp_MyLive",
            "name": f"{chr(0x1f4fa)} {SINGLE_GROUP}|长辈极简版",
            "type": 3,
            "api": "csp_XPath",
            "searchable": 0,
            "quickSearch": 0,
            "filterable": 0,
        }],
        "lives": []
    }
    for name, url, epg in nodes:
        entry = {"name": name, "type": 0, "url": url, "playerType": 1}
        if epg:
            entry["epg"] = epg
        config["lives"].append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def generate_json(channels, path):
    lives = []
    for ch in channels:
        lives.append({
            "name": ch["name"],
            "urls": ch.get("urls", []),
            "group": SINGLE_GROUP,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"lives": lives}, f, ensure_ascii=False, indent=2)

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  TV 直播源聚合器 v4 — 长辈极简版（零测速）")
    print("=" * 60)

    # 1. 拉取公开源
    all_entries = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for url, fmt in SOURCE_URLS:
            futures[pool.submit(fetch_text, url)] = (url, fmt)
        for fut in as_completed(futures):
            url, fmt = futures[fut]
            short = url.rsplit("/", 1)[-1]
            print(f"\n[FETCH] {short}")
            text = fut.result()
            if text is None:
                print("  [SKIP]")
                continue
            parser = parse_m3u if fmt == "m3u" else parse_txt
            entries = parser(text)
            print(f"  [OK] {len(entries)} 条")
            all_entries.extend(entries)

    print(f"\n{'=' * 60}")
    print(f"  拉取总计: {len(all_entries)} 条")

    # 2. 合并去重（保留全部 URL，不测速、不删除）
    merged = merge(all_entries)
    print(f"  去重后: {len(merged)} 个频道")

    # 3. 白名单过滤
    whitelisted = []
    unmatched = []
    for ch in merged:
        if match_whitelist(ch["name"]):
            whitelisted.append(ch)
        else:
            unmatched.append(ch)
    print(f"  白名单命中: {len(whitelisted)} | 淘汰: {len(unmatched)}")
    if unmatched:
        names = [ch["name"] for ch in unmatched]
        print(f"  淘汰列表: {', '.join(names)}")

    # 4. 注入硬编码黑龙江本地源
    print(f"\n  [LOCAL] 注入本地源: {len(LOCAL_SOURCES)} 个")
    for ls in LOCAL_SOURCES:
        whitelisted.append(dict(ls))
        print(f"    + {ls['name']}")

    # 5. 按白名单强排序（含同名去重）
    final = sort_by_whitelist(whitelisted)
    print(f"\n  最终频道 ({len(final)}):")
    for ch in final:
        urls = ch.get("urls", [])
        tag = "★" if any("111.40.205.87" in u for u in urls) else " "
        print(f"    {tag} {ch['name']}  ({len(urls)}条链路)")

    # 6. 输出
    sd = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(sd)

    json_path = os.path.join(root, OUTPUT_JSON)
    generate_json(final, json_path)
    print(f"\n[OUTPUT] {OUTPUT_JSON} ({os.path.getsize(json_path) / 1024:.1f} KB)")

    m3u_path = os.path.join(root, OUTPUT_M3U)
    generate_m3u(final, m3u_path)
    print(f"[OUTPUT] {OUTPUT_M3U} ({os.path.getsize(m3u_path) / 1024:.1f} KB)")

    txt_path = os.path.join(root, OUTPUT_TXT)
    generate_txt(final, txt_path)
    print(f"[OUTPUT] {OUTPUT_TXT} ({os.path.getsize(txt_path) / 1024:.1f} KB)")

    tvbox_path = os.path.join(root, OUTPUT_TVBOX)
    generate_tvbox_json(OUTPUT_M3U, tvbox_path)
    print(f"[OUTPUT] {OUTPUT_TVBOX} ({os.path.getsize(tvbox_path) / 1024:.1f} KB)")

    print("=" * 60)
    print(f"  长辈极简版 v4：{len(final)} 个频道，单一分类「{SINGLE_GROUP}」")
    print(f"  零测速 · 不删链 · 白名单强排序")
    print("=" * 60)

if __name__ == "__main__":
    main()
