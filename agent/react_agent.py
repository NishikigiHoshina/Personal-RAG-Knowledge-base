"""
智能体类
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from tools.agent_tools import (rag_summarize,get_weather,get_user_id,get_user_location,
                               get_current_month,get_time_now,fetch_external_data,fill_context_for_report)
from tools.middleware import monitor_tool,log_before_model,report_prompt_switch


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize,get_weather,get_user_id,get_current_month,get_time_now,
                   fetch_external_data,fill_context_for_report,get_user_location],
            middleware=[monitor_tool,log_before_model,report_prompt_switch],
        )


    def execute_stream(self,query:str):
        input_dict = {
            "messages":[
                {"role":"user","content":query},
            ]
        }

        # context就是上下文runtime中的信息，就是我们做提示词切换的标记
        res = self.agent.stream(input_dict,stream_mode="values",context={"report":False})

        for chunk in res:
            latest_message = chunk["messages"][-1]

            if latest_message:
                yield latest_message.content.strip() + "\n"


if __name__=='__main__':
    agent = ReactAgent()

    res = agent.execute_stream("纵观整个故事，夏亚是个怎样的人，你如何评价他")

    for chunk in res:
        print(chunk,end="",flush=True)