"""
Flask 前端入口 — RAG 智能问答助手
支持 SSE 流式对话 + 工具调用可视化 + 文件上传入库
"""
import json
import os
import uuid
import time
import threading
import secrets
from pathlib import Path

from flask import Flask, Response, request, jsonify, render_template, session

# LangChain message types for tool call detection
from langchain_core.messages import AIMessage, ToolMessage

from agent.react_agent import ReactAgent

# ── 文件上传相关 ─────────────────────────────────────────
from tools.agent_tools import rag  # 模块级单例，获取向量库访问
from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path
from utils.file_handler import txt_loader, pdf_loader, get_file_md5_hex
from utils.logger_handler import logger

ALLOWED_EXTENSIONS = {"txt", "pdf"}

# ── App 初始化 ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ── Agent 单例（惰性初始化，线程安全） ─────────────────────
_agent_lock = threading.Lock()
_agent: ReactAgent | None = None


def get_agent() -> ReactAgent:
    """惰性单例：首次调用时创建 ReactAgent，后续复用。
    LangGraph 的 stream() 支持并发调用，每次创建独立状态，线程安全。"""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = ReactAgent()
    return _agent


# ── Session 存储（服务端内存，UUID 隔离） ──────────────────
_store_lock = threading.Lock()
session_store: dict[str, dict] = {}

SESSION_TTL_SECONDS = 3600  # 1 小时过期


def _make_session() -> dict:
    return {"messages": [], "tool_logs": [], "last_access": time.time()}


def _get_or_create_sid() -> str:
    sid = session.get("sid")
    if not sid or sid not in session_store:
        sid = str(uuid.uuid4())
        session["sid"] = sid
        with _store_lock:
            session_store[sid] = _make_session()
    else:
        # 刷新访问时间
        with _store_lock:
            if sid in session_store:
                session_store[sid]["last_access"] = time.time()
    return sid


def _add_message(sid: str, role: str, content: str) -> None:
    with _store_lock:
        if sid in session_store:
            session_store[sid]["messages"].append({"role": role, "content": content})


def _get_messages(sid: str) -> list:
    with _store_lock:
        return list(session_store.get(sid, {}).get("messages", []))


def _add_tool_log(sid: str, entry: dict) -> None:
    with _store_lock:
        if sid in session_store:
            session_store[sid]["tool_logs"].append(entry)


def _get_tool_logs(sid: str) -> list:
    with _store_lock:
        return list(session_store.get(sid, {}).get("tool_logs", []))


def _cleanup_expired_sessions() -> None:
    """后台清理过期会话，防止内存无限增长"""
    while True:
        time.sleep(300)  # 每 5 分钟清理一次
        now = time.time()
        with _store_lock:
            expired = [
                k
                for k, v in session_store.items()
                if now - v.get("last_access", 0) > SESSION_TTL_SECONDS
            ]
            for k in expired:
                del session_store[k]


# 启动清理线程
_cleanup_thread = threading.Thread(target=_cleanup_expired_sessions, daemon=True)
_cleanup_thread.start()

# ── 路由 ───────────────────────────────────────────────────


