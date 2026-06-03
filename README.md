# 📺 TV 直播源自动聚合

每天自动从 7 个公开源拉取、合并、去重 → 输出 TVBox 兼容 JSON。

## 📊 当前数据

| 分组 | 频道数 |
|------|--------|
| 央视频道 | 42 |
| 卫视频道 | 71 |
| 地方频道 | 104 |
| 数字频道 | 180 |
| 体育频道 | 64 |
| 少儿频道 | 14 |
| 国际频道 | 9 |
| **合计** | **484** |

## 🚀 使用方法

### 方法一：直接用我的（推荐）

等我把仓库推到 GitHub，你直接在 TVBox 里填：
```
https://raw.githubusercontent.com/你的用户名/tv-source-aggregator/main/sources.json
```

### 方法二：自己 Fork

1. Fork 本仓库到你的 GitHub
2. 启用 Actions（Settings → Actions → Allow all）
3. TVBox 设置 → 配置地址 → 填入上面那个 URL

## ⏰ 自动更新

GitHub Actions 每天 **6:00 和 18:00**（北京时间）自动执行聚合脚本。

也可以手动触发：Actions → "Update TV Sources" → Run workflow

## 📡 数据来源

| 源 | 频道数 |
|---|--------|
| fanmingming/live (ipv6) | ~82 |
| fanmingming/live (itv) | ~189 |
| ssili126/tv | ~91 |
| YanG-1989/m3u Gather | ~125 |
| YueChan/Live IPTV | ~89 |
| iptv-org (中国) | ~170 |
