<script lang="ts">
    import { onMount } from "svelte";

    import { LoaderCircle, Pin, RefreshCcw, Search, X } from "@lucide/svelte";

    import PinFieldsEditor from "$lib/components/timeline/pin-fields-editor.svelte";
    import TimelineItem, {
        type PinsPanelContext,
    } from "$lib/components/timeline/timeline-item.svelte";
    import type { OutcomeMeta } from "$lib/components/timeline/types";
    import type { MediaWithoutList as AniListMediaWithoutList } from "$lib/types/anilist";
    import type {
        HistoryItem,
        PinFieldOption,
        PinListResponse,
        PinResponse,
        PinSearchResponse,
        PinSearchResult,
    } from "$lib/types/api";
    import { preferredTitle } from "$lib/utils/anilist";
    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";
    import { clearPinOptionsCache, loadPinOptions } from "$lib/utils/pin-options";

    interface Props {
        profile: string;
    }
    let { profile }: Props = $props();

    // Panel open state
    let open = $state(false);

    // Shared pin options
    let options: PinFieldOption[] = $state([]);
    let optionsLoading = $state(false);
    let optionsError: string | null = $state(null);

    // Pinned list
    let pinned: PinResponse[] = $state([]);
    let pinnedLoading = $state(false);
    let pinnedError: string | null = $state(null);

    // Search state
    let q = $state("");
    let searchLoading = $state(false);
    let searchError: string | null = $state(null);
    let results: PinSearchResult[] = $state([]);

    // Per-row editor state
    type RowKey = number; // anilist id
    let expanded: Record<RowKey, boolean> = $state({});
    let saving: Record<RowKey, boolean> = $state({});
    let rowError: Record<RowKey, string | null> = $state({});
    let selections: Record<RowKey, string[]> = $state({});
    let baselines: Record<RowKey, string[]> = $state({});

    const PINNED_META: OutcomeMeta = {
        label: "Pinned",
        color: "bg-fuchsia-700/60",
        icon: Pin,
        order: 0,
    };

    const SEARCH_META: OutcomeMeta = {
        label: "Search",
        color: "bg-sky-700/60",
        icon: Search,
        order: 1,
    };

    interface PinsPanelData {
        value: string[];
        baseline: string[];
        options: PinFieldOption[];
        optionsLoading: boolean;
        saving: boolean;
        error: string | null;
        optionsError: string | null;
        disabled: boolean;
        onSave: (value: string[]) => void;
        onChange: (value: string[]) => void;
        onRefresh: (force: boolean) => void;
    }

    const timelineDisplayTitle = (item: HistoryItem): string | null =>
        preferredTitle(item.anilist?.title) ||
        (item.anilist_id ? `AniList ${item.anilist_id}` : null) ||
        "Unknown";

    const timelineCoverImage = (item: HistoryItem): string | null =>
        item.anilist?.coverImage?.large ||
        item.anilist?.coverImage?.medium ||
        item.anilist?.coverImage?.extraLarge ||
        null;

    const timelineAnilistUrl = (item: HistoryItem): string | null => {
        const id = item.anilist?.id || item.anilist_id;
        if (!id) return null;
        return `https://anilist.co/anime/${id}`;
    };

    const timelinePlexUrl = () => null;

    function toHistoryItem(
        aid: number,
        pin: PinResponse | null | undefined,
        anilist: AniListMediaWithoutList | null,
        outcome: string,
    ): HistoryItem {
        const timestamp = pin?.updated_at || pin?.created_at || "";
        return {
            id: aid,
            profile_name: profile,
            anilist_id: aid,
            outcome,
            before_state: null,
            after_state: null,
            error_message: null,
            timestamp,
            anilist: anilist ?? null,
            plex: null,
            pinned_fields: pin?.fields ?? [],
        } satisfies HistoryItem;
    }

    function setRow(aid: number, fields: string[], updateBaseline = false) {
        selections[aid] = [...fields];
        if (updateBaseline) baselines[aid] = [...fields];
    }

    async function ensureOptions(force = false) {
        if (options.length && !force) return;
        optionsLoading = true;
        optionsError = null;
        try {
            const loaded = await loadPinOptions(force);
            options = [...loaded];
        } catch (e) {
            console.error(e);
            optionsError = (e as Error)?.message || "Failed to load pin options";
        } finally {
            optionsLoading = false;
        }
    }

    async function loadPinned() {
        pinnedLoading = true;
        pinnedError = null;
        try {
            const r = await apiFetch(`/api/pins/${profile}?with_anilist=true`);
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = (await r.json()) as PinListResponse;
            pinned = d.pins || [];
            for (const p of pinned) setRow(p.anilist_id, p.fields || [], true);
        } catch (e) {
            console.error(e);
            pinnedError = (e as Error)?.message || "Failed to load pins";
            toast("Failed to load pins", "error");
        } finally {
            pinnedLoading = false;
        }
    }

    async function search() {
        const query = q.trim();
        if (!query) {
            results = [];
            searchError = null;
            return;
        }
        searchLoading = true;
        searchError = null;
        try {
            const u = new URLSearchParams({ q: query, limit: "10" });
            const r = await apiFetch(`/api/pins/${profile}/search?${u}`);
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = (await r.json()) as PinSearchResponse;
            results = d.results || [];
            for (const res of results) {
                const base = res.pin?.fields || [];
                setRow(Number(res.anilist.id), base, true);
            }
        } catch (e) {
            console.error(e);
            searchError = (e as Error)?.message || "Search failed";
        } finally {
            searchLoading = false;
        }
    }

    async function save(aid: number, fields: string[]) {
        if (saving[aid]) return;
        saving[aid] = true;
        rowError[aid] = null;
        try {
            if (!fields.length) {
                const r = await apiFetch(`/api/pins/${profile}/${aid}`, {
                    method: "DELETE",
                });
                if (!r.ok) throw new Error("HTTP " + r.status);
                setRow(aid, [], true);
                pinned = pinned.filter((p) => p.anilist_id !== aid);
                results = results.map((res) =>
                    Number(res.anilist.id) === aid ? { ...res, pin: null } : res,
                );
                toast("Pins cleared", "success");
                return;
            }
            const r = await apiFetch(
                `/api/pins/${profile}/${aid}?with_anilist=true`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fields }),
                },
                { successMessage: "Pins updated" },
            );
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = (await r.json()) as PinResponse;
            const next = d.fields || [];
            setRow(aid, next, true);

            const existing = pinned.find((p) => p.anilist_id === aid) || null;
            let anilistMeta = d.anilist ?? existing?.anilist ?? null;
            if (!anilistMeta) {
                const resMatch = results.find((res) => Number(res.anilist.id) === aid);
                anilistMeta = resMatch?.anilist ?? null;
            }
            const merged: PinResponse = {
                ...(existing ?? {}),
                ...d,
                anilist: anilistMeta,
            } as PinResponse;

            const idx = pinned.findIndex((p) => p.anilist_id === aid);
            if (idx >= 0) pinned[idx] = merged;
            else pinned = [merged, ...pinned];
            results = results.map((res) =>
                Number(res.anilist.id) === aid ? { ...res, pin: merged } : res,
            );
        } catch (e) {
            console.error(e);
            rowError[aid] = (e as Error)?.message || "Failed to save";
            toast("Failed to save pins", "error");
        } finally {
            saving[aid] = false;
        }
    }

    function togglePanel() {
        const next = !open;
        open = next;
        if (next) {
            void ensureOptions(false);
            void loadPinned();
        }
    }

    function refreshAll() {
        clearPinOptionsCache();
        void ensureOptions(true);
        void loadPinned();
        if (q.trim()) void search();
    }

    function toggleRow(aid: number) {
        expanded[aid] = !expanded[aid];
    }

    $effect(() => {
        if (!open) {
            expanded = {};
            saving = {};
            rowError = {};
        }
    });

    onMount(() => {
        void ensureOptions(false);
    });

    function panelDataFor(aid: number, base: string[], sel: string[]): PinsPanelData {
        return {
            value: sel,
            baseline: baselines[aid] ?? base,
            options,
            optionsLoading,
            saving: saving[aid] || false,
            error: rowError[aid] || null,
            optionsError,
            disabled: !!optionsError,
            onSave: (value: string[]) => save(aid, value),
            onChange: (value: string[]) => (selections[aid] = [...value]),
            onRefresh: (force: boolean) => ensureOptions(force),
        };
    }
