/**
 * RAG 智能问答助手 — 文件上传 & 页面导航
 */
(function () {
    "use strict";

    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    /* ─── DOM 引用 ────────────────────────────── */
    const sidebar = $("#sidebar");
    const navItems = $$(".nav-item");
    const pages = $$(".page");
    const btnMenuToggle = $("#btn-menu-toggle");

    // Upload page
    const dropzone = $("#upload-dropzone");
    const fileInput = $("#file-input");
    const btnSelectFile = $("#btn-select-file");
    const uploadStatus = $("#upload-status");
    const fileListContainer = $("#file-list-container");
    const btnRefreshFiles = $("#btn-refresh-files");

    /* ─── 页面导航 ────────────────────────────── */
    function switchPage(pageName) {
        // 更新导航 active 状态
        navItems.forEach((item) => {
            item.classList.toggle("active", item.dataset.page === pageName);
        });

        // 切换页面显示
        pages.forEach((page) => {
            page.classList.toggle("active", page.id === `page-${pageName}`);
        });

        // 切换到上传页时加载文件列表
        if (pageName === "upload") {
            loadFileList();
        }

        // 移动端关闭侧边栏
        sidebar.classList.remove("open");
    }

    navItems.forEach((item) => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            switchPage(item.dataset.page);
        });
    });

    /* ─── 移动端菜单 ───────────────────────────── */
    if (btnMenuToggle) {
        btnMenuToggle.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });
    }

    // 点击内容区关闭移动端侧边栏
    $("#content")?.addEventListener("click", () => {
        if (window.innerWidth <= 768) {
            sidebar.classList.remove("open");
        }
    });

    /* ─── 拖拽上传 ────────────────────────────── */
    if (dropzone) {
        dropzone.addEventListener("click", () => {
            fileInput.click();
        });

        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });

        dropzone.addEventListener("dragleave", () => {
            dropzone.classList.remove("dragover");
        });

        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
            const files = e.dataTransfer?.files;
            if (files && files.length > 0) {
                uploadFile(files[0]);
            }
        });
    }

    /* ─── 按钮选择上传 ────────────────────────── */
    if (btnSelectFile) {
        btnSelectFile.addEventListener("click", (e) => {
            e.stopPropagation();
            fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const file = fileInput.files?.[0];
            if (file) {
                uploadFile(file);
                fileInput.value = "";
            }
        });
    }

    /* ─── 文件上传 ────────────────────────────── */
    async function uploadFile(file) {
        // 前端校验扩展名
        const ext = file.name.split(".").pop()?.toLowerCase();
        if (!["txt", "pdf"].includes(ext)) {
            showStatus("error", `不支持的文件类型 .${ext}，仅允许 txt、pdf 格式`);
            return;
        }

        showStatus("uploading", `正在上传并解析 ${file.name}…`);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/upload", {
                method: "POST",
                body: formData,
            });
            const data = await res.json();

            if (data.status === "success") {
                showStatus("success", `✅ ${data.message}`);
            } else if (data.status === "duplicate") {
                showStatus("duplicate", `⚠️ ${data.message}`);
            } else {
                showStatus("error", `❌ ${data.message}`);
            }
        } catch (err) {
            showStatus("error", `❌ 上传失败: ${err.message}`);
        }

        // 刷新文件列表
        loadFileList();
    }

    /* ─── 状态提示 ────────────────────────────── */
    function showStatus(type, message) {
        if (!uploadStatus) return;
        uploadStatus.className = type;
        uploadStatus.textContent = message;
        uploadStatus.classList.remove("hidden");

        // 成功/重复 提示 5 秒后自动消失
        if (type === "success" || type === "duplicate") {
            setTimeout(() => {
                uploadStatus.classList.add("hidden");
            }, 5000);
        }
    }

    /* ─── 加载文件列表 ────────────────────────── */
    async function loadFileList() {
        if (!fileListContainer) return;
        fileListContainer.innerHTML =
            '<p class="panel-empty">加载中…</p>';

        try {
            const res = await fetch("/api/files");
            const data = await res.json();
            const files = data.files || [];

            if (files.length === 0) {
                fileListContainer.innerHTML =
                    '<p class="panel-empty">暂无已上传文件</p>';
                return;
            }

            let html = `
                <table class="file-table">
                    <thead>
                        <tr>
                            <th>文件名</th>
                            <th>大小</th>
                            <th>状态</th>
                            <th>MD5</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            for (const f of files) {
                html += `
                    <tr>
                        <td class="file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</td>
                        <td>${escapeHtml(f.size_str)}</td>
                        <td>
                            <span class="status-badge ${f.in_store ? 'stored' : 'pending'}">
                                ${f.in_store ? '已入库' : '未入库'}
                            </span>
                        </td>
                        <td class="file-md5" title="${escapeHtml(f.md5)}">${escapeHtml(f.md5)}</td>
                    </tr>
                `;
            }

            html += "</tbody></table>";
            fileListContainer.innerHTML = html;
        } catch (err) {
            fileListContainer.innerHTML =
                '<p class="panel-empty" style="color: var(--danger);">加载失败，请重试</p>';
        }
    }

    /* ─── 刷新按钮 ────────────────────────────── */
    if (btnRefreshFiles) {
        btnRefreshFiles.addEventListener("click", loadFileList);
    }

    /* ─── 工具函数 ────────────────────────────── */
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
