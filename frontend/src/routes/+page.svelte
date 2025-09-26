<script lang="ts">
    import { onMount } from "svelte";

    import {
        ChevronRight,
        CloudDownload,
        DatabaseBackup,
        RefreshCcw,
        Users,
    } from "@lucide/svelte";

    import { goto } from "$app/navigation";
    import { resolve } from "$app/paths";
    import type { ProfileStatus, StatusResponse } from "$lib/types/api";
    import { apiFetch, apiJson } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

    let profiles: StatusResponse["profiles"] = $state({});
    let isLoading = $state(true);
    let lastRefreshed: number | null = $state(null);
    let ws: WebSocket | null = $state(null);

    function profileEntries() {
        return Object.entries(profiles).sort((a, b) => a[0].localeCompare(b[0]));
    }

    function isProfileRunning(p?: ProfileStatus): boolean {
        return p?.status?.current_sync?.state === "running";
    }

    function anyRunning(): boolean {
        for (const [, p] of Object.entries(profiles)) {
            if (isProfileRunning(p)) return true;
        }
        return false;
    }

    function formatTimeAgo(ts?: string) {
        if (!ts) return "—";
        const d = new Date(ts);
        const diff = Date.now() - d.getTime();
        const sec = Math.floor(diff / 1000);
        if (sec < 45) return "just now";
        const min = Math.floor(sec / 60);
        if (min < 60) return `${min}m ago`;
        const hr = Math.floor(min / 60);
        if (hr < 24) return `${hr}h ago`;
        const day = Math.floor(hr / 24);
        return `${day}d ago`;
    }

    async function refresh() {
        try {
            const d = await apiJson<StatusResponse>("/api/status");
            profiles = d.profiles;
            isLoading = false;
            lastRefreshed = Date.now();
        } catch (e) {
            console.error("Failed to load status", e);
            toast("Failed to load status", "error");
        }
    }

    function openWs() {
        try {
            ws?.close();
        } catch {}
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${proto}//${location.host}/ws/status`;
        ws = new WebSocket(url);
        ws.onmessage = (ev) => {
            try {
                const data = JSON.parse(ev.data);
                if (data.profiles) {
                    profiles = data.profiles;
                    isLoading = false;
                    lastRefreshed = Date.now();
                }
            } catch {}
        };
        ws.onclose = () => {
            setTimeout(openWs, 2000);
        };
    }

    async function syncAll(poll: boolean) {
        await apiFetch(
            `/api/sync?poll=${poll}`,
            { method: "POST" },
            {
                successMessage: poll
                    ? "Triggered poll sync for all profiles"
                    : "Triggered full sync for all profiles",
            },
        );
        refresh();
    }

    async function syncDatabase() {
        await apiFetch(
            `/api/sync/database`,
            { method: "POST" },
            { successMessage: "Triggered database sync" },
        );
        refresh();
    }

    async function syncProfile(name: string, poll: boolean) {
        await apiFetch(
            `/api/sync/profile/${name}?poll=${poll}`,
            { method: "POST" },
            {
                successMessage: poll
                    ? `Triggered poll sync for profile ${name}`
                    : `Triggered full sync for profile ${name}`,
            },
        );
        refresh();
    }

    function goTimeline(name: string) {
        goto(resolve(`/timeline/${name}`));
    }

    function progressPercent(p: ProfileStatus): number | null {
        const c = p.status?.current_sync;
        if (!c || c.state !== "running") return null;
        const secIdx = Math.max(0, (c.section_index || 1) - 1);
        const secCount = Math.max(1, c.section_count || 1);
        const total = Math.max(1, c.section_items_total || 1);
        const done = Math.min(total, c.section_items_processed || 0);
        const sectionFrac = total > 0 ? done / total : 0;
        const overall = (secIdx + sectionFrac) / secCount;
        return Math.max(0, Math.min(1, overall));
    }

    onMount(() => {
        refresh();
        openWs();
    });
</script>

