"""
Wiki 存储服务
JSON KV 存 wiki 页面，Chroma 单独 collection 存页面向量
"""
import json
import sys
import os
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

    def _load_kv(self) -> dict:
        if not os.path.exists(self.kv_path):
            return {}
        try:
            with open(self.kv_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[WikiStore]加载KV失败：{str(e)}")
            return {}

    def _save_kv(self) -> None:
        try:
            with open(self.kv_path, "w", encoding="utf-8") as f:
                json.dump(self.pages, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[WikiStore]保存KV失败：{str(e)}")

    def upsert_page(self, name: str, page: dict) -> None:
        """新增/更新页面：写 KV + 写向量库"""
        self.pages[name] = page
        self._save_kv()

        # 页面文本 = 名称 + 描述 + 关系摘要，用于 embedding 检索
        rels = "；".join(
            f"{r.get('target','')}({r.get('desc','')})"
            for r in page.get("relationships", [])
        )
        content = f"{page.get('name', name)}：{page.get('description','')}"
        if rels:
            content += f" | 关系：{rels}"

        doc = Document(
            page_content=content,
            metadata={"name": name, "type": page.get("type", "")}
        )
        # 注：本最小原型不处理向量库内的同名旧记录，重复构建会产生重复向量
        # 在 WikiBuildService.query 中按 name 去重，保证返回不重复
        self.vector_store.add_documents([doc])
        logger.info(f"[WikiStore]页面已写入：{name}")

    def get_page(self, name: str) -> dict | None:
        return self.pages.get(name)

    def list_pages(self) -> list[dict]:
        result = []
        for name, page in self.pages.items():
            result.append({
                "name": name,
                "type": page.get("type", ""),
                "description": page.get("description", ""),
                "rel_count": len(page.get("relationships", [])),
                "sources": [s.get("file", "") for s in page.get("sources", [])],
            })
        return result

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": wiki_conf["k"]})


if __name__ == '__main__':
    ws = WikiStoreService()
    print(ws.list_pages())
    retriever = ws.get_retriever()
    res = retriever.invoke("夏亚")
    for r in res:
        print(r.page_content)
        print("-" * 20)
