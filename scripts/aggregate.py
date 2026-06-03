#!/usr/bin/env python3
"""
TV 直播源聚合 v5 — 长辈极简版（零测速）
白名单匹配 → 去重 → 硬编码注入 → 强排序 → 扁平化输出

设计哲学：
- 零测速、不删链、白名单精准强排序
- 海外 GitHub Actions 不依赖网络测速，名字匹配即保留全部链路
- 单一大类「电视直播」，目标 ~63 个精选频道

修复清单（v5 vs v4）：
  1. tvbox.json 改为内联频道 + dummy 防崩溃节点，不再用 M3U 外链
  2. Blacklist 逻辑修正（标准化 key 比对）
  3. 所有 import 提升至模块顶层
  4. ThreadPoolExecutor 异常全捕获
  5. show_name 标准化输出（CCTV1→CCTV-1, BRTV 前缀清理）
  6. ensure_ascii=False + indent=2 写入所有 JSON
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
# ║                        常    量                              ║
# ╚══════════════════════════════════════════════════════════════╝

OUTPUT_M3U   = "sources.m3u"
OUTPUT_TXT   = "sources.txt"
OUTPUT_JSON  = "sources.json"
OUTPUT_TVBOX = "tvbox.json"
SINGLE_GROUP = "电视直播"
TIMEOUT      = 15
MAX_WORKERS  = 8
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; TVBox/1.0)"}

# ╔══════════════════════════════════════════════════════════════╗
# ║                7 个公开直播源（仅拉取，不测速）              ║
# ╚══════════════════════════════════════════════════════════════╝

SOURCE_URLS = [
    # (url, 解析器类型)
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", "m3u"),
    ("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u",  "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u",         "m3u"),
    ("https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt",         "txt"),
    ("https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",       "m3u"),
    ("https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",           "m3u"),
    ("https://iptv-org.github.io/iptv/countries/cn.m3u",                       "m3u"),
]

# ╔══════════════════════════════════════════════════════════════╗
# ║         硬编码：黑龙江广电直连本地源（永不丢弃）             ║
# ╚══════════════════════════════════════════════════════════════╝

HLJ_LOCAL = [
    ("黑龙江都市",   "http://111.40.205.87/live/ds.m3u8"),
    ("黑龙江影视",   "http://111.40.205.87/live/ys.m3u8"),
    ("黑龙江文体",   "http://111.40.205.87/live/wt.m3u8"),
    ("哈尔滨综合",   "http://111.40.205.87/live/hrb1.m3u8"),
]

# ╔══════════════════════════════════════════════════════════════╗
# ║              白名单（列表顺序 = 最终排序）                   ║
# ║              格式: (唯一ID, [名称变体...])                   ║
# ║              目标: ~63 个频道                                ║
# ╚══════════════════════════════════════════════════════════════╝

WHITELIST = [
    # ── 第一军团：央视全阵列 (16) ──
    ("cctv1",     ["CCTV-1",  "CCTV1"]),
    ("cctv2",     ["CCTV-2",  "CCTV2"]),
    ("cctv3",     ["CCTV-3",  "CCTV3"]),
    ("cctv4",     ["CCTV-4",  "CCTV4"]),
    ("cctv5",     ["CCTV-5",  "CCTV5"]),
    ("cctv6",     ["CCTV-6",  "CCTV6"]),
    ("cctv7",     ["CCTV-7",  "CCTV7"]),
    ("cctv8",     ["CCTV-8",  "CCTV8"]),
    ("cctv9",     ["CCTV-9",  "CCTV9"]),
    ("cctv10",    ["CCTV-10", "CCTV10"]),
    ("cctv11",    ["CCTV-11", "CCTV11"]),
    ("cctv12",    ["CCTV-12", "CCTV12"]),
    ("cctv13",    ["CCTV-13", "CCTV13"]),
    ("cctv14",    ["CCTV-14", "CCTV14"]),
    ("cctv15",    ["CCTV-15", "CCTV15"]),
    ("cctv5plus", ["CCTV-5+", "CCTV5+", "CCTV5Plus"]),

    # ── 第二军团：中国教育台 (2) ──
    ("cetv1",     ["CETV-1", "CETV1", "中国教育1"]),
    ("cetv4",     ["CETV-4", "CETV4", "中国教育4"]),

    # ── 第三军团：黑龙江黄金阵营 (5) ──
    ("hlj_ws",    ["黑龙江卫视"]),
    ("hlj_ds",    ["黑龙江都市"]),
    ("hlj_ys",    ["黑龙江影视"]),
    ("hlj_wt",    ["黑龙江文体"]),
    ("hrb_zh",    ["哈尔滨综合", "哈尔滨新闻综合"]),

    # ── 第四军团：一线王牌卫视 (5) ──
    ("hunan",     ["湖南卫视"]),
    ("zhejiang",  ["浙江卫视"]),
    ("jiangsu",   ["江苏卫视"]),
    ("dongfang",  ["东方卫视", "DragonTV"]),
    ("beijing",   ["北京卫视"]),

    # ── 第五军团：其他 26 省级卫视 ──
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
    ("fujian",    ["东南卫视", "福建卫视"]),
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

    # ── 第六军团：精选专题频道 (9) ──
    ("qiusuodw",  ["求索动物"]),
    ("qiusuosh",  ["求索生活"]),
    ("qiusuokx",  ["求索科学"]),
    ("qiusuo",    ["求索纪录"]),
    ("jingbao",   ["劲爆体育"]),
    ("kaku",      ["卡酷少儿", "卡酷", "BTV卡酷少儿"]),
    ("youman",    ["优漫卡通", "优漫"]),
    ("jinying",   ["金鹰卡通", "金鹰"]),
    ("haha",      ["哈哈炫动", "哈哈"]),
]

# ╔══════════════════════════════════════════════════════════════╗
# ║                   运行时匹配表构建                            ║
# ╚══════════════════════════════════════════════════════════════╝

def _norm(s):
    """Unicode NFKC 标准化 + 大写 + 去符号去空白"""
    s = unicodedata.normalize("NFKC", s.upper())
    s = re.sub(r'[-_（）()【】\[\]\s·•\.\u200b-\u200d\ufeff]', "", s)
    return s

def _name_key(name):
    return _norm(name)

def _build_matcher():
    """构建模糊匹配列表（长优先）和排序权重"""
    items = []
    for wid, keywords in WHITELIST:
        for kw in keywords:
            items.append((_norm(kw), wid))
    items.sort(key=lambda x: -len(x[0]))  # 长关键词优先匹配
    order = {wid: i for i, (wid, _) in enumerate(WHITELIST)}
    return items, order

MATCH_LIST, WHITELIST_ORDER = _build_matcher()

# wid → 首选显示名（白名单第一变体）
WHITELIST_DICT = {wid: keywords for wid, keywords in WHITELIST}

# 黑名单：标准化 key 集合
BLACKLIST_KEYS = {
    _norm(s) for s in [
        "CCTV16", "CCTV-16", "CCTV17", "CCTV-17",
        "CCTV-9(I)", "CCTV9I", "DRAGONTVINTERNATIONAL",
    ]
}

# ╔══════════════════════════════════════════════════════════════╗
# ║                    频道清洗 & 匹配                           ║
# ╚══════════════════════════════════════════════════════════════╝

JUNK_KW = [
    "免费订阅", "公告说明", "维护", "请勿贩卖", "#佛系维护",
    "删除", "IPV6暂无", "测试", "TEST", "购物", "SHOPPING",
    "电视购物", "轮播", "循环", "广播", "RADIO",
]

def clean_name(raw):
    """清洗原始名称 → 干净名称；返回空串表示垃圾频道"""
    name = raw.strip()
    if len(name) < 2:
        return ""
    # 垃圾关键词
    for jk in JUNK_KW:
        if jk.upper() in name.upper():
            return ""
    # 去清晰度标记
    name = re.sub(r'\s*[\[\(]?\d{3,4}[pP][\]\)]?\s*', '', name)
    name = re.sub(r'\s*-\s*\d{3,4}[pP]?\s*', '', name)
    name = re.sub(
        r'\s*(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|1080|720|2160|576|HEVC|50FPS|60FPS)\s*',
        '', name
    )
    for tag in ["[Not24/7]", "[Geo-blocked]", "[Offline]", "[Geo-block]"]:
        name = name.replace(tag, "")
    name = name.strip()
    return name if len(name) >= 2 else ""


def match_whitelist(name):
    """模糊匹配白名单，返回频道 ID；None = 未命中"""
    key = _name_key(name)
    for kw_norm, wid in MATCH_LIST:
        pos = key.find(kw_norm)
        if pos == -1:
            continue
        # 避免 "CCTV1" 误匹配 "CCTV10"：检查匹配位置后续字符
        if wid.startswith("cctv") and kw_norm[-1].isdigit():
            after = pos + len(kw_norm)
            if after < len(key) and key[after].isdigit():
                continue
        return wid
    return None


def normalize_display(name):
    """统一显示名称：CCTV1→CCTV-1 / CETV1→CETV-1 / 去 BRTV 前缀"""
    # CCTV
    m = re.search(r'CCTV[\s-]*(\d+)', name, re.IGNORECASE)
    if m:
        num = m.group(1)
        if 1 <= int(num) <= 17:
            return re.sub(r'CCTV[\s-]*\d+', f'CCTV-{num}', name)
    # CETV
    m = re.search(r'CETV[\s-]*(\d+)', name, re.IGNORECASE)
    if m:
        num = m.group(1)
        return re.sub(r'CETV[\s-]*\d+', f'CETV-{num}', name)
    # BRTV 前缀
    name = re.sub(r'^BRTV', '', name)
    return name

# ╔══════════════════════════════════════════════════════════════╗
# ║                    网络拉取 & 解析                           ║
# ╚══════════════════════════════════════════════════════════════╝

def fetch_text(url):
    """拉取远程文本，自动识别编码"""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        for enc in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARN {url.rsplit('/', 1)[-1]}: {e}", file=sys.stderr)
        return None


def parse_m3u(text):
    """解析 M3U 直播源格式"""
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
                results.append({"name": cur["name"], "url": line.strip()})
            cur = {}
    return results


def parse_txt(text):
    """解析 TXT 直播源格式（name,url 或 name,url#genre#）"""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace(",#genre#", "")
        p = line.split(",", 1)
        if len(p) != 2:
            continue
        name = clean_name(p[0].strip())
        url  = p[1].strip()
        if not name or not url:
            continue
        if not (url.startswith("http") or url.startswith("rtmp") or url.startswith("rtp")):
            continue
        results.append({"name": name, "url": url})
    return results

