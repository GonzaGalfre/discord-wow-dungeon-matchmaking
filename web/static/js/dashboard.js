const POLL_INTERVAL_MS = 10000;

const elements = {
    refreshBtn: document.getElementById("refreshBtn"),
    guildFilter: document.getElementById("guildFilter"),
    lastUpdated: document.getElementById("lastUpdated"),
    metricQueueTotal: document.getElementById("metricQueueTotal"),
    metricGroupsTotal: document.getElementById("metricGroupsTotal"),
    metricWeeklyKeys: document.getElementById("metricWeeklyKeys"),
    metricMaxKey: document.getElementById("metricMaxKey"),
    queueTotal: document.getElementById("queueTotal"),
    groupsTotal: document.getElementById("groupsTotal"),
    leaderboardTotal: document.getElementById("leaderboardTotal"),
    queueContent: document.getElementById("queueContent"),
    groupsContent: document.getElementById("groupsContent"),
    leaderboardContent: document.getElementById("leaderboardContent"),
    completedContent: document.getElementById("completedContent"),
    clearQueueBtn: document.getElementById("clearQueueBtn"),
    devCleanupBtn: document.getElementById("devCleanupBtn"),
    clearHistoryBtn: document.getElementById("clearHistoryBtn"),
    clearLogsBtn: document.getElementById("clearLogsBtn"),
    downloadLogsBtn: document.getElementById("downloadLogsBtn"),
    addFakePlayerForm: document.getElementById("addFakePlayerForm"),
    addFakeGroupForm: document.getElementById("addFakeGroupForm"),
    adminActionStatus: document.getElementById("adminActionStatus"),
};

const state = {
    // Keep guild IDs as strings to preserve Discord snowflake precision.
    selectedGuildId: null,
    guildsInitialized: false,
};

function normalizeBasePath(rawValue) {
    const raw = String(rawValue ?? "").trim();
    if (!raw || raw === "/") {
        return "";
    }
    return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

function detectBasePath() {
    const meta = document.querySelector('meta[name="dashboard-base-path"]');
    if (meta?.content) {
        return normalizeBasePath(meta.content);
    }
    const path = window.location.pathname || "/";
    if (path === "/") {
        return "";
    }
    return normalizeBasePath(path);
}

const BASE_PATH = detectBasePath();

function withBasePath(path) {
    return `${BASE_PATH}${path}`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

function formatTime(date) {
    return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    }).format(date);
}

async function getJson(path) {
    const response = await fetch(path, { credentials: "same-origin" });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
}

async function postJson(path, body) {
    const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    let payload = {};
    try {
        payload = await response.json();
    } catch (_error) {
        payload = {};
    }

    if (!response.ok) {
        const detail = payload?.detail || `HTTP ${response.status}`;
        throw new Error(String(detail));
    }

    return payload;
}

function roleLabel(role, roles) {
    if (Array.isArray(roles) && roles.length > 0) {
        return roles.join(" > ");
    }
    if (role === "tank") return "tank";
    if (role === "healer") return "healer";
    if (role === "dps") return "dps";
    return "group";
}

function roleClass(role, roles) {
    if (Array.isArray(roles) && roles.length > 1) return "role-group";
    const primaryRole = Array.isArray(roles) && roles.length > 0 ? roles[0] : role;
    if (primaryRole === "tank") return "role-tank";
    if (primaryRole === "healer") return "role-healer";
    if (primaryRole === "dps") return "role-dps";
    return "role-group";
}

function rolePill(role, roles) {
    const label = roleLabel(role, roles);
    return `<span class="role-pill ${roleClass(role, roles)}">${label}</span>`;
}

function keyPreferenceLabel(entry) {
    if (entry.key_bracket) {
        return String(entry.key_bracket);
    }
    return `+${entry.key_min}-${entry.key_max}`;
}

function keystoneLabel(entry) {
    if (!entry.has_keystone) {
        return "No key";
    }
    if (entry.keystone_level) {
        return `+${entry.keystone_level}`;
    }
    return "Has key";
}

function updateMetric(target, value) {
    target.textContent = value;
    target.classList.remove("value-fade");
    void target.offsetWidth;
    target.classList.add("value-fade");
}

