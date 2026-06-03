#!/usr/bin/env python3
"""TV 直播源聚合 — 多源拉取→合并去重→TVBox JSON"""
import json, re, os, sys
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT_FILE = "sources.json"
TIMEOUT = 15; MAX_WORKERS = 8

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
GROUP_ORDER = {"央视频道":0,"卫视频道":1,"地方频道":2,"数字频道":3,"体育频道":4,"少儿频道":5,"国际频道":6,"其他频道":7}

# 垃圾条目过滤关键词
JUNK_KW = ["免费订阅","公告说明","维护内容","维护时间","请勿贩卖","IPV6暂无","#佛系维护","删除·IPV6"]

def fetch_text(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        for enc in ["utf-8","gbk","gb2312","utf-8-sig"]:
            try: return raw.decode(enc)
            except: continue
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] {url} -> {e}", file=sys.stderr)
        return None

def guess_group(name):
    n = name.strip(); nu = n.upper()

    # 央视系
    if re.search(r'CCTV', nu): return "央视频道"
    if re.search(r'CETV\s*[-\s]?\s*\d', nu): return "央视频道"
    if '中国教育' in n: return "央视频道"

    # 卫视系
    if '卫视' in n: return "卫视频道"
    for kw in ['TVB','凤凰','星空','澳亚','明珠','翡翠','华娱','阳光','莲花','本港',
               'ATV','中天','东森','三立','民视','台视','华视','公视','大爱','人间',
               'DragonTV','BreadTV']:
        if kw in n: return "卫视频道"
    # 英文卫视名 (省级卫视)
    sat_kw = ['ShenzhenSatellite','AnhuiTV','BeijingTV','ChongqingTV','FujianTV','GansuTV','GuangdongTV',
              'GuangxiTV','GuizhouTV','HainanTV','HebeiTV','HeilongjiangTV','HenanTV',
              'HubeiTV','HunanTV','JiangsuTV','JiangxiTV','JilinTV','LiaoningTV',
              'NeiMonggolTV','NingxiaTV','QinghaiTV','ShaanxiTV','ShandongTV',
              'ShanxiTV','SichuanTV','TianjinTV','XinjiangTV','XizangTV','YunnanTV',
              'ZhejiangTV','SZTV','BRTV','SMG']
    for kw in sat_kw:
        if kw.upper() in nu: return "卫视频道"
    # 陕西农林卫视
    if 'ShaanxiAgroforestry' in n: return "卫视频道"

    # 体育
    for kw in ['体育','足球','篮球','电竞','高尔夫','网球','搏击','SPORT','英超','NBA',
               '中超','CBA','欧冠','F1','格斗','赛车','拳击','台球','乒乓','羽毛球',
               '冰雪','垂钓','钓鱼','FISHING','咪咕']:
        if kw.upper() in nu: return "体育频道"
    if '晴彩竞技' in n or '睛彩竞技' in n: return "体育频道"

    # 少儿
    for kw in ['少儿','动漫','卡通','幼儿','亲子','青少','KIDS','ANIMATION','CARTOON',
               '金鹰卡通','炫动卡通','优漫','迪士尼','DISNEY','尼克','NICK','宝宝',
               '哈哈炫动','动画']:
        if kw.upper() in nu: return "少儿频道"
    if '晴彩少年' in n: return "少儿频道"

    # 国际
    for kw in ['CGTN','CNN','BBC','NHK','KBS','FRANCE','DW','半岛','彭博','BLOOMBERG',
               'EURONEWS','ALJAZEERA','CNBC','RT ','FOX','SKYNEWS','ARIRANG',
               'TV5MONDE','CHANNELNEWSASIA','VOA']:
        if kw.upper() in nu: return "国际频道"

    # 地方台
    local_kw = ['北京','上海','广东','深圳','浙江','江苏','湖南','湖北','四川','重庆',
                '天津','山东','河南','河北','福建','安徽','辽宁','陕西','江西','广西',
                '山西','云南','贵州','甘肃','海南','宁夏','青海','西藏','内蒙古','新疆',
                '黑龙江','吉林','CHC','城市','都市','公共','经济','综合','新闻',
                '文旅','影视','生活','教育','科教','农业','文化','政法','女性',
                '商务资讯','丝路','农牧','文体']
    for kw in local_kw:
        if kw in n: return "地方频道"
    # 各地电视台
    tvt_kw = ['电视台','萍鄉']
    for kw in tvt_kw:
        if kw in n: return "地方频道"
    # 英文拼音地方台
    local_en = ['JiangxiCity','JiangxiEconomy','JiangxiPublic','STVCity',
                'STVNews','QTV-','SipingTV','Anshun','Chifeng','GuangzhouTV',
                'Harbin','PingYu','JilinCity','JilinLifestyle','LiangshanTV',
                'Nanchang','Tonghua']
    for kw in local_en:
        if kw in n: return "地方频道"

    # 数字频道 (各类专题/付费)
    d_kw = ['风云','求索','纪实','探索','DISCOVERY','地理','法治','兵器','军事',
            '戏曲','MUSIC','MV','怀旧','老故事','文物','书画','靓妆','卫生健康',
            'NATIONALGEOGRAPHIC','DOCUMENTARY','HISTORY','SCIENCE','EDUCATION',
            'RELIGIOUS','GAME','游戏','电影','MOVIE','影院','剧场','财经','证券',
            '理财','购物','SHOP','生活','旅游','TRAVEL','美食','FOOD','时尚',
            'FASHION','汽车','AUTO','宠物','ENTERTAINMENT','COMEDY','CLASSIC',
            'NewTV','iHOT','CCTV-Culture','CCTV-Health','CCTV-Nostalgia',
            'CCTV-Women','WorldEconomy','YicaiTV','中国交通','中国天气','中国气象',
            '光影','星影','重温经典','金色学堂','七彩戏剧','魅力音乐','华数',
            '睛彩广场舞','晴彩广场舞','爱上','纯享','精选','茶','靓',
            '天元','劲爆','极速','先锋','乒羽','汽摩','电竞','围棋',
            '世界地理','发现之旅','中学生','优漫卡通','金鹰纪实','欢笑','乐游',
            '求索','全纪实']
    for kw in d_kw:
        if kw.upper() in nu: return "数字频道"

    return "其他频道"