<div class="space-y-6">
    <div class="space-y-2">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-1 sm:flex-1">
                <div class="flex items-center gap-2">
                    <Users class="inline h-4 w-4 text-slate-300" />
                    <h2 class="text-lg font-semibold">Profiles</h2>
                    <span class="hidden text-xs text-slate-500 sm:inline"
                        >{Object.keys(profiles).length} total {#if lastRefreshed}•
                            updated {formatTimeAgo(
                                new Date(lastRefreshed).toISOString(),
                            )}{/if}</span>
                </div>
                <p class="text-xs text-slate-400">Browse your configured profiles.</p>
            </div>
            <div class="flex flex-wrap gap-2 sm:justify-end">
                <button
                    class="inline-flex items-center gap-1 rounded-md border border-amber-600/60 bg-amber-600/30 px-2 py-1 text-xs font-medium text-amber-200 shadow-sm backdrop-blur-sm transition-colors hover:bg-amber-600/40 focus:ring-2 focus:ring-amber-500/40 focus:outline-none sm:gap-1 sm:px-3 sm:py-1.5 sm:text-sm"
                    onclick={syncDatabase}>
                    <DatabaseBackup class="inline h-3 w-3 sm:h-4 sm:w-4" />
                    <span>Sync Database</span>
                </button>
                <button
                    class="inline-flex items-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-2 py-1 text-xs font-medium text-emerald-200 shadow-sm backdrop-blur-sm transition-colors hover:bg-emerald-600/40 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 sm:gap-1 sm:px-3 sm:py-1.5 sm:text-sm"
                    onclick={() => syncAll(false)}
                    disabled={anyRunning()}
                    title={anyRunning()
                        ? "A sync is currently running. Please wait."
                        : "Trigger a full sync for all profiles"}>
                    <RefreshCcw class="inline h-3 w-3 sm:h-4 sm:w-4" />
                    <span>Full Sync All</span>
                </button>
                <button
                    class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-600/30 px-2 py-1 text-xs font-medium text-sky-200 shadow-sm backdrop-blur-sm transition-colors hover:bg-sky-600/40 focus:ring-2 focus:ring-sky-500/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 sm:gap-1 sm:px-3 sm:py-1.5 sm:text-sm"
                    onclick={() => syncAll(true)}
                    disabled={anyRunning()}
                    title={anyRunning()
                        ? "A sync is currently running. Please wait."
                        : "Trigger a poll sync for all profiles"}>
                    <CloudDownload class="inline h-3 w-3 sm:h-4 sm:w-4" />
                    <span>Poll Sync All</span>
                </button>
            </div>
        </div>
    </div>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(min(100%,32rem),1fr))] gap-4">
        {#if isLoading && Object.keys(profiles).length === 0}
            {#each [1, 2, 3] as i (i)}
                <div
                    class="animate-pulse rounded-md border border-slate-800/60 bg-slate-900/40 p-4">
                    <div class="h-4 w-1/3 rounded-md bg-slate-700/60"></div>
                    <div class="mt-3 h-3 w-1/2 rounded-md bg-slate-800/60"></div>
                    <div class="mt-3 flex gap-2">
                        <div class="h-6 w-20 rounded-md bg-slate-800/60"></div>
                        <div class="h-6 w-24 rounded-md bg-slate-800/60"></div>
                        <div class="h-6 w-16 rounded-md bg-slate-800/60"></div>
                    </div>
                </div>
            {/each}
        {/if}
        {#each profileEntries() as [name, p] (name)}
            <button
                type="button"
                class="group cursor-pointer rounded-md border border-slate-800/80 bg-slate-900/50 p-4 text-left transition-colors hover:bg-slate-900/70 focus:ring-2 focus:ring-sky-600/40 focus:outline-none"
                onclick={() => goTimeline(name)}
                title={`Open timeline for ${name}`}>
                <div
                    class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                        <div class="font-medium text-slate-100">{name}</div>
                        <div class="mt-1 text-xs text-slate-400">
                            {#if p.status?.last_synced}
                                <span
                                    title={new Date(
                                        p.status.last_synced + "Z",
                                    ).toLocaleString()}
                                    >Last sync · {formatTimeAgo(
                                        p.status.last_synced,
                                    )}</span>
                            {:else}
                                <span>No sync yet</span>
                            {/if}
                        </div>
                    </div>
                    <div class="flex flex-wrap items-start gap-2">
                        <a
                            href={resolve(`/timeline/${name}`)}
                            class="inline-flex items-center gap-1 rounded-md border border-indigo-600/60 bg-indigo-600/30 px-2 py-1 text-[11px] font-medium text-indigo-200 shadow-sm hover:bg-indigo-600/40">
                            <span>Timeline</span>
                            <ChevronRight class="inline h-3 w-3" />
                        </a>
                        <span
                            role="button"
                            tabindex="0"
                            aria-disabled={isProfileRunning(p)}
                            onclick={(e) => {
                                e.stopPropagation();
                                if (!isProfileRunning(p)) syncProfile(name, false);
                            }}
                            onkeydown={(e) =>
                                (e.key === "Enter" || e.key === " ") &&
                                (e.preventDefault(),
                                e.stopPropagation(),
                                !isProfileRunning(p) && syncProfile(name, false))}
                            class="inline-flex items-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-2 py-1 text-[11px] font-medium text-emerald-200 hover:bg-emerald-600/40"
                            class:opacity-50={isProfileRunning(p)}
                            class:cursor-not-allowed={isProfileRunning(p)}
                            title={isProfileRunning(p)
                                ? "Sync in progress. Please wait."
                                : "Full sync this profile"}>
                            <RefreshCcw class="inline h-3 w-3" />
                            <span>Full</span>
                        </span>
                        <span
                            role="button"
                            tabindex="0"
                            aria-disabled={isProfileRunning(p)}
                            onclick={(e) => {
                                e.stopPropagation();
                                if (!isProfileRunning(p)) syncProfile(name, true);
                            }}
                            onkeydown={(e) =>
                                (e.key === "Enter" || e.key === " ") &&
                                (e.preventDefault(),
                                e.stopPropagation(),
                                !isProfileRunning(p) && syncProfile(name, true))}
                            class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-600/30 px-2 py-1 text-[11px] font-medium text-sky-200 hover:bg-sky-600/40"
                            class:opacity-50={isProfileRunning(p)}
                            class:cursor-not-allowed={isProfileRunning(p)}
                            title={isProfileRunning(p)
                                ? "Sync in progress. Please wait."
                                : "Poll sync this profile"}>
                            <CloudDownload class="inline h-3 w-3" />
                            <span>Poll</span>
                        </span>
                    </div>
                </div>
                {#if p.status?.current_sync?.state === "running"}
                    <div class="mt-3 space-y-2">
                        <div
                            class="flex items-center justify-between text-[11px] text-slate-400">
                            <div class="truncate">
                                {#if p.status.current_sync.section_title}
                                    <span class="text-slate-300"
                                        >{p.status.current_sync.section_title}</span>
                                    <span class="mx-1">•</span>
                                {/if}
                                <span class="tracking-wide uppercase"
                                    >{p.status.current_sync.stage ||
                                        "processing"}</span>
                            </div>
                            <div>
                                {p.status.current_sync.section_items_processed || 0}/{p
                                    .status.current_sync.section_items_total || 0}
                            </div>
                        </div>
                        {#key p.status.current_sync.section_index}
                            <div
                                class="h-2 w-full overflow-hidden rounded bg-slate-800/80">
                                <div
                                    class="h-full bg-gradient-to-r from-indigo-500 via-sky-500 to-cyan-400 transition-[width] duration-300 ease-out"
                                    style={`width: ${Math.round((progressPercent(p) ?? 0) * 100)}%`}>
                                </div>
                            </div>
                        {/key}
                    </div>
                {/if}
                <div class="mt-3 flex flex-wrap gap-2 text-xs">
                    {#if p.config?.anilist_user}<span
                            class="rounded-md bg-slate-800/80 px-2 py-1 text-slate-200"
                            >{p.config.anilist_user}</span
                        >{/if}
                    <span class="rounded-md bg-slate-800/80 px-2 py-1 text-slate-300"
                        >Interval: {p.config?.sync_interval ?? "-"}</span>
                    {#if p.config?.sync_modes?.includes("periodic")}<span
                            class="rounded-md bg-blue-900/50 px-2 py-1 text-blue-200"
                            >Periodic Sync</span
                        >{/if}
                    {#if p.config?.sync_modes?.includes("poll")}<span
                            class="rounded-md bg-blue-900/50 px-2 py-1 text-blue-200"
                            >Poll Sync</span
                        >{/if}
                    {#if p.config?.sync_modes?.includes("webhook")}<span
                            class="rounded-md bg-blue-900/50 px-2 py-1 text-blue-200"
                            >Webhook Sync</span
                        >{/if}
                </div>
            </button>
        {/each}
    </div>
</div>