# ╔══════════════════════════════════════════════════════════════╗
# ║                合并去重（不测速 · 不删链）                   ║
# ╚══════════════════════════════════════════════════════════════╝

def merge_and_dedup(entries):
    """
    合并频道（按白名单 ID 分组）：
    - 白名单匹配 → 按 wid 合并
    - 未匹配的丢弃
    - 黑名单过滤
    - 返回 {wid: {"name": display_name, "urls": [...], "_order": priority}}
    """
    cmap = {}
    for e in entries:
        name = e.get("name", "").strip()
        url  = e.get("url",  "").strip()
        if not name or not url:
            continue
        nk = _name_key(name)
        if nk in BLACKLIST_KEYS:
            continue
        # 白名单匹配
        wid = match_whitelist(name)
        if not wid:
            continue  # 非白名单频道直接丢弃
        # 显示名清洗
        disp = re.sub(r'[\d０-９]+\s*[FＦfｆ][PＰpｐ][SＳsｓ]', '', name)
        disp = re.sub(r'\s+', '', disp)
        if wid not in cmap:
            cmap[wid] = {"name": disp, "urls": [], "_order": WHITELIST_ORDER.get(wid, 999)}
        existing = cmap[wid]
        # 选最短最干净的名字
        if len(disp) < len(existing["name"]):
            existing["name"] = disp
        if url not in existing["urls"]:
            existing["urls"].append(url)
    return cmap

