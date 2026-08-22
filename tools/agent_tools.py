"""
Agent工具能力
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import os
from datetime import datetime
from tools.getweather import get_weather as get_weather_from_tool
from tools.log_parser import search_logs_simple, LogSearcher
from langchain_core.tools import tool
from rag.rag_service import RagSummarizeService
from utils.config_handler import agent_conf,system_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

rag = RagSummarizeService()

external_data = {}

@tool(description="当用户要求从知识库中获取资料时调用，从向量存储中检索参考资料，入参为用户的提问信息query，返回值为字符串")
def rag_summarize(query:str)-> str:
    return rag.rag_summarize_service(query)

@tool(description="获取指定城市的天气，以消息字符串的形式返回")
def get_weather(city:str)->str:

    response = get_weather_from_tool(city)
    weather = response['天气']
    temp = response['气温']
    
    return f"城市{city}：天气 {weather}，气温{temp}"

@tool(description="获取用户城市的名称，以纯字符串形式返回")
def get_user_location()->str:
    return "深圳"

@tool(description="获取用户的ID，以纯字符串的形式返回")
def get_user_id() -> str:
    if system_conf["user_id"]:
        uid = system_conf["user_id"]
        return uid
    else:
        return "当前用户未登录，无法获取uid"

@tool(description="获取当前月份，以纯字符串形式返回")
def get_current_month()->str:
    current_month = datetime.now().strftime("%Y-%m")
    return "当前是"+current_month

@tool(description="获取当前的时间")
def get_time_now()->str:
    current_time = datetime.now()
    return current_time


# 抽取外部数据，并做格式化处理
def generate_external_data(user_id:str):

    if not external_data:
        external_data_path = get_abs_path(agent_conf["external_data_path"])

        if not os.path.exists(external_data_path):
            raise FileNotFoundError(f"外部数据文件{external_data_path}不存在")

        results = search_logs_simple(external_data_path, user_id)
        return results



@tool(description="获取用户的使用记录，以纯字符串的形式返回，如果没有检索到则返回空字符串")
def fetch_external_data(user_id:str,month:str)->str:
    external_data = generate_external_data(user_id)

    try:
        return external_data
    except KeyError:
        logger.warning(f"[fetch_external_data]未检索到用户：{user_id}在{month}的使用记录数据")
        return ""
    

@tool(description="无入参，无返回值，调用后触发中间件自动为报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息")
def fill_context_for_report():
    return "fill_context_for_report已调用"



if __name__=='__main__':
    print(get_current_month())
    print(fetch_external_data("LC12808","2025-01"))