def normalize_name(name):
    name = name.strip()
    # 过滤垃圾条目
    for jk in JUNK_KW:
        if jk in name: return ""
    name = re.sub(r'\s*[\[\(]?\d{3,4}[pP][\]\)]?\s*','',name)
    name = re.sub(r'\s*-\s*\d{3,4}[pP]?\s*','',name)
    name = re.sub(r'\s*(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|1080|720|2160|576|HEVC)\s*','',name)
    name = re.sub(r'\[Not24/7\]','',name)
    name = re.sub(r'\[Geo-blocked\]','',name)
    name = re.sub(r'\[Offline\]','',name)
    name = re.sub(r'\s+','',name)
    return name

def norm_key(name):
    n = name.strip().upper()
    n = re.sub(r'[_\s\-·•\.\u3000【】\[\]\(\)（）]','',n)
    n = re.sub(r'(高清|超清|标清|蓝光|4K|8K|HD|FHD|UHD|SD|HEVC|50FPS|60FPS)','',n)
    return n

def parse_m3u(text):
    results = []; cur = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            cur = {}
            for key in ["tvg-name","tvg-id","tvg-logo","group-title"]:
                m = re.search(rf'{key}="([^"]*)"', line)
                if m: cur[key] = m.group(1).strip()
            if "," in line:
                name = line.rsplit(",",1)[-1].strip()
            else:
                name = cur.get("tvg-name","").strip()
            if name and not re.match(r'^\d{4,}$',name):
                nname = normalize_name(name)
                if nname: cur["name"] = nname
        elif line and not line.startswith("#"):
            if cur.get("name"):
                g = guess_group(cur.get("group-title",""))
                if g == "其他频道": g = guess_group(cur["name"])
                results.append({"name":cur["name"],"urls":[line.strip()],"group":g,"logo":cur.get("tvg-logo","")})
            cur = {}
    return results

def parse_txt(text):
    results = []; cg = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if ",#genre#" in line: cg = line.replace(",#genre#","").strip(); continue
        p = line.split(",",1)
        if len(p)==2:
            name = normalize_name(p[0].strip()); url = p[1].strip()
            if name and url and (url.startswith("http") or url.startswith("rtmp")):
                g = guess_group(cg)
                if g == "其他频道": g = guess_group(name)
                results.append({"name":name,"urls":[url],"group":g,"logo":""})
    return results

def merge(entries):
    cmap = {}
    for e in entries:
        name = e.get("name","").strip()
        if not name or len(name)<2: continue
        key = norm_key(name)
        if key not in cmap:
            cmap[key] = {"name":name,"urls":[],"group":e.get("group","其他频道"),"logo":e.get("logo","")}
        ex = cmap[key]
        for u in e.get("urls",[]):
            if u not in ex["urls"]: ex["urls"].append(u)
        if e.get("logo") and not ex["logo"]: ex["logo"] = e["logo"]
    r = list(cmap.values())
    r.sort(key=lambda x:(GROUP_ORDER.get(x["group"],99),x["name"]))
    return r

def main():
    print("="*55); print("  TV 直播源聚合器"); print("="*55)
    all_e = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        fs = {}
        for url,fmt in SOURCE_URLS: fs[pool.submit(fetch_text,url)] = (url,fmt)
        for fut in as_completed(fs):
            url,fmt = fs[fut]; short = url.rsplit("/",1)[-1]; print(f"\n[FETCH] {short}")
            text = fut.result()
            if text is None: print("  [SKIP]"); continue
            parser = parse_m3u if fmt=="m3u" else parse_txt
            entries = parser(text); print(f"  [OK] {len(entries)}")
            all_e.extend(entries)
    print(f"\n{'='*55}")
    merged = merge(all_e)
    print(f"  原始:{len(all_e)} | 去重:{len(merged)}")
    gc = {}
    for ch in merged: g=ch["group"]; gc[g]=gc.get(g,0)+1
    for g in sorted(gc,key=lambda x:GROUP_ORDER.get(x,99)): print(f"    {g}:{gc[g]}")
    output = {"lives":merged}
    sd = os.path.dirname(os.path.abspath(__file__))
    op = os.path.join(os.path.dirname(sd), OUTPUT_FILE)
    with open(op,"w",encoding="utf-8") as f: json.dump(output,f,ensure_ascii=False,indent=2)
    print(f"\n[OUTPUT] sources.json ({os.path.getsize(op)/1024:.1f} KB)")
    print("="*55)

if __name__ == "__main__": main()