# ╔══════════════════════════════════════════════════════════════╗
# ║                白名单过滤 + 强排序                           ║
# ╚══════════════════════════════════════════════════════════════╝

def sort_channels(merged):
    """标准化显示名 → 归一化为白名单首选名 → 按白名单顺序排序"""
    result = []
    for wid, data in merged.items():
        # 用白名单第一个变体（如 CCTV-1）作为显示名
        whitelist_names = WHITELIST_DICT.get(wid)
        if whitelist_names:
            data["name"] = whitelist_names[0]
        else:
            data["name"] = normalize_display(data["name"])
        result.append(data)
    result.sort(key=lambda x: x.get("_order", 999))
    for r in result:
        r.pop("_order", None)
    return result

# ╔══════════════════════════════════════════════════════════════╗
# ║                    注入硬编码本地源                           ║
# ╚══════════════════════════════════════════════════════════════╝

def inject_local(channels):
    """
    注入黑龙江本地源：
    - 如果频道已存在 → 追加 URL
    - 如果频道不存在 → 追加新频道
    返回注入后的 channels 列表（已重新排序）
    """
    for name, url in HLJ_LOCAL:
        wid = match_whitelist(name)
        found = False
        for ch in channels:
            if _name_key(ch["name"]) == _name_key(name) or (wid and match_whitelist(ch.get("_ref_name", ch["name"])) == wid):
                if url not in ch["urls"]:
                    ch["urls"].append(url)
                found = True
                print(f"    + {name} (追加到已有)")
                break
        if not found:
            new_ch = {"name": name, "urls": [url]}
            # 找到插入位置
            new_order = WHITELIST_ORDER.get(wid, 999)
            channels.append(new_ch)
            print(f"    ** {name} (** 新建)")

    # 重新排序
    for ch in channels:
        ch["_order"] = WHITELIST_ORDER.get(match_whitelist(ch["name"]), 999)
    channels.sort(key=lambda x: x.get("_order", 999))
    for ch in channels:
        ch.pop("_order", None)
    return channels