function renderQueue(data) {
    const guilds = data.guilds || [];
    const totalInQueue = data.total_players_in_queue ?? data.total_in_queue ?? 0;
    elements.queueTotal.textContent = `${totalInQueue} players`;
    updateMetric(elements.metricQueueTotal, `${totalInQueue}`);

    if (!guilds.length) {
        elements.queueContent.innerHTML = '<p class="state-message">No guild data yet.</p>';
        return;
    }

    elements.queueContent.innerHTML = guilds
        .map((guild) => {
            const entries = guild.entries || [];
            const rows = entries.length
                ? entries
                    .map((entry) => `
                        <tr>
                            <td>${escapeHtml(entry.username)}</td>
                            <td>${rolePill(entry.role, entry.roles)}</td>
                            <td>${keyPreferenceLabel(entry)}</td>
                            <td>${keystoneLabel(entry)}</td>
                        </tr>
                    `)
                    .join("")
                : '<tr><td colspan="4" class="state-message">Queue empty.</td></tr>';

            return `
                <article class="queue-guild">
                    <header class="queue-guild-head">
                        <p class="queue-guild-name">${escapeHtml(guild.guild_name)}</p>
                        <span class="pill pill-neutral">${guild.player_count ?? guild.count ?? 0} players in queue</span>
                    </header>
                    <div class="queue-table-wrap">
                        <table class="queue-table">
                            <thead>
                                <tr>
                                    <th>Player</th>
                                    <th>Role</th>
                                    <th>Range</th>
                                    <th>Key</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                </article>
            `;
        })
        .join("");
}

function renderGroups(queueData) {
    const allGroups = [];
    (queueData.guilds || []).forEach((guild) => {
        const pendingBySignature = new Set();
        (guild.pending_confirmations || []).forEach((group) => {
            const signature = (group.user_ids || [])
                .map((value) => String(value))
                .sort()
                .join(",");
            if (signature) {
                pendingBySignature.add(signature);
            }
            allGroups.push({
                guildName: guild.guild_name,
                totalPlayers: group.total_players ?? 0,
                entries: group.entries || [],
                phase: "awaiting_confirmation",
                confirmationTotal: group.confirmation_targets_total ?? 0,
                confirmationConfirmed: group.confirmation_targets_confirmed ?? 0,
                fallbackCount: group.channel_fallback_count ?? 0,
            });
        });

        (guild.active_matches || []).forEach((group) => {
            const signature = (group.entries || [])
                .map((entry) => String(entry.user_id ?? ""))
                .filter((value) => value !== "")
                .sort()
                .join(",");
            if (signature && pendingBySignature.has(signature)) {
                return; // Already represented as a pending-confirmation group
            }
            allGroups.push({
                guildName: guild.guild_name,
                totalPlayers: group.total_players ?? 0,
                entries: group.entries || [],
                phase: "forming",
                confirmationTotal: 0,
                confirmationConfirmed: 0,
                fallbackCount: 0,
            });
        });
    });

    elements.groupsTotal.textContent = `${allGroups.length} active`;
    updateMetric(elements.metricGroupsTotal, `${allGroups.length}`);

    if (!allGroups.length) {
        elements.groupsContent.innerHTML = '<p class="state-message">No active groups forming right now.</p>';
        return;
    }

    elements.groupsContent.innerHTML = `
        <div class="groups-grid">
            ${allGroups
                .map((group) => {
                    const fillPercent = Math.max(0, Math.min(100, (group.totalPlayers / 5) * 100));
                    const isPending = group.phase === "awaiting_confirmation";
                    const statusLabel = isPending
                        ? `Waiting confirmations ${group.confirmationConfirmed}/${group.confirmationTotal}`
                        : "Forming";
                    const fallbackNote = isPending && group.fallbackCount > 0
                        ? `<p class="group-subtext">${group.fallbackCount} confirming in channel (DM fallback)</p>`
                        : "";
                    return `
                        <article class="group-card">
                            <header class="group-head">
                                <p class="group-name">${escapeHtml(group.guildName)}</p>
                                <span class="pill">${group.totalPlayers}/5</span>
                            </header>
                            <p class="group-subtext">${escapeHtml(statusLabel)}</p>
                            ${fallbackNote}
                            <div class="group-progress">
                                <div class="group-progress-fill" style="width:${fillPercent}%"></div>
                            </div>
                            <ul class="member-list">
                                ${group.entries
                                    .map(
                                        (entry) => `
                                            <li>
                                                <span>${escapeHtml(entry.username)}</span>
                                                ${rolePill(entry.role, entry.roles)}
                                            </li>
                                        `
                                    )
                                    .join("")}
                            </ul>
                        </article>
                    `;
                })
                .join("")}
        </div>
    `;
}

