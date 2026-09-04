"""
实体/关系抽取服务：输入文档分片，LLM 抽取实体与关系，返回结构化记录
"""
import os
import sys
import json
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

    def _parse_result(self, raw: str) -> list[dict]:
        """解析 LLM 输出为实体记录列表，失败容错为空"""
        text = (raw or "").strip()
        # 容错：去掉可能的 markdown 代码块标记
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
            return data.get("entities", [])
        except Exception as e:
            logger.warning(f"[EntityExtractor]JSON解析失败：{str(e)}")
            return []

    def extract_from_documents(self, documents: list[Document]) -> list[dict]:
        """对每个分片调链，解析 JSON，聚合为实体记录列表"""
        all_records = []
        for doc in documents:
            try:
                raw = self.chain.invoke({"input": doc.page_content})
            except Exception as e:
                logger.error(f"[EntityExtractor]抽取调用失败：{str(e)}")
                continue

            entities = self._parse_result(raw)

            # 来源文件名（TextLoader/PyPDFLoader 把完整路径放在 metadata.source）
            source = ""
            if hasattr(doc, "metadata"):
                source = doc.metadata.get("source", "")
            if source:
                source = os.path.basename(source)

            for ent in entities:
                ent["source"] = source
                all_records.append(ent)

        logger.info(f"[EntityExtractor]共抽取{len(all_records)}条实体记录")
        return all_records


if __name__ == '__main__':
    from utils.path_tool import get_abs_path
    from utils.file_handler import txt_loader
    docs = txt_loader(get_abs_path("data/test_upload.txt"))
    print(EntityExtractor().extract_from_documents(docs))
