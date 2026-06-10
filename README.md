# 📺 家用电视直播单列表

给家里电视盒子提供**稳定、单目录、纯直播**的电视列表。

> 不再混入点播、复杂 TVBox 外壳、左右切换分组。

## 频道阵容
- **央视**：CCTV-1 ~ 15（含 CCTV-5+）
- **卫视**：湖南 / 浙江 / 江苏 / 东方 / 北京 / 深圳 / 广东 等 26 省
- **本地**：黑龙江卫视 / 都市 / 影视 / 文体 + 哈尔滨综合
- **专题**：求索系列 / 劲爆体育 / 金鹰卡酷 / 优漫哈哈
- **总计**：~63 频道，白名单强排序，零测速

## 生成文件
| 文件 | 格式 | 用途 |
|------|------|------|
| `tvbox.json` | 扁平 JSON | TVBox 直播入口（老盒子兼容 `url` 单数字段） |
| `box-live.json` | 分层 JSON | 支持 `urls` 数组的盒子 |
| `sources.json` | 扁平 JSON | GitHub Actions 参考、API 读取 |
| `sources.txt` | CSV | 纯文本直播源 |
| `sources.m3u` | M3U | 标准 M3U 格式 |
| `datasource.json` | TVBox 数据源 | 配置远程地址加载 |
| `live-test.txt` / `live-test.m3u` | — | 最小验证文件 |

## 推荐测试顺序

### 1. 数据源地址（先配这个）
```
https://cdn.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/datasource.json
```
TVBox 可通过「数据源管理」导入，自动加载下面所有 CDN 线路。

### 2. 直播源直连地址
先试最小验证（能通再换正式）：
```
https://cdn.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/live-test.txt
```
正式版本（按盒子支持的格式选一个）：
| 格式 | CDN 地址 |
|------|---------|
| TVBox JSON | `https://cdn.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/tvbox.json` |
| M3U | `https://cdn.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/sources.m3u` |
| TXT | `https://cdn.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/sources.txt` |

> **备选 CDN**：如果 jsDelivr 国内不稳定，换成 gcore：
> `https://gcore.jsdelivr.net/gh/xu1152/tv-source-aggregator@master/tvbox.json`
> 或试试 ghproxy：
> `https://ghproxy.net/https://raw.githubusercontent.com/xu1152/tv-source-aggregator/master/tvbox.json`

### 3. EPG 地址
```
https://epg.112114.xyz/e.xml
```

## 自动更新
GitHub Actions 每天北京时间 **6:00 和 18:00** 自动重新抓取 7 个公开源 → 白名单过滤 → 去重 → 推送到仓库。

也可以手动触发：Actions → `Update TV Sources` → `Run workflow`

## Node.js 兼容性
GitHub Actions 已启用 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` 环境变量，兼容 Node.js 24 运行时。

## 本地运行
```bash
# 需要 Python 3.10+
python scripts/aggregate.py
```
输出文件直接写入仓库根目录。
