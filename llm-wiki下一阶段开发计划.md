# llm-wiki 下一阶段开发计划

> 基于《llm-wiki升级方案.md》《llm-wiki功能模块设计.md》已落地的最小原型，结合实际验证中发现的问题与用户提出的改进方向，制定下一阶段计划。
> 本文档为**计划文档**，不含代码实现。延续最小原型原则，模块封装与编码风格不变。

---

## 目录

- [一、当前实现现状回顾](#一当前实现现状回顾)
- [二、改进方向总览](#二改进方向总览)
- [三、方向一：合并检索（切块为基 + wiki 补充）](#三方向一合并检索切块为基--wiki-补充)
- [四、方向二：新增材料时增量更新 wiki](#四方向二新增材料时增量更新-wiki)
- [五、方向三：存储演进（搁置）](#五方向三存储演进搁置)
- [六、范围界定（OUT）](#六范围界定out)
- [七、实施步骤](#七实施步骤)
- [八、风险与取舍](#八风险与取舍)

---

## 一、当前实现现状回顾

已落地（v0.1 wiki 原型）：

- `wiki/` 包：`WikiStoreService`（JSON KV `wiki_store.json` + 独立 Chroma `wiki` collection）、`EntityExtractor`（LCEL 抽取）、`WikiBuildService`（编排 + 纯向量检索）。
- Agent 工具 `wiki_query`（独立检索 wiki 页面）、Flask 路由 `/api/wiki/{build,<name>,}`、前端 wiki 浏览页。

**已确认的两个缺口（本阶段要解决）：**

1. **wiki 未接入主 RAG 流程**：`rag_summarize` 仍只检索 `agent` 切块 collection；`wiki_query` 是另一条独立路径。wiki 内容没有"替换或喂入"原 RAG。
2. **wiki 不支持增量更新**：`build_from_documents` 只看本次文档的记录，重建已有实体时**覆盖丢旧信息**；`upsert_page` 不清理向量库内同名旧记录，重复构建产生重复向量；无"已处理文件"去重，重复构建会重复抽取。

---

## 二、改进方向总览

| # | 方向 | 目标 | 本阶段 |
|---|---|---|---|
| 1 | **合并检索** | `rag_summarize` 同时检索切块（基）+ wiki 页面（补充），结果合并喂 LLM | ✅ 实施 |
| 2 | **增量更新** | 新增材料时，已有实体页面自动并入新信息；已处理文件不重复抽取；向量库不产生重复向量 | ✅ 实施 |
| 3 | **存储演进** | JSON KV 性能不足（全量加载、全量重写、无并发安全），未来换 SQLite 等 | ⏸ 搁置（仅记录方向） |

> 用户决策依据：直接用扁平 wiki 页面替换切块，会让 LLM 自行建立逻辑联系、降低理解效率；故**以切块为语义基底、wiki 页面作结构化补充**。存储搁置因当前 JSON 方式仍符合最小原型需求。

---

## 三、方向一：合并检索（切块为基 + wiki 补充）

### 3.1 目标
`rag_summarize` 工具一次调用即检索两路：切块（`agent` collection，base）+ wiki 页面（`wiki` collection，supplement），拼装成统一 context 喂 LCEL 链。wiki 未构建时自动降级为仅切块。

### 3.2 设计

**依赖注入而非耦合**：`RagSummarizeService` 新增可选 `wiki_retriever`，由 `tools/agent_tools.py` 把已存在的 `wiki_service` 单例的 retriever 传入。避免 `rag→tools` 循环导入、避免重复打开 wiki Chroma 客户端。

**Context 拼装顺序**：切块优先（base）→ wiki 实体卡片补充（supplement），两类显式标注，便于 LLM 区分"原始参考资料"与"结构化实体卡片"。

### 3.3 模块改动（接口契约级，无实现）

**`rag/rag_service.py` — `RagSummarizeService`**
- `__init__(self, wiki_retriever=None)` — 新增可选参数；其余不变。
- `retrieve_wiki_pages(query: str) -> list[dict]` — 新增；`wiki_retriever.invoke` 取 `supplement_k` 个，按 `metadata.name` 去重，从 KV 取完整页面。
- `rag_summarize_service(query: str) -> str` — 改：检索切块（base）+ 调 `retrieve_wiki_pages`（supplement，受 `supplement_enabled` 开关控制）→ 拼装 merged context → 调链。
- `retriever_docs(query)` — 保留不变。

**`tools/agent_tools.py`（单例顺序调整）**
- 先 `wiki_service = WikiBuildService()`，再 `rag = RagSummarizeService(wiki_retriever=wiki_service.store.get_retriever())`。
- `rag_summarize` 工具本身不变。

**`prompts/rag_summarize.txt`（微调）**
- 增补一句：context 中可能同时含「参考资料」（原文切块）与「wiki 实体卡片」（结构化实体信息），回答应综合二者，事实以参考资料为准、实体关系以 wiki 卡片为准。

**`config/wiki.yml`（增量字段）**
```yaml
supplement_k: 3              # 合并检索时 wiki 补充条数
supplement_enabled: true     # 合并检索开关
```

### 3.4 边界
- wiki collection 空 → `retrieve_wiki_pages` 返回空 → context 仅切块（降级）。
- 不做跨 collection 的重排序/rerank（最小原型，按"切块在前、wiki在后"拼接）。
- 两路结果不按来源去重合并（各自 top-k 独立召回，简单拼接）。

---

## 四、方向二：新增材料时增量更新 wiki

### 4.1 目标
- 上传/新增文件后，wiki **只处理新文件**（已处理文件 MD5 去重，不重复抽取）。
- 新文件中出现的**已有实体**：并入新信息生成更新页面（不丢旧信息）。
- 新文件中的**新实体**：正常新建页面。
- `upsert_page` 写入前清理向量库内同名旧记录，消除重复向量。

### 4.2 设计

**更新而非重建**：对已有实体，不回读所有旧文档重抽，而是拿"现有页面正文 + 新文件对该实体的抽取记录"走 **update 提示词**生成更新正文（option-C）。成本低、保留旧知识。

**MD5 去重**：沿用项目既有"文件级 MD5 去重"风格（对标 `md5.txt`），新增 `wiki_md5.txt` 记录已被 wiki 处理过的文件 MD5，`build_from_data_dir` 跳过已处理文件。

### 4.3 模块改动（接口契约级）

**`wiki/wiki_service.py` — `WikiBuildService`**
- `build_from_documents(documents, source_name="") -> int` — 改为增量感知：抽取 → 按名聚合 → 逐实体：`existing = store.get_page(name)`；存在则 `update_page`，否则 `build_page`。
- `update_page(name: str, existing_page: dict, new_records: list[dict]) -> dict` — 新增；用 `wiki_update.txt` 链（existing 正文 + new records → 更新正文）；合并 relationships（按 `(target,desc)` 去重）、sources（按 file 去重，并入新来源）。
- `build_page(name, records)` — 保留不变（仅新实体走此路径）。
- `build_from_file(filepath: str) -> int` — 新增；单文件加载 → 分片 → `build_from_documents`；供 `/api/upload` 触发。
- `build_from_data_dir() -> int` — 改：对每个文件先查 `wiki_md5_store`，命中则跳过；未命中则 `build_from_file` + 记录 MD5。

**`wiki/wiki_store.py` — `WikiStoreService`**
- `upsert_page(name, page)` — 改：写入向量库前，删除 `metadata.name == name` 的旧记录（实现细节：需验证 `langchain_chroma` 当前版本的 `delete(where=...)` 支持；不支持则先按 `where` 查 ids 再 `delete(ids=...)`）。
- `is_source_processed(md5: str) -> bool` / `record_source_processed(md5: str) -> None` — 新增；读写 `wiki_md5_store`（对标 `VectiorStoreService` 内部 MD5 去重写法）。

**`prompts/wiki_update.txt`（新建）**
- 输入：`{name}`、`{existing}`（现有页面正文）、`{new_records}`（新抽取记录）。
- 约束：基于现有正文与新记录合并更新，不编造、不丢失旧信息；仅输出更新后正文纯文本。

**`config/wiki.yml`（增量字段）**
```yaml
wiki_md5_store: wiki_md5.txt    # wiki 已处理文件 MD5 记录
auto_build_on_upload: true       # 上传后自动增量构建 wiki
```

**`app.py` — `/api/upload`**
- 文件入库（切块入 `agent` collection）成功后，若 `wiki_conf["auto_build_on_upload"]`：对该文件调 `wiki_service.build_from_file(save_path)`（增量更新 wiki）。
- 失败不影响上传主流程（try/except + `logger.error`）。

### 4.4 数据模型变更
- `page.sources` 由 `[{file}]` 扩为 `[{file, md5}]`，便于追溯与未来按文件清理。
- 其余字段不变。

### 4.5 边界
- 同名异实体（"苹果"公司 vs 水果）不去重合并（按精确名称聚合，最小原型不变）。
- 已有实体的"旧原始记录"不回读，仅靠现有页面正文承载旧知识（LLM 合并），可能逐次更新有轻微信息漂移——可接受，记为风险。
- 增量更新仅处理"新增文件"；删除/修改既有文件不在本阶段范围。

---

## 五、方向三：存储演进（搁置）

当前 JSON KV 的不足（**不在本阶段处理，仅记录**）：

- 全量加载到内存：实体量增大后启动慢、内存占用高。
- 每次 `upsert_page` 全文件重写：写入随实体数增长变慢。
- 无并发安全：多请求同时写 `wiki_store.json` 可能丢数据。
- 无索引查询：`list_pages` 全量遍历。

**未来方向（待选）**：
- **SQLite**（推荐）：文件型、零运维、支持查询/事务/并发，与项目"朴素可读存储"风格兼容。
- **Chroma metadata-only**：把页面 JSON 存进 Chroma doc 的 metadata，省独立 KV，但 metadata 大小有限。
- 迁移时机：实体量超过 ~10k 或出现并发写问题时。

---

## 六、范围界定（OUT）

- 跨 collection rerank / 重排序融合。
- 图遍历检索（local search）、社区检测（Leiden）、global search。
- 真图存储（Neo4j/networkx）与多跳推理。
- 存储迁移到 SQLite/DB（搁置，见第五节）。
- 同名异实体的实体消歧/别名表。
- 既有文件的删除/修改触发的 wiki 同步。

---

## 七、实施步骤

> 每步可独立 `if __name__ == '__main__'` 自测，沿用既有风格。

- [ ] **T1 合并检索**
  - `rag/rag_service.py`：`RagSummarizeService.__init__` 加 `wiki_retriever`、新增 `retrieve_wiki_pages`、改 `rag_summarize_service` 拼装 merged context。
  - `tools/agent_tools.py`：单例创建顺序调整 + `rag` 注入 wiki retriever。
  - `config/wiki.yml`：加 `supplement_k` / `supplement_enabled`。
  - `prompts/rag_summarize.txt`：微调提示词。
  - 自测：`rag_summarize_service(query)` 返回的内容同时含切块与 wiki 卡片；wiki 空时降级。

- [ ] **T2 增量更新核心**
  - `prompts/wiki_update.txt`：新建。
  - `utils/prompt_loader.py` + `config/prompts.yml`：加 `load_wiki_update_prompts`。
  - `wiki/wiki_service.py`：新增 `update_page`；改 `build_from_documents` 为增量感知。
  - 自测：先建文件 A 的实体，再加入含同实体的文件 B，页面正文应含 A+B 信息。

- [ ] **T3 去重与触发**
  - `wiki/wiki_store.py`：`upsert_page` 删旧同名向量；新增 `is_source_processed` / `record_source_processed`。
  - `wiki/wiki_service.py`：`build_from_file`；`build_from_data_dir` 加 MD5 去重。
  - `config/wiki.yml`：加 `wiki_md5_store` / `auto_build_on_upload`。
  - `app.py`：`/api/upload` 成功后触发 `build_from_file`。
  - 自测：重复点 BUILD 不重复抽取；上传新文件后 wiki 自动增量更新。

- [ ] **T4 联调**
  - 上传文件 → 自动切块入 RAG + 增量建 wiki → 对话 `rag_summarize` 返回切块+wiki 合并结果 → wiki 页浏览见更新后实体。
  - 确认无重复向量、无旧信息丢失。

---

## 八、风险与取舍

| 风险/取舍 | 说明 | 应对 |
|---|---|---|
| 合并检索 context 变长 | 切块 + wiki 拼接使 context 增大，可能抬升 token 成本 | `supplement_k` 默认 3，可调；未来可加相关性阈值过滤 |
| 增量更新信息漂移 | update 链基于"现有正文+新记录"LLM 合并，多次更新可能轻微语义偏移 | 可接受；未来可保留原始记录快照彻底重建 |
| upsert 删旧向量依赖 Chroma API | `delete(where=...)` 在不同 `langchain_chroma` 版本支持不一 | 实现时先验证 API；不支持则 query-取-ids-再-delete |
| 增量触发拖慢上传 | 上传即建 wiki 增加耗时 | 失败不影响上传主流程；可异步化（未来） |
| JSON KV 并发写 | 多请求并发写 `wiki_store.json` 可能丢数据 | 当前单实例+锁可忍；规模化时迁移 SQLite（第五节） |
| 合并检索两路独立召回不去重 | 同一信息可能既在切块又在 wiki 卡片 | 最小原型接受冗余；未来加 rerank 去重 |

---

> 说明：本阶段仍不引入新依赖；所有改动在既有 `rag/`、`wiki/`、`tools/`、`app.py`、`prompts/`、`config/` 内完成，风格与封装不变。