function renderLeaderboard(data) {
    const players = data.player_stats || data.top_players || [];
    elements.leaderboardTotal.textContent = `Total keys ${data.total_keys ?? 0}`;

    if (!players.length) {
        elements.leaderboardContent.innerHTML = '<p class="state-message">No leaderboard data yet.</p>';
        return;
    }

    elements.leaderboardContent.innerHTML = `
        <ol class="leaderboard-list">
            ${players
                .slice(0, 10)
                .map(
                    (player, index) => `
                        <li class="leaderboard-item">
                            <span class="leaderboard-rank">#${index + 1}</span>
                            <span>${escapeHtml(player.username)}</span>
                            <span class="leaderboard-keys">${player.key_count} keys</span>
                        </li>
                    `
                )
                .join("")}
        </ol>
    `;
}

function renderCompleted(data) {
    const totalKeys = data.total_keys ?? 0;
    const avgLevel = data.avg_key_level ?? 0;
    const maxLevel = data.max_key_level ?? 0;

    updateMetric(elements.metricWeeklyKeys, `${totalKeys}`);
    updateMetric(elements.metricMaxKey, `${maxLevel}`);

    elements.completedContent.innerHTML = `
        <div class="completed-grid">
            <article class="completed-stat">
                <p class="completed-stat-label">Total Keys</p>
                <p class="completed-stat-value">${totalKeys}</p>
            </article>
            <article class="completed-stat">
                <p class="completed-stat-label">Average Level</p>
                <p class="completed-stat-value">${avgLevel}</p>
            </article>
            <article class="completed-stat">
                <p class="completed-stat-label">Max Level</p>
                <p class="completed-stat-value">${maxLevel}</p>
            </article>
        </div>
    `;
}

function renderError(error) {
    const message = `<div class="status-error">Failed to load dashboard data: ${escapeHtml(error.message)}</div>`;
    elements.queueContent.innerHTML = message;
    elements.groupsContent.innerHTML = message;
    elements.leaderboardContent.innerHTML = message;
    elements.completedContent.innerHTML = message;
}

function setAdminStatus(message, isError = false) {
    if (!elements.adminActionStatus) {
        return;
    }
    elements.adminActionStatus.textContent = message;
    elements.adminActionStatus.classList.toggle("is-error", Boolean(isError));
}

function normalizeQueuePayload(payload) {
    if (Array.isArray(payload.guilds)) {
        return payload;
    }

    const count = payload.player_count ?? payload.count ?? 0;
    return {
        total_in_queue: count,
        guilds: [payload],
    };
}

function buildStatsPath(basePath) {
    const params = new URLSearchParams({ period: "weekly" });
    if (state.selectedGuildId !== null) {
        params.set("guild_id", String(state.selectedGuildId));
    }
    return `${basePath}?${params.toString()}`;
}

function renderGuildOptions(guilds) {
    const previous = state.selectedGuildId === null ? "" : String(state.selectedGuildId);
    const options = ['<option value="">All guilds</option>'];
    guilds.forEach((guild) => {
        options.push(`<option value="${guild.guild_id}">${escapeHtml(guild.guild_name)}</option>`);
    });
    elements.guildFilter.innerHTML = options.join("");
    elements.guildFilter.value = previous;
}

async function initializeGuildFilter() {
    if (state.guildsInitialized) {
        return;
    }

    try {
        const guilds = await getJson(withBasePath("/api/guilds"));
        renderGuildOptions(guilds || []);
    } catch (_error) {
        elements.guildFilter.innerHTML = '<option value="">All guilds</option>';
    } finally {
        state.guildsInitialized = true;
    }
}