</script>

{#snippet PinEditorPanel(props: PinsPanelContext)}
    {@const data = props.data as PinsPanelData | undefined}
    {#if props.openPins && data}
        <PinFieldsEditor
            value={data.value}
            baseline={data.baseline}
            options={data.options}
            loading={data.optionsLoading}
            saving={data.saving}
            error={data.error}
            optionsError={data.optionsError}
            disabled={data.disabled}
            title="Pin fields"
            subtitle="Keep these fields unchanged for this entry when syncing."
            onSave={data.onSave}
            onChange={data.onChange}
            onRefresh={data.onRefresh} />
    {/if}
{/snippet}

<div class="relative inline-flex items-center gap-2">
    <button
        type="button"
        class="inline-flex items-center gap-2 rounded-md border border-fuchsia-600/50 bg-fuchsia-600/20 py-1 pr-2 pl-2 text-[12px] font-medium text-fuchsia-100 hover:bg-fuchsia-600/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-400/60"
        aria-expanded={open}
        aria-controls="global-pins-panel"
        title={open ? "Hide pins manager" : "Show pins manager"}
        onclick={togglePanel}>
        <Pin class="inline h-4 w-4" />
        <span class="hidden sm:inline">Pins</span>
        <span
            class="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded border border-white/10 bg-fuchsia-700/30 px-1 text-[10px] font-semibold text-white/90">
            {pinned.length}
        </span>
    </button>
    <button
        type="button"
        class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[11px] text-slate-100 hover:border-slate-600 disabled:opacity-60"
        title="Refresh pins and options"
        disabled={!open}
        onclick={refreshAll}>
        <RefreshCcw class="inline h-3.5 w-3.5" />
        <span class="hidden md:inline">Refresh</span>
    </button>
</div>

{#if open}
    <section
        id="global-pins-panel"
        aria-label="Global pins manager"
        class="mt-2 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/70 shadow-md shadow-black/30">
        <div class="px-3 pt-2 pb-3 text-[11px]">
            <!-- Search bar -->
            <div class="mb-3 flex items-center gap-2">
                <div class="relative flex-1">
                    <Search
                        class="pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                    <input
                        class="h-8 w-full rounded-md border border-slate-700 bg-slate-900 pr-8 pl-8 text-[12px] text-slate-100 placeholder-slate-500 focus:border-slate-500 focus:outline-none"
                        placeholder="Search AniList titles"
                        bind:value={q}
                        onkeydown={(e) => (e.key === "Enter" ? search() : undefined)} />
                    {#if q}
                        <button
                            class="absolute top-1/2 right-2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                            title="Clear"
                            onclick={() => (
                                (q = ""),
                                (results = []),
                                (searchError = null)
                            )}>
                            <X class="inline h-3.5 w-3.5" />
                        </button>
                    {/if}
                </div>
                <button
                    class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-slate-200 hover:border-slate-600 disabled:opacity-60"
                    onclick={search}
                    disabled={searchLoading || !!optionsError}
                    title={optionsError ? "Load options first" : "Search"}>
                    {#if searchLoading}
                        <LoaderCircle class="inline h-3.5 w-3.5 animate-spin" />
                    {:else}
                        <Search class="inline h-3.5 w-3.5" />
                    {/if}
                    Search
                </button>
            </div>

            {#if optionsError}
                <div
                    class="mb-3 rounded-md border border-amber-600/60 bg-amber-900/20 px-3 py-2 text-amber-100">
                    <div class="mb-1 font-semibold">{optionsError}</div>
                    <button
                        class="inline-flex items-center gap-1 rounded-md border border-amber-500/70 px-2.5 py-1 hover:border-amber-400"
                        onclick={() => ensureOptions(true)}>
                        <RefreshCcw class="h-3.5 w-3.5" /> Retry loading options
                    </button>
                </div>
            {/if}

            <!-- Pinned list -->
            <div
                class="mb-4 overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
                <div
                    class="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                    <div class="flex items-center gap-2 text-[10px]">
                        <Pin class="h-3.5 w-3.5" />
                        <span
                            class="font-semibold tracking-wide text-slate-100 uppercase"
                            >Pinned entries</span>
                        <span class="text-[11px] font-normal text-slate-400 normal-case"
                            >{pinned.length}</span>
                    </div>
                    <div class="text-[11px] text-slate-400">
                        {#if pinnedLoading}
                            <span class="inline-flex items-center gap-1 text-sky-300"
                                ><LoaderCircle
                                    class="inline h-3.5 w-3.5 animate-spin" /> Loading…</span>
                        {/if}
                    </div>
                </div>
                <div class="divide-y divide-slate-800">
                    {#if pinnedError}
                        <div class="px-3 py-2 text-red-200">{pinnedError}</div>
                    {:else if !pinnedLoading && !pinned.length}
                        <div class="px-3 py-2 text-slate-400">No pinned entries.</div>
                    {/if}
                    {#each pinned as p (p.anilist_id)}
                        {@const aid = p.anilist_id}
                        {@const base = p.fields || []}
                        {@const sel = selections[aid] ?? base}
                        {@const historyItem = toHistoryItem(
                            aid,
                            p,
                            p.anilist ?? null,
                            "pinned",
                        )}
                        {@const panelData = panelDataFor(aid, base, sel)}
                        <div class="px-3 py-2">
                            <TimelineItem
                                {profile}
                                item={historyItem}
                                meta={PINNED_META}
                                displayTitle={timelineDisplayTitle}
                                coverImage={timelineCoverImage}
                                anilistUrl={timelineAnilistUrl}
                                plexUrl={timelinePlexUrl}
                                hasPins={true}
                                togglePins={(item) => toggleRow(item.id)}
                                openPins={expanded[aid] || false}
                                pinButtonLoading={saving[aid] || false}
                                pinButtonDisabled={!!optionsError}
                                pinCount={sel.length}
                                pinsPanel={PinEditorPanel}
                                pinsPanelData={panelData} />
                        </div>
                    {/each}
                </div>
            </div>

            <!-- Search results -->
            <div
                class="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
                <div
                    class="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                    <div class="flex items-center gap-2 text-[10px]">
                        <Search class="h-3.5 w-3.5" />
                        <span
                            class="font-semibold tracking-wide text-slate-100 uppercase"
                            >Search results</span>
                        <span class="text-[11px] font-normal text-slate-400 normal-case"
                            >{results.length}</span>
                    </div>
                    <div class="text-[11px] text-slate-400">
                        {#if searchLoading}
                            <span class="inline-flex items-center gap-1 text-sky-300"
                                ><LoaderCircle
                                    class="inline h-3.5 w-3.5 animate-spin" /> Loading…</span>
                        {/if}
                    </div>
                </div>
                <div class="divide-y divide-slate-800">
                    {#if searchError}
                        <div class="px-3 py-2 text-red-200">{searchError}</div>
                    {:else if !searchLoading && q && !results.length}
                        <div class="px-3 py-2 text-slate-400">No results.</div>
                    {/if}
                    {#each results as r (r.anilist.id)}
                        {@const aid = Number(r.anilist.id)}
                        {@const base = r.pin?.fields || []}
                        {@const sel = selections[aid] ?? base}
                        {@const meta = r.pin ? PINNED_META : SEARCH_META}
                        {@const historyItem = toHistoryItem(
                            aid,
                            r.pin ?? null,
                            r.anilist ?? null,
                            r.pin ? "pinned" : "search",
                        )}
                        {@const panelData = panelDataFor(aid, base, sel)}
                        <div class="px-3 py-2">
                            <TimelineItem
                                {profile}
                                item={historyItem}
                                {meta}
                                displayTitle={timelineDisplayTitle}
                                coverImage={timelineCoverImage}
                                anilistUrl={timelineAnilistUrl}
                                plexUrl={timelinePlexUrl}
                                hasPins={true}
                                togglePins={(item) => toggleRow(item.id)}
                                openPins={expanded[aid] || false}
                                pinButtonLoading={saving[aid] || false}
                                pinButtonDisabled={!!optionsError}
                                pinCount={sel.length}
                                pinsPanel={PinEditorPanel}
                                pinsPanelData={panelData} />
                        </div>
                    {/each}
                </div>
            </div>

            <div
                class="mt-2 flex items-center justify-between gap-2 border-t border-slate-800 bg-slate-950/60 px-3 py-2 text-[11px] text-slate-400">
                <div class="flex items-center gap-3">
                    <span class="mr-2">{pinned.length} pinned</span>
                    {#if optionsLoading}
                        <span class="inline-flex items-center gap-1 text-sky-300"
                            ><LoaderCircle class="inline h-3.5 w-3.5 animate-spin" /> options…</span>
                    {/if}
                    {#if searchLoading}
                        <span class="ml-2 inline-flex items-center gap-1 text-sky-300"
                            ><LoaderCircle class="inline h-3.5 w-3.5 animate-spin" /> search…</span>
                    {/if}
                </div>
                <div class="ml-auto">
                    <button
                        type="button"
                        class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 hover:border-slate-600"
                        onclick={togglePanel}>
                        <X class="inline h-3.5 w-3.5" />
                        Close
                    </button>
                </div>
            </div>
        </div>
    </section>
{/if}