# ╔══════════════════════════════════════════════════════════════╗
# ║                    文件输出生成                               ║
# ╚══════════════════════════════════════════════════════════════╝

def _write_json(data, path):
    """统一 JSON 写入：UTF-8 · 无 Unicode 转义 · 2 空格缩进"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_json_flat(channels, path):
    """
    标准扁平 JSON（sources.json）
    同名多源 → 展开为多条独立记录
    """
    flat = []
    for ch in channels:
        for u in ch.get("urls", []):
            flat.append({"name": ch["name"], "url": u})
    data = {
        "spider": "",
        "sites": [],
        "lives": [{"group": SINGLE_GROUP, "channels": flat}],
    }
    _write_json(data, path)


def write_tvbox(channels, path):
    """
    tvbox.json 主入口：
    - dummy 假站点防 UI 闪退
    - lives 内联全部频道（不依赖外部 M3U）
    - 单频道多源用 urls 数组（主流 TVBox 格式）
    """
    inline = []
    for ch in channels:
        inline.append({
            "name": ch["name"],
            "urls": list(ch.get("urls", [])),
        })
    data = {
        "spider": "",
        "sites": [
            {
                "key":        "dummy",
                "name":       "占位防崩溃",
                "type":       3,
                "api":        "",
                "searchable": 0,
            }
        ],
        "lives": [{"group": SINGLE_GROUP, "channels": inline}],
    }
    _write_json(data, path)


def write_m3u(channels, path):
    """M3U 格式"""
    lines = ["#EXTM3U"]
    for ch in channels:
        for url in ch.get("urls", []):
            lines.append(f'#EXTINF:-1 group-title="{SINGLE_GROUP}",{ch["name"]}')
            lines.append(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_txt(channels, path):
    """TXT 格式（名称,URL）"""
    lines = []
    for ch in channels:
        for url in ch.get("urls", []):
            lines.append(f'{ch["name"]},{url}')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

# ╔══════════════════════════════════════════════════════════════╗
# ║                       主    流    程                          ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    print("=" * 60)
    print("  TV 直播源聚合器 v5 — 长辈极简版（零测速）")
    print("=" * 60)

    # ── 1. 并行拉取 7 个公开源 ──
    all_entries = []
    fetch_ok = 0
    fetch_fail = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for url, fmt in SOURCE_URLS:
            futures[pool.submit(fetch_text, url)] = (url, fmt)
        for fut in as_completed(futures):
            url, fmt = futures[fut]
            short = url.rsplit("/", 1)[-1]
            print(f"\n[FETCH] {short}")
            try:
                text = fut.result()
            except Exception as e:
                print(f"  ERR 线程异常: {e}", file=sys.stderr)
                fetch_fail += 1
                continue
            if text is None:
                print(f"  ⊘ 网络不可达，跳过")
                fetch_fail += 1
                continue
            parser = parse_m3u if fmt == "m3u" else parse_txt
            entries = parser(text)
            print(f"  OK {len(entries)} 条")
            all_entries.extend(entries)
            fetch_ok += 1

    print(f"\n{'='*60}")
    print(f"  拉取成功: {fetch_ok}/{len(SOURCE_URLS)} | 原始条目: {len(all_entries)}")

    # ── 2. 合并去重 ──
    merged = merge_and_dedup(all_entries)
    print(f"  合并去重: {len(merged)} 个唯一频道")

    # ── 3. 白名单过滤 + 排序 ──
    sorted_ch = sort_channels(merged)
    print(f"  白名单命中: {len(sorted_ch)} 个")

    # ── 4. 注入硬编码黑龙江本地源 ──
    print(f"\n  [LOCAL] 注入本地源 ({len(HLJ_LOCAL)} 个):")
    sorted_ch = inject_local(sorted_ch)

    # ── 打印清单 ──
    url_total = sum(len(ch.get("urls", [])) for ch in sorted_ch)
    print(f"\n  >> 最终频道 ({len(sorted_ch)} 个 · {url_total} 条链路):")
    for i, ch in enumerate(sorted_ch, 1):
        ul = ch.get("urls", [])
        star = "**" if any("111.40.205.87" in u for u in ul) else " "
        print(f"    {i:2d}. {star} {ch['name']}  ({len(ul)}条)")

    # ── 5. 输出文件到仓库根目录 ──
    sd   = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(sd) if os.path.basename(sd) == "scripts" else sd

    files = [
        (OUTPUT_JSON,  write_json_flat, "扁平 JSON（供 GitHub Actions 参考）"),
        (OUTPUT_TVBOX, write_tvbox,     "TVBox 主入口（内联 urls 数组 + 防崩溃）"),
        (OUTPUT_M3U,   write_m3u,       "M3U 标准格式"),
        (OUTPUT_TXT,   write_txt,       "TXT 纯文本格式"),
    ]

    for fname, writer, desc in files:
        fpath = os.path.join(root, fname)
        writer(sorted_ch, fpath)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"\n[OUTPUT] {fname}  ({size_kb:.1f} KB) — {desc}")

    print(f"\n{'='*60}")
    print(f"  ==> 聚合完成！{len(sorted_ch)} 频道 · {url_total} 链路 · 零测速")
    print(f"  单一大类「{SINGLE_GROUP}」· 白名单强排序 · tvbox.json 即插即用")
    print("=" * 60)


if __name__ == "__main__":
    main()
