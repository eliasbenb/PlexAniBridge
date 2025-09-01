<script lang="ts">
    import { onMount } from "svelte";

    import {
        ArrowRight,
        ArrowUp,
        Check,
        Circle,
        CircleCheck,
        CircleX,
        Clock,
        CloudDownload,
        Copy,
        ExternalLink,
        Funnel,
        History,
        Infinity,
        LoaderCircle,
        RefreshCcw,
        RotateCw,
        Search,
        SearchX,
        SkipForward,
        SquareMinus,
        SquarePlus,
        Trash2,
        X,
    } from "@lucide/svelte";

    const { params } = $props<{ params: { profile: string } }>();

    type HistoryItem = {
        id: number;
        outcome: string;
        timestamp: string;
        anilist_id?: number;
        plex_guid?: string;
        plex_rating_key?: string;
        plex_child_rating_key?: string | null;
        plex_type?: string;
        error_message?: string;
        before_state?: any;
        after_state?: any;
        anilist?: {
            id?: number;
            title?: { romaji?: string; english?: string; native?: string };
            coverImage?: {
                medium?: string;
                large?: string;
                extraLarge?: string;
                color: string;
            };
            format?: string;
            status?: string;
            episodes?: number;
        };
        plex?: {
            guid?: string;
            title?: string;
            type?: string | null;
            art?: string | null;
            thumb?: string | null;
        };
    };

    let items: HistoryItem[] = $state([]);
    let stats: Record<string, number> = $state({});
    let loadingInitial = $state(true);
    let loadingMore = $state(false);
    let page = $state(1);
    let pages = $state(1);
    let perPage = $state(50);
    let outcomeFilter: string | null = $state(null);
    let showJump = $state(false);
    let newItemsCount = $state(0);
    let ws: WebSocket | null = null;
    let knownIds = new Set<number>();
    let sentinel: HTMLDivElement | null = $state(null);
    let titleLangTick = $state(0); // force rerender on title language preference change
    let openDiff: Record<number, boolean> = $state({});

    type ItemDiffUi = {
        tab: "changes" | "compare";
        filter: string;
        showUnchanged: boolean;
    };

    let diffUi: Record<number, ItemDiffUi> = $state({});

    function ensureDiffUi(id: number): ItemDiffUi {
        return (diffUi[id] ??= { tab: "changes", filter: "", showUnchanged: false });
    }

    function toggleDiff(id: number) {
        openDiff[id] = !openDiff[id];
        ensureDiffUi(id);
    }

    type DiffEntry = {
        path: string;
        before: any;
        after: any;
        status: "added" | "removed" | "changed" | "unchanged";
    };

    function buildDiff(item: HistoryItem): DiffEntry[] {
        const before = item.before_state || {};
        const after = item.after_state || {};
        const paths = new Set<string>();
        const visit = (obj: any, base = "") => {
            if (!obj || typeof obj !== "object") return;
            for (const k of Object.keys(obj)) {
                const val = obj[k];
                const path = base ? `${base}.${k}` : k;
                if (val && typeof val === "object" && !Array.isArray(val))
                    visit(val, path);
                else paths.add(path);
            }
        };
        visit(before);
        visit(after);
        const diff: DiffEntry[] = [];
        for (const p of paths) {
            const segs = p.split(".");
            const get = (root: any) =>
                segs.reduce((o, k) => (o && k in o ? o[k] : undefined), root);
            const bv = get(before);
            const av = get(after);
            let status: DiffEntry["status"] = "unchanged";
            if (bv === undefined && av !== undefined) status = "added";
            else if (bv !== undefined && av === undefined) status = "removed";
            else if (JSON.stringify(bv) !== JSON.stringify(av)) status = "changed";
            diff.push({ path: p, before: bv, after: av, status });
        }
        const weight: Record<string, number> = {
            changed: 0,
            added: 1,
            removed: 2,
            unchanged: 3,
        };
        diff.sort(
            (a, b) =>
                weight[a.status] - weight[b.status] || a.path.localeCompare(b.path),
        );
        return diff;
    }

    function truncateValue(v: any, max = 120) {
        if (v === null) return "null";
        if (v === undefined) return "undefined";
        const s = typeof v === "string" ? v : JSON.stringify(v);
        return s.length > max ? s.slice(0, max - 1) + "…" : s;
    }

    function sizeLabel(obj: any) {
        if (!obj) return "0 keys";
        let count = 0;
        const scan = (o: any) => {
            if (o && typeof o === "object")
                Object.keys(o).forEach((k) => {
                    count++;
                    if (o[k] && typeof o[k] === "object" && !Array.isArray(o[k]))
                        scan(o[k]);
                });
        };
        scan(obj);
        return count + " keys";
    }

    function highlightJson(obj: any) {
        if (!obj) return '<span class="text-slate-600">—</span>';
        const json = JSON.stringify(obj, null, 2);
        return json
            .replace(/(&|<)/g, (c) => (c === "&" ? "&amp;" : "&lt;"))
            .replace(
                /("(\\.|[^"])*"\s*:)|("(\\.|[^"])*")|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g,
                (m) => {
                    if (/^".*":$/.test(m))
                        return `<span class='text-sky-300'>${m}</span>`;
                    if (/^"/.test(m))
                        return `<span class='text-emerald-300'>${m}</span>`;
                    if (/true|false/.test(m))
                        return `<span class='text-indigo-300'>${m}</span>`;
                    if (/null/.test(m))
                        return `<span class='text-pink-300'>${m}</span>`;
                    return `<span class='text-amber-300'>${m}</span>`;
                },
            );
    }

    function copyJson(obj: any) {
        try {
            navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
        } catch {}
    }

    const OUTCOME_META: Record<
        string,
        { label: string; color: string; icon: any; order: number }
    > = {
        synced: {
            label: "Synced",
            color: "bg-emerald-600/80",
            icon: CircleCheck,
            order: 0,
        },
        failed: { label: "Failed", color: "bg-red-600/80", icon: CircleX, order: 1 },
        not_found: {
            label: "Not Found",
            color: "bg-amber-500/80",
            icon: SearchX,
            order: 2,
        },
        deleted: { label: "Deleted", color: "bg-rose-600/80", icon: Trash2, order: 3 },
        pending: { label: "Pending", color: "bg-slate-600/80", icon: Clock, order: 4 },
        skipped: {
            label: "Skipped",
            color: "bg-slate-500/60",
            icon: SkipForward,
            order: 5,
        },
    };

    function metaFor(o: string) {
        return (
            OUTCOME_META[o] ?? {
                label: o,
                color: "bg-slate-600/70",
                icon: Circle,
                order: 999,
            }
        );
    }

    function orderedStats() {
        return Object.fromEntries(
            Object.entries(stats).sort(
                (a, b) => metaFor(a[0]).order - metaFor(b[0]).order,
            ),
        );
    }

    const buildQuery = (p: number) => {
        const u = new URLSearchParams({ page: String(p), per_page: String(perPage) });
        if (outcomeFilter) u.set("outcome", outcomeFilter);
        return `/api/history/${params.profile}?${u}`;
    };

    function preferredTitle(t?: {
        romaji?: string;
        english?: string;
        native?: string;
    }) {
        if (!t) return null;
        let pref: string | null = null;
        try {
            pref = localStorage.getItem("anilist.lang");
        } catch {}
        if (pref && (t as any)[pref]) return (t as any)[pref] as string;
        return t.romaji || t.english || t.native || null;
    }

    function displayTitle(item: HistoryItem) {
        return (
            preferredTitle(item.anilist?.title) ||
            item.plex?.title ||
            (item.anilist_id ? `AniList ID: ${item.anilist_id}` : null) ||
            (item.plex_guid ? item.plex_guid : "Unknown Title")
        );
    }

    function coverImage(item: HistoryItem) {
        return (
            item.anilist?.coverImage?.large ||
            item.anilist?.coverImage?.medium ||
            item.anilist?.coverImage?.extraLarge ||
            item.plex?.thumb ||
            item.plex?.art ||
            null
        );
    }

    function anilistUrl(item: HistoryItem) {
        return item.anilist?.id ? `https://anilist.co/anime/${item.anilist.id}` : null;
    }

    function plexUrl(item: HistoryItem) {
        if (!item.plex_guid) return null;
        const cleanGuid = item.plex_guid.split("/").pop();
        const key = encodeURIComponent(`/library/metadata/${cleanGuid}`);
        return `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=${key}`;
    }

    async function deleteHistory(item: HistoryItem) {
        if (!confirm("Delete this history entry?")) return;
        try {
            const res = await fetch(`/api/history/${params.profile}/${item.id}`, {
                method: "DELETE",
            });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            // Remove locally
            items = items.filter((i) => i.id !== item.id);
            knownIds.delete(item.id);
            // Adjust stats
            const oc = data.outcome || item.outcome;
            if (oc) stats[oc] = Math.max(0, (stats[oc] || 1) - 1);
        } catch (e) {
            // @ts-ignore
            if (window.notify?.toast) window.notify.toast("Delete failed", "error");
            console.error(e);
        }
    }

    let isNearTop = $state(true);

    function handleScroll() {
        isNearTop = window.scrollY < 120;
        if (isNearTop) newItemsCount = 0;
        showJump = !isNearTop && (newItemsCount > 0 || window.scrollY > 400);
    }

    async function loadFirst() {
        loadingInitial = true;
        try {
            const r = await fetch(buildQuery(1));
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            items = d.items || [];
            stats = d.stats || {};
            page = d.page || 1;
            pages = d.pages || 1;
            perPage = d.per_page || perPage;
            knownIds = new Set(items.map((i) => i.id));
            newItemsCount = 0;
        } catch (e) {
            console.error(e);
        } finally {
            loadingInitial = false;
        }
    }

    async function loadMore() {
        if (loadingMore || page >= pages) return;
        loadingMore = true;
        const next = page + 1;
        try {
            const r = await fetch(buildQuery(next));
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            const existing = new Set(items.map((i: HistoryItem) => i.id));
            const newOnes = (d.items || []).filter(
                (i: HistoryItem) => !existing.has(i.id),
            );
            items = [...items, ...newOnes];
            stats = d.stats || stats;
            page = d.page || next;
            pages = d.pages || pages;
            perPage = d.per_page || perPage;
            newOnes.forEach((i: HistoryItem) => knownIds.add(i.id));
        } catch (e) {
            console.error(e);
        } finally {
            loadingMore = false;
        }
    }

    function toggleOutcomeFilter(k: string) {
        outcomeFilter = outcomeFilter === k ? null : k;
        loadFirst();
    }

    function initWs() {
        try {
            ws?.close();
        } catch {}
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${proto}//${location.host}/ws/history/${params.profile}`);
        ws.onmessage = (ev) => {
            try {
                const d = JSON.parse(ev.data);
                if (!Array.isArray(d.items)) return;
                let added = 0;
                for (const it of d.items) {
                    if (!knownIds.has(it.id)) {
                        items = [it, ...items];
                        knownIds.add(it.id);
                        added++;
                    }
                }
                if (added && !isNearTop) newItemsCount += added;
                handleScroll();
            } catch {}
        };
    }

    function jumpToLatest() {
        window.scrollTo({ top: 0, behavior: "smooth" });
        setTimeout(() => {
            newItemsCount = 0;
            handleScroll();
        }, 400);
    }

    async function triggerSync(poll: boolean) {
        try {
            await fetch(`/api/sync/${params.profile}?poll=${poll}`, { method: "POST" });
            // optionally surface toast if a global notifier exists
            // @ts-ignore
            if (window.notify?.toast) window.notify.toast("Sync started", "info");
        } catch (e) {
            // @ts-ignore
            if (window.notify?.toast) window.notify.toast("Sync failed", "error");
        }
    }

    onMount(() => {
        loadFirst();
        initWs();
        const langHandler = () => titleLangTick++;
        addEventListener("anilist-lang-changed", langHandler);
        const io = new IntersectionObserver((entries) => {
            for (const e of entries) if (e.isIntersecting) loadMore();
        });
        if (sentinel) io.observe(sentinel);
        addEventListener("scroll", handleScroll, { passive: true });
        return () => {
            try {
                ws?.close();
            } catch {}
            removeEventListener("anilist-lang-changed", langHandler);
            removeEventListener("scroll", handleScroll);
            io.disconnect();
        };
    });
</script>

<div class="space-y-6">
    <div class="flex flex-wrap items-center gap-2">
        <History class="inline h-4 w-4 text-slate-300" />
        <h2 class="text-lg font-semibold">Sync Timeline</h2>
        <span class="text-xs text-slate-500">profile: <i>{params.profile}</i></span>
        <div class="ml-auto flex items-center gap-2 text-[11px]">
            <button
                onclick={() => triggerSync(false)}
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-2 py-1 font-medium text-emerald-200 hover:bg-emerald-600/40"
                ><RefreshCcw class="inline h-4 w-4 text-[14px]" /> Full Sync</button
            >
            <button
                onclick={() => triggerSync(true)}
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-600/30 px-2 py-1 font-medium text-sky-200 hover:bg-sky-600/40"
                ><CloudDownload class="inline h-4 w-4 text-[14px]" /> Poll Sync</button
            >
            <button
                onclick={() => loadFirst()}
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-slate-600/60 bg-slate-700/40 px-2 py-1 font-medium text-slate-200 hover:bg-slate-600/50"
                ><RotateCw class="inline h-4 w-4 text-[14px]" /> Reload</button
            >
        </div>
    </div>
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {#each Object.entries(orderedStats()) as [k, v] (k)}
            <button
                type="button"
                onclick={() => toggleOutcomeFilter(k)}
                class={`group relative cursor-pointer select-none overflow-hidden rounded-md p-3 text-left transition ${outcomeFilter === k ? "border-sky-500 bg-sky-950/40 ring-1 ring-sky-400/60" : "border border-slate-800 bg-gradient-to-br from-slate-900/70 to-slate-800/30 hover:border-slate-700"}`}
                title={outcomeFilter === k
                    ? "Click to remove filter"
                    : "Funnel by " + metaFor(k).label}
            >
                <div
                    class="text-[10px] font-medium uppercase tracking-wide text-slate-400"
                >
                    {metaFor(k).label}
                </div>
                <div class="mt-1 text-2xl font-semibold tabular-nums">{v}</div>
                {#if outcomeFilter === k}
                    <div class="absolute right-1 top-1">
                        <span
                            class="mr-1 inline-flex items-center gap-0.5 rounded bg-sky-600/70 px-1 py-0.5 text-[9px] font-semibold text-white"
                            ><Funnel class="inline h-3 w-3" /> Active</span
                        >
                    </div>
                {/if}
            </button>
        {/each}
    </div>
    {#if outcomeFilter}
        <div class="flex items-center gap-2 text-[11px] text-slate-400">
            <div>
                Filtering by <span class="font-semibold text-slate-200"
                    >{metaFor(outcomeFilter).label}</span
                >
            </div>
            <button
                onclick={() => ((outcomeFilter = null), loadFirst())}
                class="flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-sky-300 hover:bg-slate-700"
                ><X class="inline h-3.5 w-3.5" /> Clear</button
            >
        </div>
    {/if}
    <div
        class="flex items-center gap-2 text-[11px] text-slate-500"
        hidden={!items.length}
    >
        <span class="inline-flex items-center gap-1"
            ><Infinity class="inline h-4 w-4" /> Scroll to load older history</span
        >
        {#if loadingMore}<span class="inline-flex items-center gap-1 text-sky-300"
                ><LoaderCircle class="inline h-4 w-4 animate-spin" /> Loading…</span
            >{/if}
        {#if !loadingMore && page >= pages}<span
                class="inline-flex items-center gap-1 text-emerald-400"
                ><Check class="inline h-4 w-4" /> All loaded</span
            >{/if}
    </div>
    <div class="space-y-4" class:hidden={!items.length && !loadingInitial}>
        {#each items as item (item.id + "-" + titleLangTick)}
            {@const meta = metaFor(item.outcome)}
            <div
                class="flex gap-3 overflow-hidden rounded-md border border-slate-800 bg-slate-900/60 p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md"
            >
                <div class={`w-1 rounded-md ${meta.color}`}></div>
                <div class="flex min-w-0 flex-1 gap-3">
                    {#if coverImage(item)}
                        <div
                            class="relative h-20 w-14 shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-800/40"
                        >
                            <img
                                src={coverImage(item)!}
                                alt={displayTitle(item) || "Cover"}
                                loading="lazy"
                                class="h-full w-full object-cover"
                            />
                        </div>
                    {:else}
                        <div
                            class="flex h-20 w-14 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500"
                        >
                            No Art
                        </div>
                    {/if}
                    <div class="min-w-0 flex-1 space-y-1">
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0">
                                <div class="flex items-center gap-2">
                                    <span
                                        class="truncate font-medium"
                                        title={displayTitle(item)}
                                        >{displayTitle(item)}</span
                                    >
                                    <span
                                        class={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${meta.color}`}
                                    >
                                        <meta.icon
                                            class="inline h-3.5 w-3.5 text-[10px]"
                                        />
                                        {meta.label}
                                    </span>
                                </div>
                                <div
                                    class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400"
                                >
                                    {#if item.anilist?.id}
                                        <a
                                            href={anilistUrl(item)!}
                                            target="_blank"
                                            rel="noopener"
                                            class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-700/50 px-1 py-0.5 text-[9px] font-semibold text-sky-100 hover:bg-sky-600/60"
                                            title="Open in AniList"
                                            ><ExternalLink
                                                class="inline h-3.5 w-3.5 text-[11px]"
                                            />AniList</a
                                        >
                                    {/if}
                                    {#if item.plex_guid}
                                        <a
                                            href={plexUrl(item)!}
                                            target="_blank"
                                            rel="noopener"
                                            class="inline-flex items-center gap-1 rounded-md border border-amber-600 bg-amber-700/60 px-1.5 py-0.5 text-[10px] text-amber-100 transition-colors hover:bg-amber-600/60"
                                            title="Open in Plex"
                                        >
                                            <ExternalLink
                                                class="inline h-3.5 w-3.5 text-[11px]"
                                            /> Plex</a
                                        >
                                    {/if}
                                    <span class="text-xs text-slate-400"
                                        >{new Date(
                                            item.timestamp + "Z",
                                        ).toLocaleString()}</span
                                    >
                                    {#if item.anilist?.format}<span
                                            class="hidden rounded-md bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-300 sm:inline-flex"
                                            title="Format">{item.anilist.format}</span
                                        >{/if}
                                    {#if item.anilist?.episodes}<span
                                            class="hidden rounded-md bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-300 sm:inline-flex"
                                            title="Episodes"
                                            >Ep {item.anilist.episodes}</span
                                        >{/if}
                                    {#if item.anilist?.status}<span
                                            class="hidden rounded-md bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline-flex"
                                            title="AniList Status"
                                            >{item.anilist.status}</span
                                        >{/if}
                                </div>
                            </div>
                            <div class="flex shrink-0 items-center gap-2">
                                <button
                                    type="button"
                                    onclick={() => deleteHistory(item)}
                                    class="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-red-600/60 bg-red-700/40 px-2 text-[11px] font-medium text-red-100 hover:bg-red-600/50"
                                    title="Delete history entry"
                                >
                                    <Trash2 class="inline h-4 w-4" />
                                </button>
                            </div>
                        </div>
                        {#if item.error_message}<div class="text-[11px] text-red-400">
                                {item.error_message}
                            </div>{/if}
                        {#if item.outcome === "synced" && (item.before_state || item.after_state)}
                            <div class="pt-1">
                                <button
                                    type="button"
                                    onclick={() => toggleDiff(item.id)}
                                    class="inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300"
                                >
                                    {#if openDiff[item.id]}<SquareMinus
                                            class="inline h-4 w-4 text-[14px]"
                                        />{:else}<SquarePlus
                                            class="inline h-4 w-4 text-[14px]"
                                        />{/if}
                                    {openDiff[item.id] ? "Hide diff" : "Show diff"}
                                </button>
                            </div>
                        {/if}
                    </div>
                </div>
            </div>
            {#if openDiff[item.id] && item.outcome === "synced" && (item.before_state || item.after_state)}
                {@const ui = ensureDiffUi(item.id)}
                {@const diffs = buildDiff(item)}
                <div
                    class="mt-2 overflow-hidden rounded-md border border-slate-800 bg-slate-950/80"
                >
                    <div
                        class="flex flex-wrap items-center gap-3 border-b border-slate-800 px-3 py-2"
                    >
                        <div
                            class="flex items-center overflow-hidden rounded-md border border-slate-700/70 bg-slate-900/60 text-[11px]"
                        >
                            <button
                                class={`px-2 py-1 font-medium ${ui.tab === "changes" ? "bg-slate-700/70 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}
                                onclick={() => (ui.tab = "changes")}
                            >
                                Changes
                            </button>
                            <button
                                class={`hidden px-2 py-1 font-medium md:inline-flex ${ui.tab === "compare" ? "bg-slate-700/70 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}
                                onclick={() => (ui.tab = "compare")}
                            >
                                Compare
                            </button>
                        </div>
                        {#if ui.tab === "changes"}
                            <div
                                class="flex min-w-[12rem] grow items-center gap-2 text-[11px]"
                            >
                                <div class="relative flex-1">
                                    <Search
                                        class="absolute left-1.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                                    />
                                    <input
                                        bind:value={ui.filter}
                                        placeholder="Funnel path…"
                                        class="w-full rounded-md border border-slate-700/70 bg-slate-900/60 py-1 pl-6 pr-2 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
                                    />
                                </div>
                                <label
                                    class="inline-flex cursor-pointer select-none items-center gap-1"
                                >
                                    <input
                                        type="checkbox"
                                        checked={ui.showUnchanged}
                                        onchange={(e: Event) => {
                                            const target = e.target as HTMLInputElement;
                                            ui.showUnchanged = target.checked;
                                        }}
                                        class="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-0"
                                    />
                                    <span class="text-slate-400">Unchanged</span>
                                </label>
                            </div>
                        {/if}
                        <div class="ml-auto flex items-center gap-1">
                            <button
                                onclick={() => copyJson(item.before_state)}
                                class="flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                                title="Copy Before JSON"
                            >
                                <Copy class="inline h-3.5 w-3.5" /> <span>Before</span>
                            </button>
                            <button
                                onclick={() => copyJson(item.after_state)}
                                class="flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                                title="Copy After JSON"
                            >
                                <Copy class="inline h-3.5 w-3.5" /> <span>After</span>
                            </button>
                        </div>
                    </div>
                    <div class="space-y-3 p-3">
                        {#if ui.tab === "changes"}
                            {@const filtered = diffs.filter((d) => {
                                if (!ui.showUnchanged && d.status === "unchanged")
                                    return false;
                                if (
                                    ui.filter &&
                                    !d.path
                                        .toLowerCase()
                                        .includes(ui.filter.toLowerCase())
                                )
                                    return false;
                                return true;
                            })}
                            {#if filtered.length}
                                <ul class="divide-y divide-slate-800/60 text-[11px]">
                                    {#each filtered as d (d.path)}
                                        <li class="group px-1 py-1.5">
                                            <div
                                                class="flex flex-wrap items-start gap-2"
                                            >
                                                <span
                                                    class="max-w-full break-all rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 group-hover:bg-slate-700/80"
                                                    >{d.path}</span
                                                >
                                                <div
                                                    class="flex min-w-[10rem] flex-1 items-start gap-1.5"
                                                >
                                                    <span
                                                        class="min-w-0 break-all {d.status ===
                                                        'removed'
                                                            ? 'text-red-400'
                                                            : d.status === 'changed'
                                                              ? 'text-red-300'
                                                              : 'text-slate-500'}"
                                                        >{truncateValue(d.before)}</span
                                                    >
                                                    <ArrowRight
                                                        class="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600"
                                                    />
                                                    <span
                                                        class="min-w-0 break-all {d.status ===
                                                        'added'
                                                            ? 'text-emerald-400'
                                                            : d.status === 'changed'
                                                              ? 'text-emerald-300'
                                                              : 'text-slate-500'}"
                                                        >{truncateValue(d.after)}</span
                                                    >
                                                </div>
                                            </div>
                                        </li>
                                    {/each}
                                </ul>
                            {:else}
                                <p class="text-[11px] italic text-slate-500">
                                    No differences.
                                </p>
                            {/if}
                        {:else}
                            <div class="grid items-start gap-2 md:grid-cols-2 md:gap-3">
                                <div class="space-y-1.5">
                                    <h5
                                        class="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-slate-400"
                                    >
                                        Before <span
                                            class="text-[10px] font-normal text-slate-600"
                                            >{sizeLabel(item.before_state)}</span
                                        >
                                    </h5>
                                    <pre
                                        class="max-h-64 overflow-auto rounded-md border border-slate-800 bg-slate-900/80 p-2 text-[11px] leading-tight"><span
                                            >{@html highlightJson(
                                                item.before_state,
                                            )}</span
                                        ></pre>
                                </div>
                                <div class="space-y-1.5">
                                    <h5
                                        class="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-slate-400"
                                    >
                                        After <span
                                            class="text-[10px] font-normal text-slate-600"
                                            >{sizeLabel(item.after_state)}</span
                                        >
                                    </h5>
                                    <pre
                                        class="max-h-64 overflow-auto rounded-md border border-slate-800 bg-slate-900/80 p-2 text-[11px] leading-tight"><span
                                            >{@html highlightJson(
                                                item.after_state,
                                            )}</span
                                        ></pre>
                                </div>
                            </div>
                        {/if}
                    </div>
                </div>
            {/if}
        {/each}
    </div>
    {#if !items.length && !loadingInitial}
        <p class="text-sm text-slate-500">No history yet.</p>
    {/if}
    <div bind:this={sentinel}></div>
    {#if showJump}
        <div class="fixed bottom-6 right-6 z-40">
            <button
                onclick={jumpToLatest}
                class="pointer-events-auto flex items-center gap-2 rounded-md border border-sky-500/60 bg-gradient-to-r from-sky-600 to-sky-500 py-2 pl-3 pr-3 text-sm font-medium text-white shadow-md shadow-slate-950/40 backdrop-blur-md hover:from-sky-500 hover:to-sky-400"
            >
                <ArrowUp class="inline h-4 w-4" />
                <span class="hidden sm:inline">Latest</span>
                {#if newItemsCount > 0}<span
                        class="inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-white/20 bg-slate-900/70 px-1 text-[10px] font-semibold leading-none text-white shadow ring-1 ring-sky-300/40"
                        >{newItemsCount}</span
                    >{/if}
            </button>
        </div>
    {/if}
</div>
