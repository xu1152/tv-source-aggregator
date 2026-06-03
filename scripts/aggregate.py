#!/usr/bin/env python3
"""
TV 直播源聚合 v3 — 长辈极简版
白名单匹配 → 测速过滤(1.5s) → 单分类排序 → 多格式输出
"""
import json, re, os, sys, socket
from urllib.request import urlopen, Request
from urllib.error import URLError
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# 输出文件
# ============================================================
OUTPUT_JSON  = "sources.json"
OUTPUT_M3U   = "sources.m3u"
OUTPUT_TXT   = "sources.txt"
OUTPUT_TVBOX = "tvbox.json"

TIMEOUT = 15       # 源拉取超时(秒)
MAX_WORKERS = 8    # 并发拉取
SPEED_TIMEOUT = 2.0  # 测速超时(秒, TCP connect)

# ============================================================
# 直播源列表
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
# 分类：唯一分类
# ============================================================
SINGLE_GROUP = "电视直播"

# ============================================================
# 白名单：按梯队排序，key=匹配关键词列表
# ============================================================
WHITELIST = [
    # 第一梯队：中央台 CCTV-1~15
    ("cctv1",  ["CCTV-1", "CCTV1"]),
    ("cctv2",  ["CCTV-2", "CCTV2"]),
    ("cctv3",  ["CCTV-3", "CCTV3"]),
    ("cctv4",  ["CCTV-4", "CCTV4"]),
    ("cctv5",  ["CCTV-5", "CCTV5"]),
    ("cctv6",  ["CCTV-6", "CCTV6"]),
    ("cctv7",  ["CCTV-7", "CCTV7"]),
    ("cctv8",  ["CCTV-8", "CCTV8"]),
    ("cctv9",  ["CCTV-9", "CCTV9"]),
    ("cctv10", ["CCTV-10", "CCTV10"]),
    ("cctv11", ["CCTV-11", "CCTV11"]),
    ("cctv12", ["CCTV-12", "CCTV12"]),
    ("cctv13", ["CCTV-13", "CCTV13"]),
    ("cctv14", ["CCTV-14", "CCTV14"]),
    ("cctv15", ["CCTV-15", "CCTV15"]),
    ("cctv5plus", ["CCTV-5+", "CCTV5+", "CCTV5Plus"]),
    ("cetv1",     ["CETV-1", "CETV1", "中国教育1"]),
    ("cetv4",     ["CETV-4", "CETV4", "中国教育4"]),

    # 第二梯队：顶流卫视
    ("hunan",    ["湖南卫视"]),
    ("zhejiang", ["浙江卫视"]),
    ("jiangsu",  ["江苏卫视"]),
    ("dongfang", ["东方卫视", "DragonTV"]),

    # 第三梯队：老家频道（黑龙江）
    ("hlj_ws",   ["黑龙江卫视"]),
    ("hlj_ds",   ["黑龙江都市"]),
    ("hlj_ys",   ["黑龙江影视"]),
    ("hlj_wt",   ["黑龙江文体"]),
    ("hlj_xw",   ["黑龙江新闻"]),
    ("hlj_gg",   ["黑龙江公共"]),
    ("hlj_nync", ["黑龙江农业", "黑龙江·农业"]),
    ("hrb_zh",   ["哈尔滨综合", "哈尔滨新闻综合"]),
    ("hrb_ys",   ["哈尔滨影视"]),
    ("hrb_sh",   ["哈尔滨生活"]),

    # 第四梯队：其他主流卫视
    ("beijing",    ["北京卫视"]),
    ("anhui",      ["安徽卫视"]),
    ("shandong",   ["山东卫视"]),
    ("guangdong",  ["广东卫视"]),
    ("shenzhen",   ["深圳卫视"]),
    ("liaoning",   ["辽宁卫视"]),
    ("henan",      ["河南卫视"]),
    ("hubei",      ["湖北卫视"]),
    ("jiangxi",    ["江西卫视"]),
    ("sichuan",    ["四川卫视"]),
    ("chongqing",  ["重庆卫视"]),
    ("tianjin",    ["天津卫视"]),
    ("hebei",      ["河北卫视"]),
    ("fujian",     ["福建卫视", "东南卫视"]),
    ("guangxi",    ["广西卫视"]),
    ("shanxi",     ["山西卫视"]),
    ("shan3xi",    ["陕西卫视"]),
    ("hainan",     ["海南卫视"]),
    ("guizhou",    ["贵州卫视"]),
    ("yunnan",     ["云南卫视"]),
    ("gansu",      ["甘肃卫视"]),
    ("jilin",      ["吉林卫视"]),
    ("neimenggu",  ["内蒙古卫视"]),
    ("ningxia",    ["宁夏卫视"]),
    ("xinjiang",   ["新疆卫视"]),
    ("xizang",     ["西藏卫视"]),
    ("qinghai",    ["青海卫视"]),

    # 第五梯队：热门数字/专题频道
    ("fengyunzy",  ["风云足球", "CCTV风云足球"]),
    ("fengyunjq",  ["风云剧场", "CCTV风云剧场"]),
    ("fengyunyy",  ["风云音乐", "CCTV风云音乐"]),
    ("qiusuodw",   ["求索动物"]),
    ("qiusuosh",   ["求索生活"]),
    ("qiusuokx",   ["求索科学"]),
    ("qiusuo",     ["求索纪录"]),
    ("dyjc",       ["第一剧场", "CCTV第一剧场"]),
    ("hxjc",       ["怀旧剧场", "CCTV怀旧剧场"]),
    ("shijiedl",   ["世界地理", "CCTV世界地理"]),
    ("guofang",    ["国防军事", "CCTV国防军事"]),
    ("nxss",       ["女性时尚", "CCTV女性时尚"]),
    ("xiangsyds",  ["央视文化精品", "文化精品"]),
    ("zqjf",       ["早教频道", "早期教育"]),
    ("jjjy",       ["劲爆体育"]),
    ("xdfc",       ["幸福彩"]),
    ("chcjt",      ["CHC家庭影院"]),
    ("chcdz",      ["CHC动作电影"]),
    ("chcgq",      ["CHC高清电影"]),
    ("youman",     ["优漫卡通"]),
    ("jinying",    ["金鹰卡通"]),
    ("haha",       ["哈哈炫动"]),
    ("kaku",       ["卡酷少儿"]),
]

