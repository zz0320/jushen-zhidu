# 具身智读

本项目是一个本地 FastAPI Web 应用，用于按北京时间自然日抓取 arXiv 上机器人、具身智能、VLA、world model、具身数据集和 benchmark 相关论文，并调用智能模型生成当日日报、按需单篇总结和全文总结。

## 功能

- 按日期从 arXiv 抓取新论文，默认分类为 `cs.RO`、`cs.CV`、`cs.LG`、`cs.AI`、`eess.SY`。
- 本地管理 arXiv 分类、关键词组、权重和排除词。
- SQLite 持久化论文、命中关键词、相关性分数、单篇总结和日报。
- 智能模型通过兼容 Chat Completions 的接口调用，支持在 Web 的“智能设置”页面配置 Base URL、模型 ID、temperature、输出 token 和长文本输入上限。
- Web 页面支持手动抓取、查看论文、生成单篇总结、生成日报和导出 Markdown。
- 抓取结果会按 arXiv 查询页缓存；重复抓取同一天会优先使用本地缓存重算关键词，减少触发 arXiv 限流。
- CLI 支持 `serve`、`fetch`、`summarize-day`、`export-day`，便于接入 cron。

## 安装

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 配置

至少在需要生成总结时配置：

```bash
export DASHSCOPE_API_KEY="sk-..."
```

常用可选环境变量：

```bash
export ARXIV_DAILY_DB="data/arxiv_daily.sqlite3"
export ARXIV_DAILY_REPORT_DIR="reports"
export ARXIV_DAILY_TIMEZONE="Asia/Shanghai"
export ARXIV_REQUEST_DELAY_SECONDS="5.0"
export ARXIV_USER_AGENT="jushen-zhidu/0.1 (arXiv API client)"
export ARXIV_RETRY_BASE_DELAY_SECONDS="30"
export ARXIV_DAILY_NETWORK_FETCH_LIMIT="5"
export ARXIV_CACHE_ENABLED="true"
```

## 使用

启动 Web 应用：

```bash
arxiv-daily serve --port 8000
```

然后打开 `http://127.0.0.1:8000`。

智能模型 API 也可以在 Web 界面的“智能设置”中保存；API Key 只显示配置状态，不会回显明文。

CLI 抓取和生成日报：

```bash
arxiv-daily fetch --date 2026-05-15
arxiv-daily summarize-day --date 2026-05-15
arxiv-daily export-day --date 2026-05-15
```

如果确实需要绕过本地 arXiv 响应缓存重新请求，可以在 Web 抓取区勾选“跳过缓存”，或使用：

```bash
arxiv-daily fetch --date 2026-05-15 --force-refresh
```

`ARXIV_DAILY_NETWORK_FETCH_LIMIT` 用于限制同一目标日期每天“有效拉取”的次数；默认 `5`。只有成功完成且保存到新论文的官方 API 抓取才计数，429、503、超时、连接失败、缓存命中和 0 篇新增都不计数。普通抓取会优先使用本地缓存重算关键词。设置为 `0` 表示不限制。

## arXiv 官方接口使用

- 日常检索使用 arXiv 官方 API：`https://export.arxiv.org/api/query`，返回 Atom XML 元数据。
- 请求节奏遵守 arXiv API Terms：单连接、至少 3 秒一次请求。本项目默认 5 秒一次；如果环境变量设置得更低，运行时也会强制按不少于 3 秒执行。
- 大规模元数据同步应使用 arXiv OAI-PMH：`https://oaipmh.arxiv.org/oai`；本项目当前日常雷达仍走搜索 API，因为需要按提交日期、分类和关键词筛选。
- PDF/全文只在用户主动生成全文总结时按单篇下载，不缓存或对外分发 PDF；界面保留 arXiv 摘要页链接作为主要阅读入口。

## 测试

```bash
pytest
```

默认测试 mock 掉外部网络和智能模型调用，不需要真实 API key。

## 说明

摘要总结和日报基于 arXiv 元数据和摘要生成；全文总结会下载 PDF 并基于文本提取结果生成。日报中的“建议深读”是基于标题、摘要、分类、关键词命中和相关性分数排序得到的候选，不代表完整论文阅读结论。
