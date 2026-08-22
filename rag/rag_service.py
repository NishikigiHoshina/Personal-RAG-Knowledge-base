"""
总结服务类：用户提问，搜索参考资料，将提问和参考资料提交给模型，让模型总结回复
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from rag.vector_store import VectiorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from model.factory import chat_model



def print_prompt(prompt):
    print("="*10)
    print(prompt.to_string())
    print("="*10)
    return prompt

class RagSummarizeService(object):
    def __init__(self):
        self.vector_store = VectiorStoreService()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_text = load_rag_prompts()
        self.prompt_templage = PromptTemplate.from_template(self.prompt_text)

        self.model = chat_model
        self.chain = self._init_chain()


    def _init_chain(self):
        chain = self.prompt_templage | print_prompt | self.model | StrOutputParser()
        return chain

    def retriever_docs(self,query:str)->list[Document]:
        return self.retriever.invoke(query)


    def rag_summarize_service(self,query:str)->str:
        context_docs = self.retriever_docs(query)

        context = ""
        counter = 0
        for doc in context_docs:
            counter +=1
            context += f"[参考资料{counter}]:参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"

        return self.chain.invoke(
            {
                "input":query,
                "context":context,
            }
        )



if __name__=='__main__':
    rag = RagSummarizeService()
    print(rag.rag_summarize_service("纵观整个故事，夏亚是个怎样的人，你如何评价他"))