# 具身智读

本项目是一个本地 FastAPI Web 应用，用于按北京时间自然日抓取 arXiv 上机器人、具身智能、VLA、world model、具身数据集和 benchmark 相关论文，并调用智能模型生成当日日报、按需单篇总结和全文总结。

## 功能

- 按日期从 arXiv 抓取新论文，默认分类为 `cs.RO`、`cs.CV`、`cs.LG`、`cs.AI`、`eess.SY`。
- 本地管理 arXiv 分类、关键词组、权重和排除词。
- SQLite 持久化论文、命中关键词、相关性分数、单篇总结和日报。
- 智能模型通过兼容 Chat Completions 的接口调用，支持在 Web 的“智能设置”页面配置 Base URL、模型 ID、temperature、输出 token 和长文本输入上限。
- Web 页面支持手动抓取、查看论文、生成单篇总结、生成日报和导出 Markdown。
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

## 测试

```bash
pytest
```

默认测试 mock 掉外部网络和智能模型调用，不需要真实 API key。

## 说明

摘要总结和日报基于 arXiv 元数据和摘要生成；全文总结会下载 PDF 并基于文本提取结果生成。日报中的“建议深读”是基于标题、摘要、分类、关键词命中和相关性分数排序得到的候选，不代表完整论文阅读结论。
