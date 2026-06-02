# 具身智读

本项目是一个本地 FastAPI Web 应用，用于按 arXiv 批次日抓取机器人、具身智能、VLA、world model、具身数据集和 benchmark 相关论文，并调用智能模型按需生成单篇摘要翻译、单篇总结和全文总结。

## 功能

- 按 arXiv 美东工作日 14:00 截止批次从 arXiv 抓取新论文，默认分类为 `cs.RO`、`cs.CV`、`cs.LG`、`cs.AI`、`eess.SY`。
- 本地管理 arXiv 分类、关键词组、权重和排除词。
- SQLite 持久化论文、命中关键词、相关性分数、摘要翻译、单篇总结和全文总结。
- 智能模型通过兼容 Chat Completions 的接口调用，支持在 Web 的“智能设置”页面配置 Base URL、模型 ID、temperature、输出 token 和长文本输入上限。
- Web 页面支持手动抓取、查看论文、生成摘要翻译、单篇总结和全文总结。
- Web 端内置账号体系：首次启动创建管理员，之后按管理员、编辑者、阅读者三类角色控制用户管理、系统设置、抓取生成和只读浏览权限。
- 抓取结果会按 arXiv 查询页缓存；重复抓取同一天会优先使用本地缓存重算关键词，减少触发 arXiv 限流。
- CLI 支持 `serve`、`fetch`、`summarize-paper`，便于接入自动化流程。

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
export ARXIV_DAILY_TIMEZONE="Asia/Shanghai"
export ARXIV_REQUEST_DELAY_SECONDS="5.0"
export ARXIV_USER_AGENT="jushen-zhidu/0.1 (arXiv API client)"
export ARXIV_RETRY_BASE_DELAY_SECONDS="30"
export ARXIV_DAILY_NETWORK_FETCH_LIMIT="5"
export ARXIV_CACHE_ENABLED="true"
export AUTH_SESSION_DAYS="14"
export AUTH_COOKIE_SECURE="false"
```

## 使用

启动 Web 应用：

```bash
arxiv-daily serve --port 8000
```

然后打开 `http://127.0.0.1:8000`。

首次打开 Web 界面时，如果数据库里还没有账号，系统会自动进入“创建管理员账号”页面。管理员创建完成后即可在“用户管理”里新增账号：

- 管理员：管理账号、检索规则、智能设置、缓存清理，以及编辑者的全部操作。
- 编辑者：抓取论文、生成智能结果、查看所有论文内容。
- 阅读者：只读浏览总览、单篇论文和论文森林。

管理员创建或重置的账号首次登录后必须修改密码。密码使用 PBKDF2-SHA256 加盐哈希保存，登录状态使用 HttpOnly + SameSite=Lax cookie 记录；如部署到 HTTPS，请设置 `AUTH_COOKIE_SECURE=true`。

智能模型 API 也可以在 Web 界面的“智能设置”中保存；API Key 只显示配置状态，不会回显明文。

CLI 抓取和单篇总结：

```bash
arxiv-daily fetch --date 2026-05-15
arxiv-daily summarize-paper 2605.15157v1
arxiv-daily summarize-paper 2605.15157v1 --full-text
```

如果确实需要绕过本地 arXiv 响应缓存重新请求，可以在 Web 抓取区勾选“跳过缓存”，或使用：

```bash
arxiv-daily fetch --date 2026-05-15 --force-refresh
```

`ARXIV_DAILY_NETWORK_FETCH_LIMIT` 用于限制同一目标日期每天“有效拉取”的次数；默认 `5`。只有成功完成且保存到新论文的官方 API 抓取才计数，429、503、超时、连接失败、缓存命中和 0 篇新增都不计数。普通抓取会优先使用本地缓存重算关键词。设置为 `0` 表示不限制。

当天和前一天的 arXiv 空结果缓存默认只复用 30 分钟，避免太早抓取到 `totalResults=0` 后挡住后续更新；可用 `ARXIV_EMPTY_CACHE_TTL_SECONDS` 调整，设置为 `0` 表示不过期。

日期选择对应 arXiv 的公告批次日，而不是北京时间自然日。周日批次覆盖上周四 14:00 到周五 14:00 前的提交；周一批次覆盖上周五 14:00 到周一 14:00 前的提交；周二到周四批次覆盖前一工作日 14:00 到当天 14:00 前的提交。周五和周六没有常规公告。

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

摘要总结基于 arXiv 元数据和摘要生成；全文总结会下载 PDF 并基于文本提取结果生成。
