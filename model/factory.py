"""
创建模型对象的工厂
"""

from abc import ABC,abstractmethod
from typing import Optional
from langchain_core.embeddings import Embeddings
#from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_deepseek.chat_models import ChatDeepSeek
from langchain_ollama.embeddings import OllamaEmbeddings
from utils.config_handler import rag_conf


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self)-> Optional[Embeddings | ChatDeepSeek]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | ChatDeepSeek]:
        return ChatDeepSeek(model=rag_conf["chat_model_name"],api_key=rag_conf["api_key"],temperature=rag_conf["temperature"])

class EmbeddingsFactory(BaseModelFactory):
    def generator(self)->Optional[Embeddings | ChatDeepSeek]:
        return OllamaEmbeddings(model=rag_conf["embedding_model_name"])


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingsFactory().generator()