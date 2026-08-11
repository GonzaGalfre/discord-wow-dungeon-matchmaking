const POLL_INTERVAL_MS = 10000;

const elements = {
    refreshBtn: document.getElementById("refreshBtn"),
    lastUpdated: document.getElementById("lastUpdated"),
    botStatus: document.getElementById("botStatus"),
    botUser: document.getElementById("botUser"),
    connectedGuilds: document.getElementById("connectedGuilds"),
    configuredGuilds: document.getElementById("configuredGuilds"),
    guildList: document.getElementById("guildList"),
    downloadLogsBtn: document.getElementById("downloadLogsBtn"),
    clearLogsBtn: document.getElementById("clearLogsBtn"),
    adminStatus: document.getElementById("adminStatus"),
};

function normalizeBasePath(rawValue) {
    const raw = String(rawValue ?? "").trim();
    if (!raw || raw === "/") return "";
    return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

const BASE_PATH = normalizeBasePath(
    document.querySelector('meta[name="dashboard-base-path"]')?.content || ""
);

function withBasePath(path) {
    return `${BASE_PATH}${path}`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

async function getJson(path) {
    const response = await fetch(withBasePath(path), { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function postJson(path, body) {
    const response = await fetch(withBasePath(path), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
}

function renderGuilds(guilds) {
    elements.configuredGuilds.textContent = String(guilds.length);
    if (!guilds.length) {
        elements.guildList.innerHTML = '<p class="state">No configured guilds yet.</p>';
        return;
    }

    elements.guildList.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Guild</th>
                    <th>Signup Channel</th>
                    <th>Signup Message</th>
                    <th>Admin Channel</th>
                    <th>Move Panel</th>
                </tr>
            </thead>
            <tbody>
                ${guilds.map((guild) => `
                    <tr>
                        <td>${escapeHtml(guild.guild_name)}</td>
                        <td>${escapeHtml(guild.signup_channel_id || "Not set")}</td>
                        <td>${escapeHtml(guild.signup_message_id || "Not set")}</td>
                        <td>${escapeHtml(guild.admin_channel_id || "Not set")}</td>
                        <td>${escapeHtml(guild.move_panel_message_id || "Not set")}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;
}

async function refresh() {
    const [status, guilds] = await Promise.all([
        getJson("/api/status"),
        getJson("/api/guilds"),
    ]);

    elements.botStatus.textContent = status.bot_ready ? "Ready" : "Starting";
    elements.botStatus.classList.toggle("ready", Boolean(status.bot_ready));
    elements.botUser.textContent = status.bot_user || "Unavailable";
    elements.connectedGuilds.textContent = String(status.connected_guild_count || 0);
    renderGuilds(guilds);
    elements.lastUpdated.textContent = `Last sync: ${new Date().toLocaleTimeString()}`;
}

elements.refreshBtn.addEventListener("click", () => {
    refresh().catch((error) => {
        elements.adminStatus.textContent = `Refresh failed: ${error.message}`;
    });
});

elements.downloadLogsBtn.addEventListener("click", () => {
    window.location.href = withBasePath("/api/admin/logs/download");
});

elements.clearLogsBtn.addEventListener("click", async () => {
    if (!window.confirm("Clear runtime logs?")) return;
    try {
        const result = await postJson("/api/admin/logs/clear", { confirm: true });
        elements.adminStatus.textContent = `Cleared ${result.removed_lines || 0} log lines.`;
    } catch (error) {
        elements.adminStatus.textContent = `Clear failed: ${error.message}`;
    }
});

refresh().catch((error) => {
    elements.adminStatus.textContent = `Initial load failed: ${error.message}`;
});
setInterval(() => refresh().catch(() => {}), POLL_INTERVAL_MS);
