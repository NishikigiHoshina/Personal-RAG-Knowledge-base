/**
 * Wiki 知识库 — 实体浏览 + 关系互链跳转 + 构建
 */
(function () {
    "use strict";

    const $ = (sel) => document.querySelector(sel);

    const navItems = document.querySelectorAll(".nav-item");
    const wikiListContainer = $("#wiki-list-container");
    const wikiListSection = $("#wiki-list-section");
    const wikiDetailContainer = $("#wiki-detail-container");
    const wikiCount = $("#wiki-count");
    const btnBuild = $("#btn-wiki-build");
    const btnRefresh = $("#btn-wiki-refresh");

    /* ─── 切换到 wiki 页时加载列表 ─────────────── */
    navItems.forEach((item) => {
        item.addEventListener("click", () => {
            if (item.dataset.page === "wiki") {
                showList();
                loadWikiList();
            }
        });
    });

    /* ─── 列表 ────────────────────────────────── */
    async function loadWikiList() {
        if (!wikiListContainer) return;
        wikiListContainer.innerHTML = '<p class="panel-empty">加载中…</p>';
        try {
            const res = await fetch("/api/wiki");
            const data = await res.json();
            const pages = data.pages || [];
            if (wikiCount) wikiCount.textContent = `${pages.length} ENTITIES`;

            if (pages.length === 0) {
                wikiListContainer.innerHTML =
                    '<p class="panel-empty">暂无实体，点击右上角 BUILD 构建</p>';
                return;
            }

            let html = `
                <table class="file-table">
                    <thead><tr><th>实体</th><th>类型</th><th>关系数</th><th>来源</th></tr></thead>
                    <tbody>`;
            for (const p of pages) {
                const sources = (p.sources || []).join(", ") || "-";
                html += `<tr class="wiki-row" data-name="${escapeHtml(p.name)}">
                    <td class="file-name">${escapeHtml(p.name)}</td>
                    <td>${escapeHtml(p.type || "-")}</td>
                    <td>${p.rel_count}</td>
                    <td>${escapeHtml(sources)}</td>
                </tr>`;
            }
            html += "</tbody></table>";
            wikiListContainer.innerHTML = html;

            document.querySelectorAll(".wiki-row").forEach((row) => {
                row.addEventListener("click", () => showDetail(row.dataset.name));
            });
        } catch (err) {
            wikiListContainer.innerHTML =
                '<p class="panel-empty" style="color:var(--danger);">加载失败，请重试</p>';
        }
    }

    /* ─── 详情 ────────────────────────────────── */
    async function showDetail(name) {
        if (!wikiDetailContainer) return;
        wikiDetailContainer.innerHTML = '<p class="panel-empty">加载中…</p>';
        wikiDetailContainer.classList.remove("hidden");
        if (wikiListSection) wikiListSection.classList.add("hidden");

        try {
            const res = await fetch(`/api/wiki/${encodeURIComponent(name)}`);
            const data = await res.json();
            const p = data.page;
            if (!p) {
                wikiDetailContainer.innerHTML =
                    '<p class="panel-empty">未找到该实体</p>';
                return;
            }

            let relsHtml = "";
            for (const r of (p.relationships || [])) {
                relsHtml += `<span class="wiki-rel" data-name="${escapeHtml(r.target)}">${escapeHtml(r.target)} <em>${escapeHtml(r.desc || "")}</em></span>`;
            }
            const sources = (p.sources || [])
                .map((s) => escapeHtml(s.file || ""))
                .join("、") || "-";

            wikiDetailContainer.innerHTML = `
                <button class="btn-secondary" id="btn-wiki-back">◀ 返回</button>
                <div class="wiki-detail">
                    <div class="wiki-detail-head">
                        <h2>${escapeHtml(p.name)}</h2>
                        <span class="status-badge stored">${escapeHtml(p.type || "未分类")}</span>
                    </div>
                    <div class="wiki-detail-body">${escapeHtml(p.description || "")}</div>
                    <div class="wiki-section">
                        <h3>◈ 关联关系</h3>
                        <div class="wiki-rels">${relsHtml || '<span class="panel-empty">无</span>'}</div>
                    </div>
                    <div class="wiki-section">
                        <h3>◈ 来源引用</h3>
                        <p class="wiki-sources">${sources}</p>
                    </div>
                </div>`;

            $("#btn-wiki-back").addEventListener("click", showList);
            document.querySelectorAll(".wiki-rel").forEach((el) => {
                el.addEventListener("click", () => showDetail(el.dataset.name));
            });
        } catch (err) {
            wikiDetailContainer.innerHTML =
                '<p class="panel-empty" style="color:var(--danger);">加载失败</p>';
        }
    }

    function showList() {
        if (wikiDetailContainer) wikiDetailContainer.classList.add("hidden");
        if (wikiListSection) wikiListSection.classList.remove("hidden");
    }

    /* ─── 构建 ────────────────────────────────── */
    if (btnBuild) {
        btnBuild.addEventListener("click", async () => {
            btnBuild.disabled = true;
            btnBuild.textContent = "构建中…";
            try {
                const res = await fetch("/api/wiki/build", { method: "POST" });
                const data = await res.json();
                alert(data.message || "构建完成");
            } catch (err) {
                alert("构建失败: " + err.message);
            }
            btnBuild.disabled = false;
            btnBuild.textContent = "构建 BUILD";
            loadWikiList();
        });
    }

    if (btnRefresh) {
        btnRefresh.addEventListener("click", loadWikiList);
    }

    /* ─── 工具 ────────────────────────────────── */
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
