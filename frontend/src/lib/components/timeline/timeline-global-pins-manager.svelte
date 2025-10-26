<script lang="ts">
    import { onMount } from "svelte";

    import {
        ExternalLink,
        LoaderCircle,
        Pin,
        RefreshCcw,
        Search,
        SquareMinus,
        SquarePlus,
        X,
    } from "@lucide/svelte";

    import PinFieldsEditor from "$lib/components/timeline/pin-fields-editor.svelte";
    import type { MediaWithoutList as AniListMediaWithoutList } from "$lib/types/anilist";
    import type {
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

    const titleOf = (m?: AniListMediaWithoutList | null) =>
        preferredTitle(m?.title) || (m?.id ? `AniList ${m.id}` : "Unknown");

    const coverOf = (m?: AniListMediaWithoutList | null): string | null =>
        m?.coverImage?.large ||
        m?.coverImage?.medium ||
        m?.coverImage?.extraLarge ||
        null;

    const anilistUrlFor = (m?: AniListMediaWithoutList | null): string | null => {
        if (!m?.id) return null;
        return `https://anilist.co/anime/${m.id}`;
    };

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

    interface RowEntryProps {
        aid: number;
        anilist?: AniListMediaWithoutList | null;
        sel: string[];
        base: string[];
        accentClass: string;
        options: PinFieldOption[];
        optionsLoading: boolean;
        savingFlag: boolean;
        rowErr: string | null;
        disabled: boolean;
        onSave: (value: string[]) => void;
        onChange: (value: string[]) => void;
        onRefresh: (force: boolean) => void;
    }
</script>

{#snippet RowEntry(props: RowEntryProps)}
    {@const {
        aid,
        anilist,
        sel,
        base,
        accentClass,
        options,
        optionsLoading,
        savingFlag,
        rowErr,
        disabled,
        onSave,
        onChange,
        onRefresh,
    } = props}
    {@const coverHref = anilistUrlFor(anilist)}
    <div class="px-3 py-2">
        <div
            class="group flex gap-3 overflow-hidden rounded-md border border-slate-800 bg-slate-900/60 p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md">
            <div class={`w-1 rounded-md ${accentClass}`}></div>
            <div class="flex min-w-0 flex-1 gap-3">
                {#if coverHref}
                    <!-- eslint-disable svelte/no-navigation-without-resolve -->
                    <a
                        href={coverHref}
                        target="_blank"
                        rel="noopener"
                        class="block h-20 w-14 shrink-0">
                        {#if coverOf(anilist)}
                            <div
                                class="relative h-full w-full overflow-hidden rounded-md border border-slate-800 bg-slate-800/40">
                                <img
                                    src={coverOf(anilist)!}
                                    alt={titleOf(anilist) || "Cover"}
                                    loading="lazy"
                                    class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                                    class:blur-sm={anilist?.isAdult} />
                            </div>
                        {:else}
                            <div
                                class="flex h-full w-full items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                                No Art
                            </div>
                        {/if}
                    </a>
                    <!-- eslint-enable svelte/no-navigation-without-resolve -->
                {:else if coverOf(anilist)}
                    <div
                        class="relative h-20 w-14 shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-800/40">
                        <img
                            src={coverOf(anilist)!}
                            alt={titleOf(anilist) || "Cover"}
                            loading="lazy"
                            class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                            class:blur-sm={anilist?.isAdult} />
                    </div>
                {:else}
                    <div
                        class="flex h-20 w-14 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                        No Art
                    </div>
                {/if}
                <div class="min-w-0 flex-1 space-y-1">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <div class="flex items-center gap-2">
                                <span
                                    class="truncate text-base font-medium"
                                    title={titleOf(anilist)}>{titleOf(anilist)}</span>
                            </div>
                            <div
                                class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                                {#if anilist?.id}
                                    <!-- eslint-disable svelte/no-navigation-without-resolve -->
                                    <a
                                        href={anilistUrlFor(anilist)!}
                                        target="_blank"
                                        rel="noopener"
                                        class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-700/50 px-1 py-0.5 text-[9px] font-semibold text-sky-100 hover:bg-sky-600/60"
                                        title="Open in AniList">
                                        <ExternalLink
                                            class="inline h-3.5 w-3.5 text-[11px]" />
                                        AniList
                                    </a>
                                    <!-- eslint-enable svelte/no-navigation-without-resolve -->
                                {/if}
                                <div
                                    class="hidden flex-wrap gap-1 text-[9px] text-slate-400 sm:flex">
                                    {#if anilist?.format}
                                        <span
                                            class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                            title={anilist.format}
                                            >{anilist.format}</span>
                                    {/if}
                                    {#if anilist?.status}
                                        <span
                                            class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                            title={anilist.status}
                                            >{anilist.status}</span>
                                    {/if}
                                    {#if anilist?.season && anilist?.seasonYear}
                                        <span
                                            class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                            title={`${anilist.season} ${anilist.seasonYear}`}
                                            >{anilist.season}
                                            {anilist.seasonYear}</span>
                                    {/if}
                                    {#if anilist?.episodes}
                                        <span
                                            class="rounded bg-slate-800/70 px-1 py-0.5"
                                            >EP {anilist.episodes}</span>
                                    {/if}
                                    {#if anilist?.isAdult}
                                        <span
                                            class="rounded bg-rose-800 px-1 py-0.5"
                                            title="ADULT content">ADULT</span>
                                    {/if}
                                </div>
                            </div>
                        </div>
                        <div class="flex shrink-0 items-center gap-2"></div>
                    </div>
                    <div class="flex gap-3 pt-1">
                        <button
                            type="button"
                            class={`diff-toggle inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 ${expanded[aid] ? "open" : ""}`}
                            onclick={() => toggleRow(aid)}
                            aria-expanded={expanded[aid] || false}>
                            <span
                                class="relative inline-flex h-4 w-4 items-center justify-center overflow-hidden">
                                {#if expanded[aid]}
                                    <SquareMinus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                {:else}
                                    <SquarePlus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                {/if}
                            </span>
                            <span class="diff-label relative"
                                >{expanded[aid] ? "Hide pins" : "Show pins"}</span>
                            <span
                                class="rounded bg-slate-800/70 px-1 text-[10px] font-semibold text-slate-300"
                                >{sel.length}</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
        {#if expanded[aid]}
            <PinFieldsEditor
                value={sel}
                baseline={base}
                {options}
                loading={optionsLoading}
                saving={savingFlag}
                error={rowErr}
                {disabled}
                title="Pin fields"
                subtitle="Keep these fields unchanged for this entry when syncing."
                {onSave}
                {onChange}
                onRefresh={(force) => onRefresh(force)} />
        {/if}
    </div>
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
                        {@render RowEntry({
                            aid,
                            anilist: p.anilist,
                            sel,
                            base: baselines[aid] ?? base,
                            accentClass: "bg-fuchsia-700/60",
                            options,
                            optionsLoading,
                            savingFlag: saving[aid] || false,
                            rowErr: rowError[aid] || null,
                            disabled: !!optionsError,
                            onSave: (value: string[]) => save(aid, value),
                            onChange: (value: string[]) =>
                                (selections[aid] = [...value]),
                            onRefresh: (force: boolean) => ensureOptions(force),
                        })}
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
                        {@render RowEntry({
                            aid,
                            anilist: r.anilist,
                            sel,
                            base: baselines[aid] ?? base,
                            accentClass: "bg-sky-700/60",
                            options,
                            optionsLoading,
                            savingFlag: saving[aid] || false,
                            rowErr: rowError[aid] || null,
                            disabled: !!optionsError,
                            onSave: (value: string[]) => save(aid, value),
                            onChange: (value: string[]) =>
                                (selections[aid] = [...value]),
                            onRefresh: (force: boolean) => ensureOptions(force),
                        })}
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

<style>
    :global(.diff-toggle) {
        position: relative;
        transition: color 0.25s ease;
    }
    :global(.diff-toggle.open) {
        animation: diffPulse 900ms ease;
    }
    @keyframes diffPulse {
        0% {
            text-shadow: 0 0 0 rgba(56, 189, 248, 0);
        }
        35% {
            text-shadow: 0 0 6px rgba(56, 189, 248, 0.7);
        }
        100% {
            text-shadow: 0 0 0 rgba(56, 189, 248, 0);
        }
    }
    :global(.diff-toggle .diff-icon) {
        transition: transform 220ms ease;
    }
    :global(.diff-toggle.open .diff-icon) {
        transform: rotate(90deg) scale(1.05);
    }
    :global(.diff-toggle:not(.open):hover .diff-icon) {
        transform: rotate(6deg);
    }
    :global(.diff-toggle:disabled) {
        cursor: not-allowed;
        opacity: 0.6;
    }
    @media (prefers-reduced-motion: reduce) {
        :global(.diff-toggle .diff-icon),
        :global(.diff-toggle.open .diff-icon),
        :global(.diff-toggle:not(.open):hover .diff-icon) {
            transition: none;
            transform: none;
        }
        :global(.diff-toggle.open) {
            animation: none;
        }
    }
</style>
