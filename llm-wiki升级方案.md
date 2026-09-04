# llm-wiki 知识库体系升级方案

> 目标：依照 **llm-wiki 理念**，在现有 RAG 项目基础上搭建"实体为中心、交叉引用、带来源"的 wiki 风格知识库最小原型。
> 本文档为**计划文档**，不涉及任何实际代码改动。实施时严格遵循本项目既有编码风格与模块封装方式。

---

## 目录

- [一、背景与目标](#一背景与目标)
- [二、llm-wiki 理念研究结论](#二llm-wiki-理念研究结论)
- [三、与现有项目的差距分析](#三与现有项目的差距分析)
- [四、升级方案总览](#四升级方案总览)
- [五、模块设计](#五模块设计)
- [六、数据模型](#六数据模型)
- [七、配置与提示词](#七配置与提示词)
- [八、集成点](#八集成点)
- [九、最小原型范围界定](#九最小原型范围界定)
- [十、实施步骤](#十实施步骤)
- [十一、风险与取舍](#十一风险与取舍)
- [参考来源](#参考来源)

---

## 一、背景与目标

### 1.1 背景
当前项目（v0.1.0）已实现**扁平 RAG**：文档切片 → Chroma 向量库 → top-k 检索 → LLM 总结。知识组织单元是"文本块"，检索结果是无结构的参考资料片段。

llm-wiki 理念主张：用 LLM 从文档中抽取**实体与关系**，生成**结构化、交叉引用、带来源引用的 wiki 页面**，使知识库既能被 Agent 检索，也能被人直接浏览。

### 1.2 目标
- **搭建最小原型**：在不动现有扁平 RAG 的前提下，新增一套 wiki 知识库体系，与原 RAG 并存。
- **复刻现有风格**：新模块的类封装、配置加载、LCEL 链、`@tool` 注册、路径/日志工具全部沿用本项目既有写法。
- **可浏览可检索**：提供 wiki 浏览 UI + 一个 Agent 工具 `wiki_query`。
- **明确边界**：社区检测、全局/局部双检索、图数据库等 GraphRAG 重型能力**不纳入**最小原型，仅作未来演进方向记录。

---

## 二、llm-wiki 理念研究结论

### 2.1 llm-wiki 核心理念
llm-wiki（参考 Pointerstudio/llm-wiki）的处理流水线为：

```
文档 → 切片+向量化 → LLM 抽取实体与关系 → 生成结构化 wiki 页面（带内部链接）→ 引用回溯源文档 → Web UI 浏览
```

四个关键特征：
1. **实体为中心** —— 知识单元是"实体/概念卡片"，而非原始文本块。
2. **交叉引用** —— 页面之间通过关系互链，形成可导航的知识网络。
3. **来源可溯** —— 每条 wiki 陈述都标注源自哪个文档/片段，抑制幻觉。
4. **人机双用** —— 既能被 Agent 检索，也能被人用 UI 浏览阅读。

### 2.2 建库期与查询期的职责划分（认知澄清）
llm-wiki 的本质是把"知识组织"从查询时**前移到建库时**，形成两个清晰分离的阶段：

- **建库期（预处理）**：LLM 抽取实体/关系 → 组织成 wiki 页面（含交叉引用 + 来源）。在用户提问之前完成。
- **查询期（检索）**：RAG 流程不变（仍要 embed、检索、喂 LLM），但检索对象从"原始文档切块"升级为"LLM 组织过的 wiki 实体卡片"。

需强调的是，"检索对象换成 wiki"只覆盖了**最朴素的纯向量检索**形式。关系数据一旦建出，查询端实际能做的事更多：

| 检索模式 | 机制 | 是否向量检索 |
|---|---|---|
| 纯向量召回 wiki 页面 | embed wiki 页面 → 相似度检索 | 是 |
| local search（图遍历） | 向量召回实体 + 沿关系游走召回邻居 + 相关切块 | 混合 |
| global search（社区摘要） | 图聚类成社区 → 社区摘要 map-reduce | 否 |

> **本最小原型只实现"纯向量召回 wiki 页面"（上表第一行）**，local/global 两种更高级模式列为 OUT。关系数据在本原型中仅用于前端互链跳转展示，不参与检索算法。

### 2.3 同类开源实现对比

| 项目 | 核心机制 | 复杂度 | 对本方案的参考价值 |
|---|---|---|---|
| **llm-wiki** (Pointerstudio) | 实体抽取 → wiki 页面生成 → 内链 + 引用 | 中 | **主参考**：流水线形态、页面+引用模型 |
| **nano-graphrag** (gusye1234) | 实体抽取 → 知识图 → Leiden 社区 → 社区摘要；KV/向量/图三存储；local/global 双检索 | 极简(~1k 行) | **存储分层 + 抽取 prompt** 参考；社区检测不纳入 |
| **LightRAG** (HKUDS) | 双层知识图 + 双级检索，支持增量更新 | 高 | 增量更新与双层检索作为演进方向参考 |
| **MS GraphRAG** | 社区检测 + 层级摘要 + 全局 map-reduce 检索 | 高 | 论文方法论参考，实现过重不纳入 |

### 2.4 采纳与舍弃
- **采纳**（来自 llm-wiki + nano-graphrag）：LLM 抽取实体/关系、生成 wiki 页面、JSON KV 存页面、Chroma 存页面向量用于检索、来源引用追溯。
- **舍弃**（超出最小原型）：Leiden 社区检测、社区摘要、global map-reduce 检索、Neo4j/networkx 图存储、增量图更新算法。

---

## 三、与现有项目的差距分析

| 维度 | 现状（扁平 RAG） | llm-wiki 升级后 |
|---|---|---|
| 知识单元 | 文本块（chunk） | 实体 wiki 页面（含描述/关系/来源） |
| 抽取方式 | 仅切分，不抽取 | LLM 抽取实体与关系 |
| 存储 | Chroma 单 collection | Chroma 原 collection + 新 wiki collection + JSON KV |
| 检索单元 | chunk 文本 | wiki 页面（实体卡片） |
| 可读性 | 仅 Agent 消费 | 人可浏览（UI） + Agent 可检索 |
| 可溯源性 | chunk 带文件元数据 | 页面带源文档 + 源片段引用 |
| 关系网络 | 无 | 页面间关系互链（轻量邻接） |

**可复用的现有模块**（不重写）：
- `model/factory.py`：`chat_model` / `embed_model` 全局单例。
- `utils/path_tool.py`：`get_abs_path`。
- `utils/file_handler.py`：`txt_loader`/`pdf_loader`/`markdown_loader`/`get_file_md5_hex`/`listdir_with_allowed_type`。
- `utils/logger_handler.py`：`logger`。
- `utils/config_handler.py` 的加载器风格、`utils/prompt_loader.py` 的加载器风格。
- `rag/vector_store.py` 的 `RecursiveCharacterTextSplitter` 分片器（wiki 构建前先复用分片）。

---

## 四、升级方案总览

```
┌──────────────────────────────────────────────────────────────────┐
│  入口层  app.py                                                    │
│  新增路由：/api/wiki/build · /api/wiki · /api/wiki/<name>          │
│  上传后可选触发 wiki 构建                                            │
└───────────────┬──────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────┐
│  Agent 层  react_agent.py   新增工具 wiki_query                     │
└────┬─────────────────────────────────────────────────────────────┘
     │
┌────▼─────────────────────────────────────────────────────────────┐
│  新增 wiki 层  wiki/                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ extractor.py │→│ wiki_service │→│ wiki_store.py            │ │
│  │ 实体/关系抽取 │  │ wiki 构建+检索│  │ JSON KV + Chroma(页面)  │ │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘ │
└────┬─────────────────────────────────────────────────────────────┘
     │ 复用
┌────▼─────────────────────────────────────────────────────────────┐
│  模型层 model/factory  ·  基础设施 utils/  ·  config/wiki.yml     │
│  prompts/wiki_extract.txt · prompts/wiki_build.txt                │
└──────────────────────────────────────────────────────────────────┘
```

**设计原则**：
1. `wiki/` 与 `rag/` 平级，互不侵入；原扁平 RAG 完全保留。
2. 每个 wiki 模块都参照一个既有同类模块的封装写法（见第五节）。
3. 不引入新依赖（除已存在于 `require.txt` 的 json/yaml 标准库外），不引入图数据库。

---

## 五、模块设计

> 以下签名与写法严格对标本项目既有风格：模块级中文 docstring、`sys.path.append`、类封装、`get_abs_path`、`logger`、LCEL 链、`@tool` 中文 description。

### 5.1 `wiki/wiki_store.py`  —— 对标 `rag/vector_store.py`

```python
"""
Wiki 存储服务
JSON KV 存 wiki 页面，Chroma 单独 collection 存页面向量
"""
import json, sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import wiki_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger
from model.factory import embed_model


class WikiStoreService:
    def __init__(self):
        # KV：实体名 -> 页面 dict，落盘为 JSON
        self.kv_path = get_abs_path(wiki_conf["wiki_kv_path"])
        self.pages: dict[str, dict] = self._load_kv()
        # 页面向量库（独立 collection，不污染原 agent collection）
        self.vector_store = Chroma(
            collection_name=wiki_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=get_abs_path(wiki_conf["persist_directory"])
        )

    def _load_kv(self) -> dict: ...
    def _save_kv(self) -> None: ...
    def upsert_page(self, name: str, page: dict) -> None:
        """新增/更新页面：写 KV + 写向量库（页面文本=描述+关系摘要）"""
    def get_page(self, name: str) -> dict | None: ...
    def list_pages(self) -> list[dict]: ...
    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": wiki_conf["k"]})


if __name__ == '__main__':
    ws = WikiStoreService()
    print(ws.list_pages())
```

### 5.2 `wiki/extractor.py`  —— 对标 `rag/rag_service.py`（LCEL 链）

```python
"""
实体/关系抽取服务：输入文档分片，LLM 抽取实体与关系，返回结构化记录
"""
import sys, json
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from model.factory import chat_model
from utils.prompt_loader import load_wiki_extract_prompts
from utils.logger_handler import logger


class EntityExtractor:
    def __init__(self):
        self.prompt_text = load_wiki_extract_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self.prompt_template | self.model | StrOutputParser()

    def extract_from_documents(self, documents: list[Document]) -> list[dict]:
        """对每个分片调链，解析 JSON，聚合为实体记录列表"""
        # 返回 [{"name":..., "type":..., "description":..., "relationships":[{"target":...,"desc":...}], "source":文件名}]
        ...


if __name__ == '__main__':
    from utils.file_handler import txt_loader
    docs = txt_loader(get_abs_path("data/test_upload.txt"))
    print(EntityExtractor().extract_from_documents(docs))
```

> JSON 解析采用"模型输出字符串 → `json.loads` → 失败容错为空列表"的简写，符合本项目"先用起来"的实用风格，不引入 Pydantic 解析器依赖。

### 5.3 `wiki/wiki_service.py`  —— 对标 `rag/rag_service.py`（编排 + 检索）

```python
"""
Wiki 构建与检索服务：编排 抽取→聚合→页面生成→存储，并提供 wiki 检索
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from model.factory import chat_model
from utils.prompt_loader import load_wiki_build_prompts
from utils.logger_handler import logger
from wiki.extractor import EntityExtractor
from wiki.wiki_store import WikiStoreService


class WikiBuildService:
    def __init__(self):
        self.extractor = EntityExtractor()
        self.store = WikiStoreService()
        self.build_prompt = PromptTemplate.from_template(load_wiki_build_prompts())
        self.model = chat_model
        self.build_chain = self.build_prompt | self.model | StrOutputParser()

    def build_from_documents(self, documents: list, source_name: str) -> int:
        """完整构建：抽取→按实体名聚合→逐实体生成页面→入库；返回页面数"""
        ...

    def build_page(self, name: str, records: list[dict]) -> dict:
        """对单实体：汇总其所有出现记录，调 build_chain 生成 wiki 页面文本+关系+来源"""
        ...

    def query(self, query: str) -> list[dict]:
        """检索 wiki 页面（向量库 top-k），返回页面 dict 列表"""
        docs = self.store.get_retriever().invoke(query)
        return [self.store.get_page(d.metadata["name"]) for d in docs]


if __name__ == '__main__':
    svc = WikiBuildService()
    # 从 data/ 批量构建
    ...
```

---

## 六、数据模型

### 6.1 wiki 页面结构（JSON KV 的一条记录）
```json
{
  "name": "夏亚·阿兹纳布尔",
  "type": "人物",
  "description": "吉翁公国的王牌驾驶员，被称为红色彗星。",
  "relationships": [
    {"target": "吉翁公国", "desc": "隶属于"},
    {"target": "阿姆罗·雷", "desc": "宿敌"}
  ],
  "sources": [
    {"file": "test_upload.txt", "md5": "...", "chunk_id": "..."}
  ],
  "updated_at": "2026-09-04T..."
}
```

### 6.2 Chroma wiki collection 的 Document
- `page_content`：`name + description + 关系摘要`（用于 embedding 检索）。
- `metadata`：`{"name": 实体名, "type": 类型, "sources_files": [文件名]}`。

### 6.3 关系网络
最小原型**不建独立图结构**，关系仅作为页面内的 `relationships` 列表存储；前端渲染时把 `target` 渲染为可点击跳转链接即可呈现"互链"效果。这是用最小代价获得 wiki 互链观感。

---

## 七、配置与提示词

### 7.1 新增 `config/wiki.yml`（对标 `chroma.yml`）
```yaml
collection_name: wiki            # 与原 agent collection 隔离
persist_directory: chroma_db
wiki_kv_path: wiki_store.json    # 页面 KV 落盘
k: 5                             # wiki 页面检索 top-k
wiki_file_type: ["txt","pdf","md"]
```

### 7.2 `utils/config_handler.py` 增量（对标现有 5 个 loader）
新增 `load_wiki_config()` 函数 + 模块级 `wiki_conf = load_wiki_config()`。

### 7.3 `utils/prompt_loader.py` 增量（对标现有 3 个 loader）
新增 `load_wiki_extract_prompts()`、`load_wiki_build_prompts()`，并在 `config/prompts.yml` 增加：
```yaml
wiki_extract_prompt_path: prompts/wiki_extract.txt
wiki_build_prompt_path: prompts/wiki_build.txt
```

### 7.4 新增提示词文件
- `prompts/wiki_extract.txt`：给定文本片段，输出 JSON：实体列表 + 每个实体的类型/描述/关系。强约束"仅输出 JSON，不附加说明"（沿用 `rag_summarize.txt` 的约束写法）。
- `prompts/wiki_build.txt`：给定某实体的多条出现记录与来源片段，生成该实体的 wiki 页面（描述 + 关系 + 来源标注），约束"基于资料，不编造"（沿用 `rag_summarize.txt` 的合规性约束）。

---

## 八、集成点

### 8.1 Agent 工具（对标 `rag_summarize`）
`tools/agent_tools.py` 新增：
```python
from wiki.wiki_service import WikiBuildService
wiki_service = WikiBuildService()   # 模块级单例，对标 rag = RagSummarizeService()

@tool(description="当用户要求查阅 wiki 知识卡片/实体资料时调用，从 wiki 知识库检索实体页面，入参为查询query，返回值为字符串")
def wiki_query(query: str) -> str:
    pages = wiki_service.query(query)
    # 格式化为参考资料字符串（对标 rag_summarize_service 的 context 拼装）
    ...
```
`agent/react_agent.py` 的 `tools=[...]` 中加入 `wiki_query`。

### 8.2 Flask 路由（`app.py` 增量）
- `POST /api/wiki/build`：读取 `data/` 下文件 → 分片 → `wiki_service.build_from_documents` → 返回构建页面数。
- `GET /api/wiki`：返回 `list_pages()`（实体名/类型/关系数）。
- `GET /api/wiki/<name>`：返回单页面详情。
- `/api/upload` 成功后**可选**触发对该文件的 wiki 构建（开关由 `wiki_conf` 控制，默认关，避免影响上传耗时）。

### 8.3 前端（对标"对话/上传"两页结构）
在 `templates/index.html` 侧边栏新增第三个导航项 **"知识库 WIKI"**，新增 `page-wiki`：
- 列表区：实体卡片表格（名称、类型、关系数、来源文件）。
- 详情区：点击实体 → 展示描述 + 关系列表（`target` 可点击跳转）+ 来源引用（文件名 + md5）。
- 新增 `static/js/wiki.js`（对标 `upload.js` 的 fetch + 渲染写法）。
- 复用 `static/css/style.css` 的 Ark UI token，不引入新设计语言。

---

## 九、最小原型范围界定

### IN（本原型交付）
- [x] 实体 + 关系抽取（每分片一次 LLM 调用，JSON 输出）
- [x] 按实体名聚合记录
- [x] wiki 页面生成（描述 / 关系 / 来源）
- [x] JSON KV 存储 + Chroma wiki collection 检索
- [x] Agent 工具 `wiki_query`
- [x] wiki 浏览 UI（列表 + 详情 + 关系跳转）
- [x] `/api/wiki/build` 批量构建入口

### OUT（明确不纳入，记为演进方向）
- [ ] Leiden 社区检测与社区摘要
- [ ] global（map-reduce）/ local 双模式检索
- [ ] Neo4j / networkx 真图存储与图算法
- [ ] 增量图更新算法（实体合并/去重的高级策略）
- [ ] 人工编辑 wiki 页面
- [ ] 多跳关系推理

---

## 十、实施步骤

> 每步均可独立验证，遵循本项目"`if __name__=='__main__'` 自测"惯例。

1. **配置与提示词骨架** —— 新增 `config/wiki.yml`、`prompts/wiki_extract.txt`、`prompts/wiki_build.txt`；在 `config_handler.py`/`prompt_loader.py`/`prompts.yml` 增量加载函数。
2. **存储层** —— 实现 `wiki/wiki_store.py`（KV + Chroma），`__main__` 自测空载入/读写。
3. **抽取层** —— 实现 `wiki/extractor.py`，`__main__` 用 `data/test_upload.txt` 自测抽取结果。
4. **构建+检索层** —— 实现 `wiki/wiki_service.py`，`__main__` 自测从 `data/` 全量构建并 `query`。
5. **Agent 工具** —— 在 `agent_tools.py` 加 `wiki_query`，在 `react_agent.py` 注册。
6. **Flask 路由** —— `app.py` 加 `/api/wiki/*` 三个路由。
7. **前端** —— `index.html` 加导航与页面、`wiki.js` 渲染、`style.css` 增量样式。
8. **联调** —— 上传一份文档 → 触发 wiki 构建 → 在 UI 浏览实体 → 在对话中让 Agent 调 `wiki_query` 验证闭环。

---

## 十一、风险与取舍

| 风险/取舍 | 说明 | 应对 |
|---|---|---|
| 抽取成本 | 每分片一次 LLM 调用，文档多时开销大 | 最小原型接受；演进方向：批量合并抽取、缓存 |
| JSON 解析失败 | LLM 偶发输出非合法 JSON | 容错为空记录 + logger.warning，不阻断流程 |
| 实体归并粗糙 | 同名异实体、异名同实体 | 最小原型仅按精确名称聚合；演进方向：别名表/模糊匹配 |
| 关系互链仅前端 | 未建真图，关系查询不能多跳 | 明确为 OUT；UI 渲染 `target` 跳转已满足"互链观感" |
| 与原 RAG 共存 | 两套知识库可能让用户困惑 | 工具 description 明确区分：`rag_summarize`=参考资料总结，`wiki_query`=实体 wiki 卡片 |
| 上传耗时 | 上传即触发 wiki 构建会拖慢上传 | 默认关，提供独立 `/api/wiki/build` 手动触发 |

---

## 参考来源

- llm-wiki（Pointerstudio）：<https://github.com/Pointerstudio/llm-wiki> —— wiki 风格知识库主参考
- nano-graphrag（gusye1234）：<https://github.com/gusye1234/nano-graphrag> —— 极简 GraphRAG 存储/抽取参考
- LightRAG（HKUDS）：<https://github.com/HKUDS/LightRAG> —— 双层检索与增量更新演进方向
- Microsoft GraphRAG：<https://github.com/microsoft/graphrag> —— 论文方法论来源
- RAGFlow：<https://github.com/infiniflow/ragflow> —— 中文知识库工程化参考