@app.route("/")
def index():
    """返回聊天页面"""
    return render_template("index.html")


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """核心：SSE 流式对话接口。
    接收 {"query": "用户消息"}，返回 text/event-stream。

    SSE 事件类型：
    - text:      助手文本块（完整替换模式）
    - tool_call: 即将调用的工具信息
    - tool_result: 工具返回结果
    - done:      流结束
    - error:     异常信息
    """
    data = request.get_json(silent=True) or {}
    query = (data.get("query", "") or "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    sid = _get_or_create_sid()
    _add_message(sid, "user", query)

    def generate():
        try:
            agent = get_agent()
            input_dict = {"messages": [{"role": "user", "content": query}]}
            full_text_parts: list[str] = []

            for chunk in agent.agent.stream(
                input_dict, stream_mode="values", context={"report": False}
            ):
                messages = chunk.get("messages", [])
                if not messages:
                    continue

                latest = messages[-1]

                # ── AI 消息：可能包含 tool_calls 和/或文本 ──
                if isinstance(latest, AIMessage):
                    # 检测工具调用
                    tool_calls = getattr(latest, "tool_calls", None) or []
                    for tc in tool_calls:
                        event = {
                            "type": "tool_call",
                            "tool_name": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        }
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        _add_tool_log(sid, event)

                    # 输出文本内容（完整内容，前端会替换而非追加）
                    content = latest.content
                    if isinstance(content, str) and content.strip():
                        full_text_parts.append(content)
                        yield f"data: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                    elif isinstance(content, list):
                        # 结构化内容：提取文本部分
                        text_parts = [
                            item.get("text", "")
                            for item in content
                            if isinstance(item, dict) and item.get("type") == "text"
                        ]
                        combined = "".join(text_parts)
                        if combined.strip():
                            full_text_parts.append(combined)
                            yield f"data: {json.dumps({'type': 'text', 'content': combined}, ensure_ascii=False)}\n\n"

                # ── 工具返回结果 ──
                elif isinstance(latest, ToolMessage):
                    result_content = latest.content
                    if isinstance(result_content, str):
                        preview = result_content[:300]
                    else:
                        preview = str(result_content)[:300]
                    event = {
                        "type": "tool_result",
                        "tool_name": getattr(latest, "name", "unknown"),
                        "content": preview,
                    }
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    _add_tool_log(sid, event)

            # 存储完整回复
            full_text = "".join(full_text_parts)
            if full_text.strip():
                _add_message(sid, "assistant", full_text)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/chat/history", methods=["POST"])
def chat_history():
    """返回当前会话的历史消息"""
    sid = session.get("sid")
    if not sid:
        return jsonify({"messages": []})
    return jsonify({"messages": _get_messages(sid)})


@app.route("/api/chat/clear", methods=["POST"])
def chat_clear():
    """清空当前会话的消息和工具日志"""
    sid = session.get("sid")
    if sid and sid in session_store:
        with _store_lock:
            session_store[sid] = _make_session()
    return jsonify({"status": "ok"})


@app.route("/api/tool-logs")
def tool_logs():
    """返回当前会话的工具调用日志"""
    sid = session.get("sid")
    if not sid:
        return jsonify({"logs": []})
    return jsonify({"logs": _get_tool_logs(sid)})


# ── 文件上传 ───────────────────────────────────────────────

def _check_md5_in_store(md5_hex: str) -> bool:
    """检查 MD5 是否已在向量库记录中（去重）"""
    md5_path = get_abs_path(chroma_conf["md5_hex_store"])
    if not os.path.exists(md5_path):
        return False
    with open(md5_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == md5_hex:
                return True
    return False


def _save_md5_to_store(md5_hex: str) -> None:
    """将 MD5 写入记录文件"""
    md5_path = get_abs_path(chroma_conf["md5_hex_store"])
    with open(md5_path, "a", encoding="utf-8") as f:
        f.write(md5_hex + "\n")


def _get_file_documents(filepath: str) -> list:
    """根据文件后缀调用对应的加载器"""
    if filepath.endswith(".txt"):
        return txt_loader(filepath)
    if filepath.endswith(".pdf"):
        return pdf_loader(filepath)
    return []


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """
    上传文件并存入向量知识库。
    接收 multipart/form-data，字段名 "file"。
    """
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "未找到上传文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"status": "error", "message": "文件名为空"}), 400

    # 1. 校验扩展名
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "status": "error",
            "message": f"不支持的文件类型 .{ext}，仅允许 {', '.join(ALLOWED_EXTENSIONS)}",
        }), 400

    # 2. 保存到 data/ 目录
    data_dir = get_abs_path(chroma_conf["data_path"])
    os.makedirs(data_dir, exist_ok=True)
    save_path = os.path.join(data_dir, file.filename)
    file.save(save_path)
    logger.info(f"[文件上传] 文件已保存: {save_path}")

    # 3. 计算 MD5
    md5_hex = get_file_md5_hex(save_path)
    if not md5_hex:
        return jsonify({"status": "error", "message": "计算文件 MD5 失败"}), 500

    # 4. 去重检查
    if _check_md5_in_store(md5_hex):
        logger.info(f"[文件上传] {file.filename} 已存在于向量库中，跳过")
        return jsonify({
            "status": "duplicate",
            "message": "该文件已存在于知识库中，无需重复上传",
            "filename": file.filename,
            "md5": md5_hex,
        })

    # 5. 加载文档
    try:
        documents = _get_file_documents(save_path)
    except Exception as e:
        logger.error(f"[文件上传] 解析文件失败: {str(e)}")
        return jsonify({"status": "error", "message": f"文件解析失败: {str(e)}"}), 500

    if not documents:
        return jsonify({"status": "error", "message": "文件中未提取到有效文本内容"}), 400

    # 6. 文本分片
    split_docs = rag.vector_store.spliter.split_documents(documents)
    if not split_docs:
        return jsonify({"status": "error", "message": "文本分片后无有效内容"}), 400

    # 7. 存入向量库
    try:
        rag.vector_store.vector_store.add_documents(split_docs)
    except Exception as e:
        logger.error(f"[文件上传] 向量库写入失败: {str(e)}")
        return jsonify({"status": "error", "message": f"向量库写入失败: {str(e)}"}), 500

    # 8. 记录 MD5
    _save_md5_to_store(md5_hex)
    logger.info(f"[文件上传] {file.filename} 成功入库，{len(split_docs)} 个分片")

    return jsonify({
        "status": "success",
        "message": f"文件 {file.filename} 上传成功，已生成 {len(split_docs)} 个知识片段",
        "filename": file.filename,
        "chunks": len(split_docs),
        "md5": md5_hex,
    })


@app.route("/api/files", methods=["GET"])
def list_files():
    """返回 data/ 目录下的文件列表及入库状态"""
    data_dir = get_abs_path(chroma_conf["data_path"])
    files = []

    if os.path.isdir(data_dir):
        allowed_types = tuple(chroma_conf.get("allow_knowledge_file_type", ["txt", "pdf"]))
        for fname in os.listdir(data_dir):
            if not fname.lower().endswith(allowed_types):
                continue
            fpath = os.path.join(data_dir, fname)
            if not os.path.isfile(fpath):
                continue
            fsize = os.path.getsize(fpath)
            md5_hex = get_file_md5_hex(fpath) or ""
            in_store = _check_md5_in_store(md5_hex) if md5_hex else False
            files.append({
                "name": fname,
                "size": fsize,
                "size_str": _format_size(fsize),
                "md5": md5_hex,
                "in_store": in_store,
            })

    # 按文件名排序
    files.sort(key=lambda f: f["name"].lower())
    return jsonify({"files": files})


def _format_size(size: int) -> str:
    """将字节数转为可读大小"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ── 启动入口 ───────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=True, use_reloader=False)