# 构建名称匹配映射
MATCH_MAP = None  # 延迟构建

def _build_match_list():
    """构建关键词→ID 列表，按关键词长度降序（优先长匹配）"""
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

# 垃圾关键词：匹配到直接丢弃
JUNK_KW = [
    "免费订阅", "公告说明", "维护", "请勿贩卖", "#佛系维护",
    "删除", "IPV6暂无", "CCTV+", "TEST", "测试",
    "购物", "SHOPPING", "电视购物", "轮播", "循环",
    "广播", "RADIO",
]
# 黑名单：归一化后的频道名，直接丢掉
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
    # 垃圾过滤
    for jk in JUNK_KW:
        if jk.upper() in name.upper():
            return ""
    # 去分辨率标签
    name = re.sub(r'\s*[\[\(]?\d{3,4}[pP][\]\)]?\s*', '', name)
    name = re.sub(r'\s*-\s*\d{3,4}[pP]?\s*', '', name)
    # 去画质标签
    name = re.sub(r'\s*(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|1080|720|2160|576|HEVC|50FPS|60FPS)\s*', '', name)
    # 去状态标签
    for tag in ['[Not24/7]', '[Geo-blocked]', '[Offline]', '[Geo-block]']:
        name = name.replace(tag, '')
    # 合并空白
    name = re.sub(r'\s+', '', name)
    return name


def name_to_key(name):
    """归一化为匹配用的 key，含 Unicode 归一化 + 画质后缀剥离"""
    import unicodedata
    n = unicodedata.normalize('NFKC', name.upper())
    n = re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]', '', n)
    n = re.sub(r'[\d０-９]+\s*[PＰpｐ]\b', '', n)
    n = re.sub(r'[-_（）()【】\[\]\s·•\.\u200b\u200c\u200d\ufeff]', '', n)
    return n


def match_whitelist(name):
    """子串匹配白名单关键词，CCTV 数字不跨界匹配。"""
    key = name_to_key(name)
    for kw_norm, wid in MATCH_LIST:
        pos = key.find(kw_norm)
        if pos == -1:
            continue
        # CCTV 频道：关键词后不能紧跟数字（防止CCTV1误匹配CCTV16）
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
# 合并去重
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
        key = nk
        # 去画质后缀得到显示名
        disp = re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]','',name)
        disp = re.sub(r'\s+','',disp)
        if key not in cmap:
            cmap[key] = {"name": disp if disp else name, "urls": []}
        ex = cmap[key]
        # 优先用不带画质后缀的显示名
        if disp and disp != ex["name"]:
            if not re.search(r'[\d]+FPS', ex["name"], re.IGNORECASE):
                pass  # 当前名已经很干净
            else:
                ex["name"] = disp
        for u in e.get("urls", []):
            if u not in cmap[key]["urls"]:
                cmap[key]["urls"].append(u)
    return list(cmap.values())


# ============================================================
# 测速（HTTP HEAD，1.5s 超时）
# ============================================================
def test_url(url):
    """TCP 连接测速，返回延迟(秒)，失败返回 None"""
    from urllib.parse import urlparse
    import time
    try:
        p = urlparse(url)
        host = p.hostname
        port = p.port or (443 if p.scheme == 'https' else 80)
        start = time.time()
        sock = socket.create_connection((host, port), timeout=SPEED_TIMEOUT)
        sock.close()
        elapsed = time.time() - start
        return elapsed if elapsed < SPEED_TIMEOUT else None
    except Exception:
        return None


