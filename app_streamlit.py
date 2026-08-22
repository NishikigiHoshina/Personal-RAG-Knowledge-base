
import time
import streamlit as st
from agent.react_agent import ReactAgent


# 标题
st.title("智能问答助手")
st.divider()
st.chat_message("assistant").write("你好，有什么可以帮你的？")

if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if "message" not in st.session_state:
    st.session_state["message"] = []

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

# 用户输入提示词
prompt = st.chat_input()
response_message = []

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role":"user","content":prompt})

    
    with st.spinner("思考中......"):
        res_stream = st.session_state["agent"].execute_stream(prompt)

        def capture(generator,cache_list):

            for chunk in generator:
                cache_list.append(chunk)
                yield chunk

                # for char in chunk:
                #     time.sleep(0.01)
                #     yield char

        st.chat_message("assistant").write_stream(capture(res_stream,response_message))
        st.session_state["message"].append({"role":"assistant","content":response_message[-1]})
        st.rerun()