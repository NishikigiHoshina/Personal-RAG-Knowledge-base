"""
配置文件工具
yaml
k : v

"""

import yaml
from utils.path_tool import get_abs_path
#from path_tool import get_abs_path

def load_rag_config(config_path:str=get_abs_path("config/rag.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_chroma_config(config_path:str=get_abs_path("config/chroma.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_prompts_config(config_path:str=get_abs_path("config/prompts.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_agent_config(config_path:str=get_abs_path("config/agent.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_system_config(config_path:str=get_abs_path("config/system.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_wiki_config(config_path:str=get_abs_path("config/wiki.yml"),encoding:str = "utf-8"):
    with open(config_path,"r",encoding="utf-8") as f:
        return yaml.load(f,Loader=yaml.FullLoader)



rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()
agent_conf = load_agent_config()
system_conf = load_system_config()
wiki_conf = load_wiki_config()

if __name__=='__main__':
    print(rag_conf["chat_model_name"])