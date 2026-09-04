# llm-wiki 功能模块设计

> 配套《llm-wiki升级方案.md》。本文**仅罗列最小原型所需开发的功能模块及其接口契约，不含代码实现**。
> 文中出现的方法签名均为**接口契约**（设计层面），不是实现；遵循本项目既有编码风格与封装方式。

---

## 一、模块全景

| # | 模块路径 | 类型 | 职责（一句话） |
|---|---|---|---|
| M1 | `wiki/wiki_store.py` | 新建 | wiki 页面 JSON KV 存储 + 独立 Chroma collection |
| M2 | `wiki/extractor.py` | 新建 | LLM 抽取实体/关系，输出结构化记录 |
| M3 | `wiki/wiki_service.py` | 新建 | 编排 抽取→聚合→页面生成→存储；提供 wiki 检索 |
| M4 | `prompts/wiki_extract.txt` | 新建 | 实体/关系抽取提示词 |
| M5 | `prompts/wiki_build.txt` | 新建 | wiki 页面生成提示词 |
| M6 | `config/wiki.yml` | 新建 | wiki 存储与检索配置 |
| M7 | `static/js/wiki.js` | 新建 | wiki 浏览页前端逻辑 |
| M8 | `utils/config_handler.py` | 改造 | 新增 wiki 配置加载 |
| M9 | `utils/prompt_loader.py` | 改造 | 新增 wiki 提示词加载 |
| M10 | `config/prompts.yml` | 改造 | 新增 2 个提示词路径项 |
| M11 | `tools/agent_tools.py` | 改造 | 新增 `wiki_query` 工具 + 单例 |
| M12 | `agent/react_agent.py` | 改造 | 注册 `wiki_query` |
| M13 | `app.py` | 改造 | 新增 `/api/wiki/*` 路由 |
| M14 | `templates/index.html` | 改造 | 新增导航项 + wiki 页面骨架 |
| M15 | `static/css/style.css` | 改造 | 新增 wiki 页面样式 |

> **合计**：新建 7 个文件，改造 8 个文件。**不引入任何新依赖**。

---

## 二、新建模块详述

### M1 · `wiki/wiki_store.py` — `WikiStoreService`

- **对标**：`rag/vector_store.py` 的 `VectiorStoreService`
- **职责**：wiki 页面持久化（JSON KV 落盘）+ 页面向量存检索（独立 collection，不污染原 `agent` collection）。
- **对外接口契约**：
  - `__init__()` — 加载 KV 文件到内存 dict；初始化 `Chroma(collection_name=wiki_conf["collection_name"])`。
  - `upsert_page(name: str, page: dict) -> None` — 写 KV + upsert 页面 Document 到向量库；`page_content` = 名称 + 描述 + 关系摘要。
  - `get_page(name: str) -> dict | None` — 按实体名取页面。
  - `list_pages() -> list[dict]` — 全量页面摘要（名称 / 类型 / 关系数 / 来源文件）。
  - `get_retriever() -> Retriever` — 返回 wiki 向量检索器（top-k = `wiki_conf["k"]`）。
- **依赖**：`model.factory.embed_model`、`utils.config_handler.wiki_conf`、`utils.path_tool.get_abs_path`、`utils.logger_handler.logger`、`langchain_chroma.Chroma`。
- **验收**：`__main__` 能空载入、写入后落盘 JSON、重启后 KV 恢复；向量库检索返回页面。

---

### M2 · `wiki/extractor.py` — `EntityExtractor`

- **对标**：`rag/rag_service.py` 的 `RagSummarizeService`（LCEL 链）
- **职责**：对文档分片逐片调 LLM，抽取实体/关系，输出结构化记录。
- **对外接口契约**：
  - `__init__()` — 加载 wiki_extract 提示词，建链 `PromptTemplate | chat_model | StrOutputParser`。
  - `extract_from_documents(documents: list[Document]) -> list[dict]` — 返回实体记录列表，每条含 `name / type / description / relationships / source`；JSON 解析失败容错为空记录 + `logger.warning`，不阻断。
- **依赖**：`model.factory.chat_model`、`utils.prompt_loader.load_wiki_extract_prompts`、`langchain_core.prompts.PromptTemplate`、`langchain_core.output_parsers.StrOutputParser`、`utils.logger_handler.logger`。
- **验收**：`__main__` 对 `data/test_upload.txt` 抽取出至少 1 个实体 + 关系，结构合法。

---

### M3 · `wiki/wiki_service.py` — `WikiBuildService`

- **对标**：`rag/rag_service.py`（编排 + 检索）
- **职责**：编排 抽取 → 按实体名聚合 → 逐实体生成 wiki 页面 → 入库；提供查询期检索。
- **对外接口契约**：
  - `__init__()` — 持有 `EntityExtractor`、`WikiStoreService`、build LCEL 链。
  - `build_from_documents(documents: list[Document], source_name: str) -> int` — 全流程构建，返回生成页面数。
  - `build_page(name: str, records: list[dict]) -> dict` — 单实体页面生成（调 build_chain）。
  - `query(query: str) -> list[dict]` — 向量检索 wiki 页面，返回页面 dict 列表（**纯向量召回，本原型唯一检索模式**）。
- **依赖**：`wiki.extractor.EntityExtractor`、`wiki.wiki_store.WikiStoreService`、`model.factory.chat_model`、`utils.prompt_loader.load_wiki_build_prompts`、`utils.logger_handler.logger`。
- **验收**：`__main__` 从 `data/` 全量构建后 `query` 能返回相关页面。

---

### M4 · `prompts/wiki_extract.txt`

- **职责**：约束 LLM 从文本片段输出 JSON（实体列表 + 类型 / 描述 / 关系）。
- **要求**：沿用 `rag_summarize.txt` 的约束写法（"仅输出 JSON，不附加说明" + 合规性）；含 `{input}` 占位。

