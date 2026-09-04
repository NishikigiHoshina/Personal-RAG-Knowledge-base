# RAG Terminal · 智能问答助手

> 基于 LangChain / LangGraph 构建的 RAG + ReAct Agent 智能问答系统。
> 支持知识库检索问答、工具自主调用、个人使用报告生成，以及 SSE 流式对话与工具调用可视化。

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [工具与中间件](#工具与中间件)
- [核心流程](#核心流程)
- [前端](#前端)
- [开发笔记](#开发笔记)

---

## 功能特性

- **RAG 知识库问答** —— 上传 txt / pdf 文档，向量化入 Chroma 库，检索 + LLM 总结作答
- **ReAct 工具调用** —— 模型自主决策调用天气查询、用户身份、时间、日志检索等 8 个工具
- **个人使用报告生成** —— 解析系统自身运行日志，按 UID 聚合生成使用报告（动态提示词切换）
- **SSE 流式对话** —— 文本逐块输出 + 工具调用卡片实时可视化
- **文件上传入库** —— 拖拽上传、MD5 去重、入库状态索引
- **双入口形态** —— Flask（生产 Web）+ Streamlit（快速原型）

## 技术栈

| 层 | 技术 |
|---|---|
| Agent 编排 | LangChain 1.3.14（`create_agent` + middleware） |
| 对话模型 | DeepSeek `deepseek-chat` |
| Embedding | Ollama 本地 `qwen3-embedding:4b` |
| 向量库 | ChromaDB 1.5.9（本地持久化） |
| Web 框架 | Flask（主） + Streamlit（备） |
| 前端 | 原生 HTML / JS / CSS（Ark UI 工业风设计系统） |
| 日志解析 | 自研 `log_parser`（正则 + UID 检索） |

## 项目结构

```
Project/
├── app.py                  # Flask 主应用（SSE 流式 + 上传 + 会话管理）
├── app_streamlit.py        # Streamlit 备用入口
├── require.txt             # 依赖清单
│
├── agent/
│   └── react_agent.py      # ReAct 智能体（create_agent 装配）
│
├── model/
│   └── factory.py          # 模型工厂（Chat + Embedding 抽象工厂）
│
├── rag/
│   ├── vector_store.py     # Chroma 向量存储 + 文本分片 + 入库去重
│   └── rag_service.py      # RAG 检索总结链（LCEL: prompt|model|parser）
│
├── tools/
│   ├── agent_tools.py      # 8 个 @tool 工具定义
│   ├── middleware.py       # 3 个中间件（监控 / 日志 / 动态提示词）
│   ├── getweather.py       # 天气爬虫（i.tianqi.com + 正则解析）
│   └── log_parser.py       # 日志解析器（UID 检索 / 上下文还原 / 导出）
│
├── utils/
│   ├── config_handler.py   # YAML 配置加载
│   ├── file_handler.py     # 文件加载 / MD5 计算
│   ├── logger_handler.py   # 日志 handler（带 uid 标记）
│   ├── path_tool.py        # 统一绝对路径
│   └── prompt_loader.py     # 提示词加载
│
├── config/                 # YAML 配置
│   ├── system.yml          # 用户 ID
│   ├── rag.yml             # 模型名 / api_key / temperature
│   ├── chroma.yml          # 向量库 / 分片参数
│   ├── agent.yml           # Agent 外部数据路径
│   └── prompts.yml         # 提示词文件路径
│
├── prompts/                # 提示词
│   ├── main_prompt.txt     # 主系统提示词
│   ├── rag_summarize.txt   # RAG 总结提示词
│   └── report_prompt.txt   # 报告生成提示词
│
├── templates/
│   └── index.html          # Flask 页面
├── static/
│   ├── css/style.css       # Ark UI 样式
│   └── js/
│       ├── chat.js         # SSE 流式客户端
│       └── upload.js       # 上传 + 页面导航
│
├── data/                   # 知识库源文件
├── logs/                   # 运行日志（同时作为报告数据源）
└── chroma_db/              # Chroma 持久化目录（运行后生成）
```

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│  入口层  app.py (Flask) / app_streamlit.py (Streamlit)       │
│  · SSE 流式接口 · 文件上传 · UUID 会话隔离 + TTL 清理         │
└───────────────┬─────────────────────────────────────────────┘
                │ 共用 Agent 单例（双检锁惰性初始化）
┌───────────────▼─────────────────────────────────────────────┐
│  Agent 层  ReactAgent = create_agent(model, prompt, tools,  │
│                                     middleware)             │
└────┬──────────────┬───────────────┬────────────────────────┘
     │              │               │
┌────▼────┐   ┌─────▼─────┐   ┌────▼────────────────────────┐
│ 模型层   │   │ 工具层    │   │ 中间件层                    │
│ factory  │   │ 8 个 @tool│   │ · monitor_tool（工具监控）  │
│ Chat+Emb │   │           │   │ · log_before_model          │
└────┬────┘   └─────┬─────┘   │ · report_prompt_switch       │
     │              │         │   （@dynamic_prompt）        │
     │       ┌──────▼────────┐└─────────────────────────────┘
     │       │ RAG 层        │
     └──────►│ vector_store │
             │ rag_service  │
             └──────┬───────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  基础设施层  utils/  +  config/*.yml  +  prompts/*.txt      │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置条件

1. **Python 3.10+**
2. **Ollama**（本地运行 Embedding 模型）—— [安装](https://ollama.com/)
3. **DeepSeek API Key** —— [获取](https://platform.deepseek.com/)

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd Project

# 2. 安装依赖（注意依赖清单文件名为 require.txt）
pip install -r require.txt

# 3. 拉取本地 Embedding 模型
ollama pull qwen3-embedding:4b
```

### 配置

编辑 `config/rag.yml`，填入你的 DeepSeek API Key：

```yaml
chat_model_name: deepseek-chat
embedding_model_name: qwen3-embedding:4b
api_key: sk-your-deepseek-api-key   # ← 替换占位符 XXX
temperature: 0.5
```

可选：编辑 `config/system.yml` 修改用户 ID（影响日志中的 uid 标记与报告检索）：

```yaml
user_id: LC12808   # 你的用户标识
```

### 首次初始化知识库

将 txt / pdf 文件放入 `data/` 目录，然后执行：

```bash
python rag/vector_store.py
```

该脚本会读取 `data/` 下所有允许类型的文件，分片后写入向量库（MD5 去重）。
也可不执行此步，改为启动后通过 Web 上传页面入库。

### 启动

**Flask 主应用（推荐）：**

```bash
python app.py
# 访问 http://localhost:5000
```

**Streamlit 备用入口：**

```bash
streamlit run app_streamlit.py
# 注：Streamlit 入口不支持报告生成流程（context.report 固定为 False）
```

## 配置说明

| 文件 | 关键字段 | 说明 |
|---|---|---|
| `config/system.yml` | `user_id` | 用户标识，写入每行日志，供报告检索 |
| `config/rag.yml` | `chat_model_name` | 对话模型名（deepseek-chat） |
| | `embedding_model_name` | Ollama embedding 模型名 |
| | `api_key` | DeepSeek API Key |
| | `temperature` | 采样温度 |
| `config/chroma.yml` | `collection_name` | Chroma collection（agent） |
| | `persist_directory` | 持久化目录（chroma_db） |
| | `k` | 检索 top-k（10） |
| | `chunk_size` / `chunk_overlap` | 分片大小 500 / 重叠 50 |
| | `separators` | 含中文标点的分隔符优先级 |
| | `md5_hex_store` | 去重记录文件（md5.txt） |
| | `allow_knowledge_file_type` | 允许的文件类型 |
| `config/agent.yml` | `external_data_path` | 报告数据源目录（logs/） |
| `config/prompts.yml` | `*_prompt_path` | 三套提示词文件路径 |

## 工具与中间件

### 工具（`tools/agent_tools.py`，共 8 个）

| 工具 | 入参 | 作用 |
|---|---|---|
| `rag_summarize` | `query` | 知识库检索 + LLM 总结 |
| `get_weather` | `city` | 爬取指定城市实时天气 |
| `get_user_location` | — | 返回用户城市（当前硬编码"深圳"） |
| `get_user_id` | — | 返回用户 ID（来自 system.yml） |
| `get_current_month` | — | 当前月份 YYYY-MM |
| `get_time_now` | — | 当前时间 |
| `fetch_external_data` | `user_id, month` | 按 UID 检索运行日志 |
| `fill_context_for_report` | — | **信号工具**：触发提示词切换为报告模式 |

### 中间件（`tools/middleware.py`，共 3 个）

| 中间件 | 装饰器 | 作用 |
|---|---|---|
| `monitor_tool` | `@wrap_tool_call` | 工具执行监控日志；捕获 `fill_context_for_report` 调用，将 `runtime.context["report"]` 置 True |
| `log_before_model` | `@before_model` | 模型调用前打印消息数量与内容 |
| `report_prompt_switch` | `@dynamic_prompt` | 根据 `context["report"]` 动态返回主提示词或报告提示词 |

> **设计要点**：`fill_context_for_report` 本身不做实际业务，仅作为模型可调用的"状态翻转开关"——模型按主提示词的强约束流程调用它后，中间件翻转 context，`@dynamic_prompt` 在下次组装提示词时切换为报告专用 prompt。判断留给模型、切换留给中间件，职责分离。

## 核心流程

### ① 日常聊天
用户输入 → `/api/chat/stream` → `agent.stream(stream_mode="values")` → 模型按需调工具 → SSE 事件流（`text` / `tool_call` / `tool_result`）回前端渲染。

### ② RAG 问答
`rag_summarize(query)` → retriever 取 top-10 → 格式化为参考资料 → LCEL 链 `PromptTemplate | model | StrOutputParser` → 总结字符串。

### ③ 文件上传入库
前端拖拽 → `/api/upload` → 保存 → MD5 → 去重检查 → `split_documents` → `vector_store.add_documents` → 记录 MD5。

### ④ 报告生成（最复杂）
用户请求生成报告 → 模型按主提示词强约束依次调用：`get_user_id` → `get_current_month` → `fill_context_for_report`（翻转 context）→ `fetch_external_data`（检索日志）→ 中间件切换到报告 prompt → 模型用报告模板整理日志输出。

> **日志自闭环**：`logger_handler` 把 `uid` 写进每行日志，`log_parser` 再按 `uid` 正则反解检索。系统自身的可观测数据即用户可查询的知识，这也是 `external_data_path` 指向 `logs/` 的原因。

## 前端

采用原生 HTML/JS/CSS 实现的 **Ark UI 工业信息系统设计风格**：

- 深色侧边栏 + 浅色主区，蓝图网格背景，等宽字体标签，零圆角
- 信号色 `#18d1ff`，状态色 `#c8eb21`
- **对话页**：消息气泡 + 工具调用卡片（可展开参数/结果）+ 工具日志侧边面板
- **上传页**：拖拽上传区 + 文件索引表（含入库状态徽标）
- 响应式：移动端侧边栏变 off-canvas 抽屉
- `chat.js`：用 `getReader()` + `TextDecoder` 手动解析 SSE `data: {...}\n\n` 帧

## 开发笔记

- **依赖清单文件名**为 `require.txt`（非 `requirements.txt`）。
- **Embedding 走本地 Ollama**，须先 `ollama pull qwen3-embedding:4b` 并保持 Ollama 服务运行。
- **Streamlit 入口**硬编码 `context={"report": False}`，不支持报告生成流程；完整功能请用 Flask 入口。
- **`rag_service.py`** 的 LCEL 链中含 `print_prompt` 调试钩子，会向 stdout 打印组装后的 prompt。
- **MD5 去重逻辑**在 `app.py` 与 `vector_store.py` 两处实现，存在可合并的冗余。
- **`get_user_location` / `get_user_id`** 当前为单用户 demo 假设（硬编码"深圳" / `LC12808`）。

## License

学习项目，未指定开源协议。