def speed_test_channels(channels):
    """对每个频道测所有 URL，任一可达即保留；保留最先通的 URL。"""
    alive = []
    dead = 0
    total = len(channels)
    print(f"\n  [测速] {total} 个频道, TCP连接超时 {SPEED_TIMEOUT}s ...")

    # 展开所有(channel, url)对
    tasks = []
    for ch in channels:
        for url in ch.get("urls", []):
            tasks.append((ch, url))

    with ThreadPoolExecutor(max_workers=30) as pool:
        futures = {pool.submit(test_url, url): (ch, url) for ch, url in tasks}

        # 每个频道取最快可达的 URL
        ch_results = {}  # id(ch) -> (latency, url)
        for fut in as_completed(futures):
            ch, url = futures[fut]
            cid = id(ch)
            latency = fut.result()
            if latency is not None:
                if cid not in ch_results or latency < ch_results[cid][0]:
                    ch_results[cid] = (latency, url)

    for ch in channels:
        cid = id(ch)
        if cid in ch_results:
            latency, best_url = ch_results[cid]
            # 把最快的 URL 放第一位
            urls = ch.get("urls", [])
            if best_url in urls:
                urls.remove(best_url)
            ch["urls"] = [best_url] + urls
            ch["latency"] = round(latency, 2)
            alive.append(ch)
        else:
            dead += 1

    alive.sort(key=lambda x: x.get("latency", 99))
    print(f"  [测速] 存活: {len(alive)} | 超时/死链: {dead}")
    return alive, dead


# ============================================================
# 按白名单排序
# ============================================================
def sort_by_whitelist(channels):
    """按白名单顺序排列 + 去重；统一 CCTV 显示名"""
    # 统一 CCTV 显示名：CCTV1 → CCTV-1
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

    # 按白名单 ID 去重（同一 whitelist 只保留延迟最低）
    by_wid = {}
    order = []
    for ch in channels:
        wid = match_whitelist(ch["name"]) or name_to_key(ch["name"])
        if wid in by_wid:
            prev = by_wid[wid]
            if ch.get("latency", 99) < prev.get("latency", 99):
                prev["urls"] = list(dict.fromkeys(prev.get("urls",[]) + ch.get("urls",[])))
                prev["latency"] = round(min(ch.get("latency", 99), prev.get("latency", 99)), 2)
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
    print("  TV 直播源聚合器 v3 — 长辈极简版")
    print("=" * 60)

    # 1. 拉取
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

    # 2. 合并去重
    merged = merge(all_entries)
    print(f"  去重后: {len(merged)} 个频道")

    # 3. 白名单过滤
    whitelisted = []
    unmatched = []
    for ch in merged:
        wid = match_whitelist(ch["name"])
        if wid:
            whitelisted.append(ch)
        else:
            unmatched.append(ch)
    print(f"  白名单命中: {len(whitelisted)} | 淘汰: {len(unmatched)}")
    if unmatched:
        names = [ch["name"] for ch in unmatched]
        print(f"  淘汰列表: {', '.join(names)}")

    # 4. 测速过滤
    alive, dead = speed_test_channels(whitelisted)

    # 5. 按白名单排序
    alive = sort_by_whitelist(alive)
    print(f"\n  最终频道 ({len(alive)}):")
    for ch in alive:
        lt = f"{ch.get('latency','?')}s"
        print(f"    {lt:>6}  {ch['name']}")

    # 6. 输出
    sd = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(sd)

    json_path = os.path.join(root, OUTPUT_JSON)
    generate_json(alive, json_path)
    print(f"\n[OUTPUT] {OUTPUT_JSON} ({os.path.getsize(json_path) / 1024:.1f} KB)")

    m3u_path = os.path.join(root, OUTPUT_M3U)
    generate_m3u(alive, m3u_path)
    print(f"[OUTPUT] {OUTPUT_M3U} ({os.path.getsize(m3u_path) / 1024:.1f} KB)")

    txt_path = os.path.join(root, OUTPUT_TXT)
    generate_txt(alive, txt_path)
    print(f"[OUTPUT] {OUTPUT_TXT} ({os.path.getsize(txt_path) / 1024:.1f} KB)")

    tvbox_path = os.path.join(root, OUTPUT_TVBOX)
    generate_tvbox_json(OUTPUT_M3U, tvbox_path)
    print(f"[OUTPUT] {OUTPUT_TVBOX} ({os.path.getsize(tvbox_path) / 1024:.1f} KB)")

    print("=" * 60)
    print(f"  长辈极简版：{len(alive)} 个频道，单一分类「{SINGLE_GROUP}」")
    print(f"  无脑按下键 → 从头看到尾")
    print("=" * 60)


if __name__ == "__main__":
    main()