### M5 · `prompts/wiki_build.txt`

- **职责**：约束 LLM 基于某实体的多条出现记录 + 来源片段生成 wiki 页面（描述 / 关系 / 来源）。
- **要求**：强约束"基于资料不编造"；含 `{name}`、`{records}` 占位。

### M6 · `config/wiki.yml`

- **对标**：`config/chroma.yml`
- **字段**：`collection_name`(wiki) / `persist_directory`(chroma_db) / `wiki_kv_path`(wiki_store.json) / `k`(5) / `wiki_file_type`([txt,pdf,md])。

### M7 · `static/js/wiki.js`

- **对标**：`static/js/upload.js`
- **职责**：wiki 页面渲染（列表表格 + 详情卡片 + 关系互链跳转 + 来源引用展示）+ 触发构建按钮 `fetch /api/wiki/build`。
- **验收**：列表加载、点击实体跳详情、关系 `target` 可点击跳转、来源文件名展示。

---

## 三、改造模块详述

### M8 · `utils/config_handler.py`

- **增量**：新增 `load_wiki_config()` 函数（对标现有 5 个 loader）+ 模块级 `wiki_conf = load_wiki_config()`。
- **验收**：`python -c "from utils.config_handler import wiki_conf; print(wiki_conf)"` 输出 wiki.yml 内容。

### M9 · `utils/prompt_loader.py`

- **增量**：新增 `load_wiki_extract_prompts()`、`load_wiki_build_prompts()`（对标现有 3 个 loader）。
- **验收**：两函数返回对应 txt 内容；`KeyError` 时 `logger.error` 并 `raise`（沿用现有风格）。

### M10 · `config/prompts.yml`

- **增量**：新增 `wiki_extract_prompt_path`、`wiki_build_prompt_path` 两项。

### M11 · `tools/agent_tools.py`

- **增量**：模块级 `wiki_service = WikiBuildService()`（对标 `rag = RagSummarizeService()`）+ `@tool` `wiki_query(query)`（对标 `rag_summarize`）。
- **要求**：工具 `description` 用中文明确区分——`wiki_query`="实体 wiki 卡片检索"，`rag_summarize`="参考资料总结"，避免 Agent 混用。
- **验收**：工具可被 Agent 调用并返回字符串。

### M12 · `agent/react_agent.py`

- **增量**：`tools=[...]` 加入 `wiki_query`。
- **验收**：Agent 在问"wiki 里有什么 / 某实体资料"时主动调 `wiki_query`。

### M13 · `app.py`

- **增量路由**：
  - `POST /api/wiki/build` — 读 `data/` → 分片 → `build_from_documents` → 返回页面数。
  - `GET /api/wiki` — `list_pages()`。
  - `GET /api/wiki/<name>` — `get_page()`。
- **可选**：`/api/upload` 成功后按 `wiki_conf` 开关触发该文件 wiki 构建（默认关，避免拖慢上传）。
- **验收**：三路由返回合法 JSON；构建路由返回非零页面数。

### M14 · `templates/index.html`

- **增量**：侧边栏新增第三导航项"知识库 WIKI" + `page-wiki` 区块（列表容器 + 详情容器 + 构建按钮）+ 引入 `wiki.js`。
- **验收**：导航切换显示 wiki 页。

### M15 · `static/css/style.css`

- **增量**：wiki 列表表格、实体详情卡片、关系链接、来源引用样式，复用 Ark UI token（`--ark-*` 变量），不引入新设计语言。
- **验收**：与对话 / 上传页视觉一致。

---

## 四、模块依赖关系

```
config/wiki.yml ─┐
                 ├─► M1 WikiStoreService ─┬─► M3 WikiBuildService ──► M11 wiki_query ──► M12 react_agent
prompts/extract ─┤   (M6 配置)             │
                 ├─► M2 EntityExtractor ──┘
prompts/build ───┘   (M4/M5 提示词)
M8 config_handler ──► M1 / M2 / M3 读取 wiki_conf
M9 prompt_loader  ──► M2 / M3 读取提示词
M13 app.py        ──► M3（构建 / 列表 / 详情路由）
M14 index.html + M7 wiki.js + M15 style.css ──► 前端浏览
```

> 依赖链无环。M1/M2 可并行开发，M3 依赖二者，前端三件套可与后端并行。

---

## 五、开发任务清单

按依赖顺序，每步可独立 `if __name__ == '__main__'` 自测：

- [ ] **T1** 配置与提示词骨架：M6 + M4 + M5 + M8 + M9 + M10
- [ ] **T2** 存储层：M1 `WikiStoreService`
- [ ] **T3** 抽取层：M2 `EntityExtractor`
- [ ] **T4** 构建 + 检索层：M3 `WikiBuildService`
- [ ] **T5** Agent 工具：M11 + 注册 M12
- [ ] **T6** Flask 路由：M13
- [ ] **T7** 前端：M14 + M7 + M15
- [ ] **T8** 联调：上传 → 构建 → 浏览 → Agent 调用 闭环

---

## 六、与最小原型原则的对齐

- **不引入新依赖**：全部基于 `require.txt` 已有包（langchain / chromadb / flask / 标准库 json/yaml）。
- **检索仅一种模式**：纯向量召回 wiki 页面（方案 §2.2 第一行）；local/global 图遍历与社区摘要列为 OUT。
- **关系不参与检索算法**：仅前端互链跳转展示。
- **存储不引入图数据库**：JSON KV + Chroma，复刻本项目"md5.txt 落盘"的朴素存储风格。
- **与原扁平 RAG 并存**：`wiki/` 与 `rag/` 平级，原 `agent` collection 不受影响。
