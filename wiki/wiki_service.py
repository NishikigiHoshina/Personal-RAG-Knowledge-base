"""
Wiki 构建与检索服务：编排 抽取→聚合→页面生成→存储，并提供 wiki 检索
"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from model.factory import chat_model
from utils.prompt_loader import load_wiki_build_prompts
from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path
from utils.file_handler import (
    txt_loader, pdf_loader, markdown_loader, listdir_with_allowed_type
)
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
        # 复用 RAG 的分片参数（来自 chroma.yml），避免再开 VectiorStoreService 的 Chroma
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def build_page(self, name: str, records: list[dict]) -> dict:
        """对单实体：汇总其所有出现记录，调 build_chain 生成 wiki 页面"""
        records_text = ""
        for i, r in enumerate(records, 1):
            records_text += f"[记录{i}] 描述：{r.get('description','')}"
            rels = r.get("relationships", [])
            if rels:
                rels_str = "；".join(
                    f"{rel.get('target','')}({rel.get('desc','')})" for rel in rels
                )
                records_text += f" | 关系：{rels_str}"
            records_text += f" | 来源：{r.get('source','')}\n"

        try:
            page_text = self.build_chain.invoke({"name": name, "records": records_text})
        except Exception as e:
            logger.error(f"[WikiBuild]生成页面失败 {name}：{str(e)}")
            page_text = records[0].get("description", "") if records else ""

        # 聚合关系与来源
        relationships = []
        sources = []
        seen_rel = set()
        for r in records:
            for rel in r.get("relationships", []):
                key = (rel.get("target"), rel.get("desc"))
                if rel.get("target") and key not in seen_rel:
                    seen_rel.add(key)
                    relationships.append(rel)
            if r.get("source"):
                sources.append({"file": r["source"]})

        return {
            "name": name,
            "type": records[0].get("type", "") if records else "",
            "description": page_text.strip(),
            "relationships": relationships,
            "sources": sources,
            "updated_at": datetime.now().isoformat(),
        }

    def build_from_documents(self, documents: list[Document], source_name: str = "") -> int:
        """完整构建：抽取→按实体名聚合→逐实体生成页面→入库；返回页面数"""
        if not documents:
            logger.warning("[WikiBuild]无文档可构建")
            return 0

        # 分片
        split_docs = self.spliter.split_documents(documents)
        if not split_docs:
            logger.warning("[WikiBuild]分片后无有效内容")
            return 0

        logger.info(f"[WikiBuild]开始抽取，共{len(split_docs)}个分片")
        records = self.extractor.extract_from_documents(split_docs)
        if not records:
            logger.warning("[WikiBuild]未抽取到任何实体")
            return 0

        # 按实体名聚合
        grouped: dict[str, list[dict]] = {}
        for r in records:
            name = r.get("name", "").strip()
            if not name:
                continue
            grouped.setdefault(name, []).append(r)

        logger.info(f"[WikiBuild]聚合为{len(grouped)}个实体，开始生成页面")
        count = 0
        for name, recs in grouped.items():
            page = self.build_page(name, recs)
            self.store.upsert_page(name, page)
            count += 1

        logger.info(f"[WikiBuild]构建完成，共{count}个页面")
        return count

    def build_from_data_dir(self) -> int:
        """从 data/ 目录读取所有允许类型文件，批量构建"""
        allowed = tuple(chroma_conf.get("allow_knowledge_file_type", ["txt", "pdf", "md"]))
        loader_map = {"txt": txt_loader, "pdf": pdf_loader, "md": markdown_loader}

        paths = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]), allowed
        )
        total = 0
        for path in paths:
            ext = path.rsplit(".", 1)[-1].lower()
            loader = loader_map.get(ext)
            if not loader:
                continue
            try:
                docs = loader(path)
                total += self.build_from_documents(docs, source_name=path)
            except Exception as e:
                logger.error(f"[WikiBuild]处理{path}失败：{str(e)}", exc_info=True)
        return total

    def query(self, query: str) -> list[dict]:
        """向量检索 wiki 页面，返回页面 dict 列表（按 name 去重）"""
        docs = self.store.get_retriever().invoke(query)
        result = []
        seen = set()
        for d in docs:
            name = d.metadata.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            page = self.store.get_page(name)
            if page:
                result.append(page)
        return result


if __name__ == '__main__':
    svc = WikiBuildService()
    n = svc.build_from_data_dir()
    print(f"构建页面数：{n}")
    res = svc.query("夏亚")
    for p in res:
        print(p)
        print("-" * 20)