async function loadDashboard() {
    elements.refreshBtn.disabled = true;
    elements.guildFilter.disabled = true;
    elements.refreshBtn.textContent = "Syncing...";

    try {
        await initializeGuildFilter();
        const queuePath = state.selectedGuildId === null
            ? withBasePath("/api/queue")
            : withBasePath(`/api/queue/${state.selectedGuildId}`);
        const [queue, leaderboard, completed] = await Promise.all([
            getJson(queuePath),
            getJson(buildStatsPath(withBasePath("/api/leaderboard"))),
            getJson(buildStatsPath(withBasePath("/api/completed"))),
        ]);
        const normalizedQueue = normalizeQueuePayload(queue);
        renderQueue(normalizedQueue);
        renderGroups(normalizedQueue);
        renderLeaderboard(leaderboard);
        renderCompleted(completed);
        elements.lastUpdated.textContent = `Last sync: ${formatTime(new Date())}`;
    } catch (error) {
        renderError(error);
    } finally {
        elements.refreshBtn.disabled = false;
        elements.guildFilter.disabled = false;
        elements.refreshBtn.textContent = "Refresh now";
    }
}

function selectedGuildOrThrow() {
    if (state.selectedGuildId === null) {
        throw new Error("Select a guild first for this action.");
    }
    return state.selectedGuildId;
}

async function withAction(button, action) {
    if (!button) {
        return;
    }
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Working...";
    try {
        await action();
    } finally {
        button.disabled = false;
        button.textContent = oldText;
    }
}

async function handleClearQueue() {
    const payload = state.selectedGuildId === null
        ? {}
        : { guild_id: state.selectedGuildId };
    const result = await postJson(withBasePath("/api/admin/queue/clear"), payload);
    if (result.scope === "all") {
        setAdminStatus(`Queue cleared for all guilds. Removed ${result.removed_entries} entries.`);
    } else {
        setAdminStatus(`Queue cleared for guild ${result.guild_id}. Removed ${result.removed_entries} entries.`);
    }
    await loadDashboard();
}

async function handleDevCleanup() {
    const payload = state.selectedGuildId === null
        ? {}
        : { guild_id: state.selectedGuildId };
    const result = await postJson(withBasePath("/api/admin/dev/cleanup"), payload);
    if (result.scope === "all") {
        setAdminStatus(`Dev cleanup completed. Removed ${result.removed_entries} fake entries across ${result.touched_guilds} guild(s).`);
    } else {
        setAdminStatus(`Dev cleanup completed for guild ${result.guild_id}. Removed ${result.removed_entries} fake entries.`);
    }
    await loadDashboard();
}

async function handleClearHistory() {
    const result = await postJson(withBasePath("/api/admin/database/clear-history"), { confirm: true });
    const deleted = result.deleted || {};
    setAdminStatus(
        `History cleared. Completed keys: ${deleted.completed_keys ?? 0}, `
        + `participants: ${deleted.key_participants ?? 0}. `
        + "Guild settings and queue entries were preserved."
    );
    await loadDashboard();
}

async function handleClearLogs() {
    const result = await postJson(withBasePath("/api/admin/logs/clear"), { confirm: true });
    setAdminStatus(
        `Runtime logs cleared. Removed ${result.removed_lines ?? 0} lines `
        + `(${result.removed_bytes ?? 0} bytes).`
    );
}

function handleDownloadLogs() {
    window.location.href = withBasePath("/api/admin/logs/download");
    setAdminStatus("Downloading runtime logs (events.jsonl)...");
}

async function handleAddFakePlayer(event) {
    event.preventDefault();
    const guildId = selectedGuildOrThrow();
    const formData = new FormData(elements.addFakePlayerForm);
    const payload = {
        guild_id: guildId,
        username: String(formData.get("name") ?? "").trim(),
        role: String(formData.get("role") ?? "dps"),
        roles: [String(formData.get("role") ?? "dps")],
        key_min: Number(formData.get("key_min")),
        key_max: Number(formData.get("key_max")),
        has_keystone: String(formData.get("has_keystone") ?? "false") === "true",
        keystone_level: Number(formData.get("keystone_level")),
        force_match: String(formData.get("force_match") ?? "true") === "true",
    };
    if (!payload.has_keystone) {
        payload.keystone_level = null;
    }
    const result = await postJson(withBasePath("/api/admin/dev/add-fake-player"), payload);
    const forceMatch = result.force_match || {};
    if (forceMatch.forced) {
        const suffix = forceMatch.matched
            ? ` Forced match formed with ${forceMatch.user_count} players.`
            : forceMatch.error
                ? ` Force match failed: ${forceMatch.error}`
                : " Force match ran with no compatible group.";
        setAdminStatus(`Fake player added (ID ${result.fake_user_id}) to guild ${result.guild_id}.${suffix}`);
    } else {
        setAdminStatus(`Fake player added (ID ${result.fake_user_id}) to guild ${result.guild_id}.`);
    }
    await loadDashboard();
}

