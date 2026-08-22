/**
 * RAG 智能问答助手 — SSE 客户端
 * 处理流式对话、工具调用可视化、会话管理
 */
(function () {
    "use strict";

    /* ─── DOM 引用 ────────────────────────────── */
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const messagesEl = $("#messages");
    const chatContainer = $("#chat-container");
    const chatInput = $("#chat-input");
    const btnSend = $("#btn-send");
    const btnClear = $("#btn-clear");
    const btnTogglePanel = $("#btn-toggle-panel");
    const btnClosePanel = $("#btn-close-panel");
    const toolPanel = $("#tool-panel");
    const toolLogList = $("#tool-log-list");
    const toolCount = $("#tool-count");
    const typingIndicator = $("#typing-indicator");
    const welcomeEl = $(".welcome-message");

    /* ─── 状态 ────────────────────────────────── */
    const state = {
        isStreaming: false,
        currentAssistantBubble: null,   // 正在流式更新的气泡 DOM
        currentToolCards: new Map(),     // tool_name → {card, body} DOM 引用
        toolCallCount: 0,
    };

    /* ─── 初始化 ──────────────────────────────── */
    function init() {
        bindEvents();
        loadHistory();
    }

    function bindEvents() {
        // 发送按钮
        btnSend.addEventListener("click", () => sendMessage());

        // 输入框：Enter 发送，Shift+Enter 换行
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // 自动调整输入框高度
        chatInput.addEventListener("input", autoResizeInput);

        // 清空按钮
        btnClear.addEventListener("click", clearChat);

        // 工具面板切换
        btnTogglePanel.addEventListener("click", toggleToolPanel);
        btnClosePanel.addEventListener("click", () => {
            toolPanel.classList.add("collapsed");
        });
    }

    /* ─── 消息历史加载 ───────────────────────── */
    async function loadHistory() {
        try {
            const res = await fetch("/api/chat/history", { method: "POST" });
            const data = await res.json();
            if (data.messages && data.messages.length > 0) {
                removeWelcome();
                for (const msg of data.messages) {
                    appendMessage(msg.role, msg.content);
                }
            }
        } catch (err) {
            console.error("Load history error:", err);
        }
    }

    /* ─── 发送消息 ────────────────────────────── */
    async function sendMessage() {
        const query = chatInput.value.trim();
        if (!query || state.isStreaming) return;

        // 重置输入
        chatInput.value = "";
        autoResizeInput();
        removeWelcome();

        // 禁用发送
        state.isStreaming = true;
        disableInput(true);

        // 显示用户消息
        appendMessage("user", query);

        // 创建空的助手气泡（流式填充）
        state.currentAssistantBubble = appendMessage("assistant", "");
        showTyping(true);

        // 重置工具卡片追踪
        state.currentToolCards.clear();

        try {
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // 解析 SSE 帧: "data: {...}\n\n"
                const parts = buffer.split("\n\n");
                buffer = parts.pop(); // 保留不完整的最后一段

                for (const part of parts) {
                    const lines = part.split("\n");
                    for (const line of lines) {
                        if (line.startsWith("data: ")) {
                            try {
                                const event = JSON.parse(line.slice(6));
                                handleSSEEvent(event);
                            } catch (e) {
                                // 忽略解析失败的行
                            }
                        }
                    }
                }
            }
        } catch (err) {
            handleSSEEvent({ type: "error", message: err.message });
        }

        // 流结束：切换状态
        showTyping(false);
        disableInput(false);
        state.isStreaming = false;

        // 聚焦输入框
        chatInput.focus();
    }

    /* ─── SSE 事件分发 ────────────────────────── */
    function handleSSEEvent(event) {
        switch (event.type) {
            case "text":
                handleTextEvent(event.content);
                break;

            case "tool_call":
                handleToolCallEvent(event.tool_name, event.args);
                break;

            case "tool_result":
                handleToolResultEvent(event.tool_name, event.content);
                break;

            case "done":
                // 流正常结束
                break;

            case "error":
                handleErrorEvent(event.message);
                break;
        }
    }

    /* ─── 文本事件：替换模式 ──────────────────── */
    function handleTextEvent(content) {
        if (!state.currentAssistantBubble) return;

        const bubble = state.currentAssistantBubble.querySelector(".message-bubble");
        if (bubble) {
            bubble.textContent = content;
        }
        scrollToBottom();
    }

    /* ─── 工具调用事件 ────────────────────────── */
    function handleToolCallEvent(toolName, args) {
        // 在聊天中插入工具调用卡片
        const card = createToolCallCard(toolName, args);
        messagesEl.appendChild(card);

        // 侧边面板日志
        addToolLogEntry(toolName, "call", args);
        updateToolBadge();

        state.currentToolCards.set(toolName, {
            card,
            body: card.querySelector(".tool-call-body"),
            status: card.querySelector(".tool-status"),
        });

        scrollToBottom();
    }

    /* ─── 工具结果事件 ────────────────────────── */
    function handleToolResultEvent(toolName, content) {
        // 更新对话中的卡片
        const entry = state.currentToolCards.get(toolName);
        if (entry) {
            // 更新状态
            entry.status.innerHTML = "✓ 完成";
            entry.status.classList.remove("running");
            entry.status.classList.add("done");

            // 填充结果
            const resultEl = entry.body.querySelector(".tool-result code");
            if (resultEl) {
                resultEl.textContent = content;
            }
        }

        // 侧边面板日志
        addToolLogEntry(toolName, "result", content);
    }

    /* ─── 错误事件 ────────────────────────────── */
    function handleErrorEvent(message) {
        if (state.currentAssistantBubble) {
            const bubble = state.currentAssistantBubble.querySelector(".message-bubble");
            if (bubble) {
                bubble.innerHTML =
                    `<span style="color: var(--danger);">⚠ 出错了：${escapeHtml(message)}</span>`;
            }
        }
    }

    /* ─── DOM 构建：消息气泡 ──────────────────── */
    function appendMessage(role, content) {
        const wrapper = document.createElement("div");
        wrapper.className = `message ${role}`;

        const roleLabel = document.createElement("div");
        roleLabel.className = "message-role";
        roleLabel.textContent = role === "user" ? "你" : "助手";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = content;

        wrapper.appendChild(roleLabel);
        wrapper.appendChild(bubble);
        messagesEl.appendChild(wrapper);

        scrollToBottom();
        return wrapper;
    }

    /* ─── DOM 构建：工具调用卡片 ──────────────── */
    function createToolCallCard(toolName, args) {
        const card = document.createElement("div");
        card.className = "tool-call-card";
        card.setAttribute("data-tool", toolName);

        const header = document.createElement("div");
        header.className = "tool-call-header";
        header.innerHTML = `
            <span class="tool-icon">🔧</span>
            <span class="tool-name">${escapeHtml(toolName)}</span>
            <span class="tool-status running">
                <span class="tool-spinner"></span> 执行中…
            </span>
        `;

        const body = document.createElement("div");
        body.className = "tool-call-body";
        body.innerHTML = `
            <div class="tool-args">
                <strong>参数：</strong>
                <code>${escapeHtml(JSON.stringify(args, null, 2))}</code>
            </div>
            <div class="tool-result">
                <strong>结果：</strong>
                <code>等待返回…</code>
            </div>
        `;

        // 点击展开/折叠
        header.addEventListener("click", () => {
            body.classList.toggle("expanded");
        });

        card.appendChild(header);
        card.appendChild(body);
        return card;
    }

    /* ─── 侧边面板：工具日志 ──────────────────── */
    function addToolLogEntry(toolName, kind, detail) {
        // 清空空状态
        const empty = toolLogList.querySelector(".panel-empty");
        if (empty) empty.remove();

        const entry = document.createElement("div");
        entry.className = "tool-log-entry";

        const badgeClass = kind === "call" ? "call" : "result";
        const badgeText = kind === "call" ? "调用" : "返回";

        entry.innerHTML = `
            <div class="tool-log-name">
                ${escapeHtml(toolName)}
                <span class="tool-log-badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="tool-log-detail">${escapeHtml(
                typeof detail === "string" ? detail : JSON.stringify(detail)
            )}</div>
        `;

        toolLogList.appendChild(entry);
    }

    function updateToolBadge() {
        state.toolCallCount++;
        toolCount.textContent = state.toolCallCount;
        toolCount.classList.remove("hidden");
    }

    function toggleToolPanel() {
        toolPanel.classList.toggle("collapsed");
        state.toolCallCount = 0;
        toolCount.classList.add("hidden");
    }

    /* ─── 清空对话 ────────────────────────────── */
    async function clearChat() {
        if (state.isStreaming) return;

        try {
            await fetch("/api/chat/clear", { method: "POST" });
        } catch (err) {
            console.error("Clear error:", err);
        }

        // 清空 DOM
        messagesEl.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">💬</div>
                <h2>你好，有什么可以帮你的？</h2>
                <p>我可以检索知识库、查询天气、分析日志，试试问我吧</p>
            </div>
        `;
        toolLogList.innerHTML = '<p class="panel-empty">暂无工具调用记录</p>';
        state.currentAssistantBubble = null;
        state.currentToolCards.clear();
        state.toolCallCount = 0;
        toolCount.classList.add("hidden");
    }

    /* ─── 工具函数 ────────────────────────────── */
    function removeWelcome() {
        const w = messagesEl.querySelector(".welcome-message");
        if (w) w.remove();
    }

    function disableInput(disabled) {
        chatInput.disabled = disabled;
        btnSend.disabled = disabled;
        if (disabled) {
            btnSend.innerHTML = '<span class="typing-dot" style="width:4px;height:4px;background:#fff;"></span>';
        } else {
            btnSend.innerHTML = '<span class="send-icon">▶</span>';
        }
    }

    function showTyping(show) {
        typingIndicator.classList.toggle("hidden", !show);
    }

    function autoResizeInput() {
        chatInput.style.height = "auto";
        chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + "px";
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        });
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    /* ─── 启动 ────────────────────────────────── */
    document.addEventListener("DOMContentLoaded", init);
})();
