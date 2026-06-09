# 📺 家用电视直播单列表

这个项目现在只做一件事：

> 给家里老人提供一个**稳定、单目录、纯直播**的电视列表。

不再混入点播、复杂 TVBox 外壳、左右切换分组。

## 当前设计
- 单目录：`电视直播`
- 优先频道：
  - CCTV 1–15（含 CCTV-5+）
  - 主流卫视
  - 黑龙江本地台
  - 少量少儿 / 体育 / 纪录
- 协议优先：`http/https m3u8`
- 暂时过滤：`rtp://`、IPv6-only、明显异常源

## 生成文件
运行脚本后会输出：

- `box-live.json`：盒子专用直播 JSON（频道对象使用 `urls` 数组）
- `live.txt`：纯文本直播源
- `live.m3u`：m3u 直播源
- `channels-debug.json`：调试用频道清单
- `datasource.json`：数据源地址占位文件
- `live-test.txt` / `live-test.m3u`：最小验证文件

同时保留旧文件名，方便历史地址继续测试：

- `tvbox.json`
- `sources.json`
- `sources.txt`
- `sources.m3u`

## 推荐测试顺序
### 1. 数据源地址
```text
https://cdn.jsdelivr.net/gh/你的用户名/tv-source-aggregator@master/datasource.json?v=999
```

### 2. 直播源地址
先试最小验证：

```text
https://cdn.jsdelivr.net/gh/你的用户名/tv-source-aggregator@master/live-test.txt?v=999
```

如果盒子认 txt，再试正式版本：

```text
https://cdn.jsdelivr.net/gh/你的用户名/tv-source-aggregator@master/live.txt?v=999
```

如果盒子更认 m3u，则试：

```text
https://cdn.jsdelivr.net/gh/你的用户名/tv-source-aggregator@master/live.m3u?v=999
```

如果盒子直播入口认 JSON，则试：

```text
https://cdn.jsdelivr.net/gh/你的用户名/tv-source-aggregator@master/box-live.json?v=999
```

### 3. EPG 地址
```text
https://epg.112114.xyz/e.xml
```

## 自动更新
GitHub Actions 每天北京时间 **6:00 和 18:00** 自动重新生成直播文件。

也可以手动触发：

- Actions
- `Update TV Sources`
- `Run workflow`