async function handleAddFakeGroup(event) {
    event.preventDefault();
    const guildId = selectedGuildOrThrow();
    const formData = new FormData(elements.addFakeGroupForm);
    const payload = {
        guild_id: guildId,
        leader_name: String(formData.get("leader_name") ?? "").trim(),
        tanks: Number(formData.get("tanks")),
        healers: Number(formData.get("healers")),
        dps: Number(formData.get("dps")),
        key_min: Number(formData.get("key_min")),
        key_max: Number(formData.get("key_max")),
    };
    const result = await postJson(withBasePath("/api/admin/dev/add-fake-group"), payload);
    setAdminStatus(
        `Fake group added (ID ${result.fake_user_id}, ${result.player_count} players) to guild ${result.guild_id}.`
    );
    await loadDashboard();
}

elements.guildFilter.addEventListener("change", () => {
    const rawValue = elements.guildFilter.value;
    state.selectedGuildId = rawValue === "" ? null : rawValue;
    loadDashboard();
});
elements.refreshBtn.addEventListener("click", loadDashboard);
elements.clearQueueBtn?.addEventListener("click", () =>
    withAction(elements.clearQueueBtn, async () => {
        try {
            await handleClearQueue();
        } catch (error) {
            setAdminStatus(`Queue clear failed: ${error.message}`, true);
        }
    })
);
elements.devCleanupBtn?.addEventListener("click", () =>
    withAction(elements.devCleanupBtn, async () => {
        try {
            await handleDevCleanup();
        } catch (error) {
            setAdminStatus(`Dev cleanup failed: ${error.message}`, true);
        }
    })
);
elements.clearHistoryBtn?.addEventListener("click", () =>
    withAction(elements.clearHistoryBtn, async () => {
        const confirmed = window.confirm(
            "This will delete leaderboard and key history data only (completed keys + participants). Guild settings and queue will be kept. Continue?"
        );
        if (!confirmed) {
            setAdminStatus("Clear history cancelled.");
            return;
        }
        try {
            await handleClearHistory();
        } catch (error) {
            setAdminStatus(`Clear history failed: ${error.message}`, true);
        }
    })
);
elements.clearLogsBtn?.addEventListener("click", () =>
    withAction(elements.clearLogsBtn, async () => {
        const confirmed = window.confirm(
            "This will clear runtime event logs used for debugging (logs/events.jsonl). Continue?"
        );
        if (!confirmed) {
            setAdminStatus("Clear logs cancelled.");
            return;
        }
        try {
            await handleClearLogs();
        } catch (error) {
            setAdminStatus(`Clear logs failed: ${error.message}`, true);
        }
    })
);
elements.downloadLogsBtn?.addEventListener("click", () =>
    withAction(elements.downloadLogsBtn, async () => {
        try {
            handleDownloadLogs();
        } catch (error) {
            setAdminStatus(`Download logs failed: ${error.message}`, true);
        }
    })
);
elements.addFakePlayerForm?.addEventListener("submit", async (event) => {
    const submitButton = elements.addFakePlayerForm.querySelector('button[type="submit"]');
    await withAction(submitButton, async () => {
        try {
            await handleAddFakePlayer(event);
        } catch (error) {
            setAdminStatus(`Add fake player failed: ${error.message}`, true);
        }
    });
});
elements.addFakeGroupForm?.addEventListener("submit", async (event) => {
    const submitButton = elements.addFakeGroupForm.querySelector('button[type="submit"]');
    await withAction(submitButton, async () => {
        try {
            await handleAddFakeGroup(event);
        } catch (error) {
            setAdminStatus(`Add fake group failed: ${error.message}`, true);
        }
    });
});
loadDashboard();
setInterval(loadDashboard, POLL_INTERVAL_MS);
