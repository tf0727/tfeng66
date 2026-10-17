# 编程培训咨询 Agent Demo

一个由老师教学样本驱动的本地咨询原型：学员咨询 → 全量召回套路 → 按背景推进 → 查询有依据的事实 → 必要时转班主任 → 反馈改进与同题回放。

**先看[启动指南](./启动指南.md)**。日常演示使用8888单端口；开发使用5173前端和8888后端。

## 功能概览

| 模块 | 能力 |
|---|---|
| 咨询平台 | 多轮对话、SSE流式回复、历史恢复、停止生成、点赞点踩 |
| 执行轨迹 | 决策摘要、Prompt版本、工具参数/结果/耗时、错误与兜底状态 |
| 工单 | 主动诉求、规则或低置信度转人工；统一落库去重；接单与处理 |
| 训练样本 | 问题、标注答案、回答原因、场景、来源；编辑、审核、删除和审计 |
| 套路库 | 展示审核样本，与每轮召回和系统上下文同源 |
| 知识库 | 人工填答、审核、确认入库、本地向量检索；修改后重新审核 |
| Prompt | 基础内容编辑、完整预览与下载、真实红线测试、版本发布及回滚 |
| 半自动改进 | Qwen分析差评、生成候选/理由/diff，人工审核后发布 |
| 回放与观测 | 同题版本对比、只读工具、运行指标导出与审计 |

## 核心业务规则

- 询价先确认学习意向，不主动报具体价格；意向明确后由班主任谈价。
- 信息不足先了解学历、基础、城市、学习目标和投入。
- 不编造政策、就业承诺或真实案例；样本也不能覆盖业务铁律。
- 每轮由程序强制调用 `recall_playbook` 获取全部已审核样本。
- 已审核样本按场景加入系统上下文；发布 Prompt 或审核样本后下一轮生效。
- 通常回复2–3句。安全Guard按完整句检查，并限制整轮句数。

## 技术栈

| 层 | 实现 |
|---|---|
| 前端 | Vue3、Vite、TypeScript，Pinia已初始化 |
| 后端 | FastAPI、SQLAlchemy、SQLite |
| 模型 | Qwen-plus，DashScope OpenAI兼容接口 |
| Harness | 注入式Loop、Context、ToolRegistry、StreamingGuard |
| 通信 | POST SSE、持久化请求ID/事件序号、心跳、取消与续读 |
| 向量检索 | SQLite保存256维字符二元组哈希向量，余弦相似检索 |
| 测试 | unittest、Playwright + 本机Edge、隔离真实模型验收 |

向量检索是无需下载模型的轻量本地实现，不是Chroma或语义embedding模型；相似度不等于回答正确率。执行轨迹不包含隐藏思维链。

## 快速启动

以下假设项目位于 `D:\codex`，Python、uv和Node/npm已可用：

```powershell
Set-Location D:\codex
uv sync --locked
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# 首次启动：在 .env 填写 DASHSCOPE_API_KEY

Set-Location D:\codex\frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run build

Set-Location D:\codex
& .\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8888 --workers 1
```

| 入口 | 地址 |
|---|---|
| 咨询 | http://127.0.0.1:8888/ |
| 后台 | http://127.0.0.1:8888/admin.html |
| 健康 | http://127.0.0.1:8888/health |
| 接口文档 | http://127.0.0.1:8888/docs |

首次空库需先录入并审核教学样本，否则按规则转人工。已安装依赖且已构建时，日常只运行最后两行即可。

## 项目目录

```text
agent/                  咨询业务、样本、工具、知识检索、Prompt与优化
harness/                业务无关的循环、上下文、工具协议和缓冲机制
api/                    聊天SSE、后台管理与页面服务
db/                     数据模型与兼容迁移
frontend/               咨询平台和后台Vue页面
data/                   默认数据库、模拟商品、案例与订单资料
scripts/                样本导入、隔离真实模型/浏览器验收服务
tests/                  后端回归测试
Dockerfile              包含前端的多阶段镜像配置
docker-compose.yml      8888端口与state数据卷配置
```

## 已注册工具

| 工具 | 用途 |
|---|---|
| recall_playbook | 全量召回已审核教学样本 |
| analyze_student | 从对话提取学员背景 |
| generate_plan | 生成能力路径，不承诺招生结果 |
| course_search | 检索已登记的模拟商品资料 |
| student_cases | 检索已核验、有来源、背景匹配的真实案例 |
| knowledge_search | 检索已审核知识及来源版本 |
| handoff | 创建或复用班主任工单 |
| assess_confidence | 记录模型自评，低于0.5转人工 |
| order_query | 当前会话绑定的只读脱敏订单 |

## 数据与配置

默认数据库为 `data/app.db`。模型Key保存在不提交的 `.env`；模型、数据库位置和差评阈值配置见 `.env.example`。

- `data/catalog.json`：带来源标记的模拟商品，不是实际招生政策。
- `data/student_cases.json`：默认空；只有 `verified=true` 且有来源的真实案例才返回。
- `data/demo_orders.json`：脱敏模拟订单；`DEMO-001` 绑定 `demo-session`，无支付和订单写入。
- 已审核样本、知识、Prompt、会话和工单保存在SQLite，重启保留。
- 修改训练样本或知识后需重新审核；运行时会服从当前业务铁律。

模型自评不是客观正确率。本地事件与指标可用于技术验证，不能解释为真实用户量、咨询转化率或商业收益。

## 测试与演示

后端：

```powershell
Set-Location D:\codex
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

真实模型：

```powershell
& .\.venv\Scripts\python.exe scripts\verify_live.py
```

真实验收使用隔离数据库，报告写入 `data/acceptance_live.json`，会消耗API配额。浏览器验收及停止方法见[启动指南](./启动指南.md)；五分钟流程见[DEMO.md](./DEMO.md)。

本次已有21项后端测试、3项浏览器场景，以及真实Qwen五轮咨询、红线测试、优化与回放记录。它们的模型桩/真实调用边界见[整改验收记录](./第八条整改验收记录.md)。

## 已知边界

- 当前是单机本地原型，按单worker运行；没有登录、生产级访问控制或多进程任务协调。
- 首个完整安全句实测中位数约3.1秒，尚未达到2秒目标。
- 商品与订单为模拟，真实业务案例需要提供经确认的资料。
- Docker配置已提供，尚无本机容器实际运行证据。
- 不实现真实支付、实时坐席系统、自动发布Prompt或fine-tune。

## 文档导航

- [启动指南](./启动指南.md)：首次配置、日常启动、开发、备份、测试与故障排查。
- [任务清单](./任务清单.md)：当前实现与剩余任务。
- [需求分析](./任务需求分析.md)：统一技术与业务基线。
- [演示脚本](./DEMO.md)：五分钟演示路径。
- [整改验收记录](./第八条整改验收记录.md)：证据、指标与未完成事项。
- [项目复盘](./项目复盘-需求与交付记录.md)：需求变化、协作分工及历史交付过程。
