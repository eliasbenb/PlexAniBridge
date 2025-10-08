<script lang="ts">
    import {
        Check,
        ExternalLink,
        LoaderCircle,
        Pin,
        PinOff,
        RefreshCcw,
        RotateCw,
        SquareMinus,
        SquarePlus,
        Trash2,
    } from "@lucide/svelte";
    import { fade } from "svelte/transition";

    import TimelineDiffViewer from "$lib/components/timeline/timeline-diff-viewer.svelte";
    import type { ItemDiffUi, OutcomeMeta } from "$lib/components/timeline/types";
    import type { HistoryItem, PinFieldOption } from "$lib/types/api";

    interface Props {
        item: HistoryItem;
        meta: OutcomeMeta;
        displayTitle: (item: HistoryItem) => string | null;
        coverImage: (item: HistoryItem) => string | null;
        anilistUrl: (item: HistoryItem) => string | null;
        plexUrl: (item: HistoryItem) => string | null;
        pinFieldLabel: (field: string) => string;
        ensurePinSelection: (anilistId: number) => Set<string>;
        togglePinField: (anilistId: number, field: string) => void;
        isPinDirty: (anilistId: number) => boolean;
        isPinSaving: (anilistId: number) => boolean;
        savePins: (anilistId: number) => void;
        resetPins: (anilistId: number) => void;
        clearPins: (anilistId: number) => void;
        togglePinEditor: (key: string, anilistId: number | null | undefined) => void;
        editorIsOpen: (key: string) => boolean;
        pinOptions?: PinFieldOption[];
        currentPins?: string[];
        canRetry: (item: HistoryItem) => boolean;
        retryHistory: (item: HistoryItem) => void;
        retryLoading?: boolean;
        isProfileRunning?: boolean;
        canUndo: (item: HistoryItem) => boolean;
        undoHistory: (item: HistoryItem) => void;
        undoLoading?: boolean;
        deleteHistory: (item: HistoryItem) => void;
        canShowDiff: (item: HistoryItem) => boolean;
        toggleDiff: (id: number) => void;
        openDiff?: boolean;
        ensureDiffUi: (id: number) => ItemDiffUi;
    }

    let {
        item,
        meta,
        displayTitle,
        coverImage,
        anilistUrl,
        plexUrl,
        pinFieldLabel,
        ensurePinSelection,
        togglePinField,
        isPinDirty,
        isPinSaving,
        savePins,
        resetPins,
        clearPins,
        togglePinEditor,
        editorIsOpen,
        pinOptions = [],
        currentPins = [],
        canRetry,
        retryHistory,
        retryLoading = false,
        isProfileRunning = false,
        canUndo,
        undoHistory,
        undoLoading = false,
        deleteHistory,
        canShowDiff,
        toggleDiff,
        openDiff = false,
        ensureDiffUi,
    }: Props = $props();

    const pinEditorKey = () => `timeline-${item.id}`;
    const isPinEditorOpen = () => editorIsOpen(pinEditorKey());
    const ui = () => ensureDiffUi(item.id);
    const selection = () => ensurePinSelection(item.anilist_id ?? 0);
</script>

<div
    class="flex gap-3 overflow-hidden rounded-md border border-slate-800 bg-slate-900/60 p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md">
    <div class={`w-1 rounded-md ${meta.color}`}></div>
    <div class="flex min-w-0 flex-1 gap-3">
        {#if coverImage(item)}
            <div
                class="relative h-20 w-14 shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-800/40">
                <img
                    src={coverImage(item)!}
                    alt={displayTitle(item) || "Cover"}
                    loading="lazy"
                    class="h-full w-full object-cover" />
            </div>
        {:else}
            <div
                class="flex h-20 w-14 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500">
                No Art
            </div>
        {/if}
        <div class="min-w-0 flex-1 space-y-1">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                    <div class="flex items-center gap-2">
                        <span
                            class="truncate font-medium"
                            title={displayTitle(item)}>
                            {displayTitle(item)}
                        </span>
                        <span
                            class={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${meta.color}`}>
                            <meta.icon class="inline h-3.5 w-3.5 text-[10px]" />
                            {meta.label}
                        </span>
                    </div>
                    <div
                        class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        {#if item.anilist?.id}
                            <!-- eslint-disable svelte/no-navigation-without-resolve -->
                            <a
                                href={anilistUrl(item)!}
                                target="_blank"
                                rel="noopener"
                                class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-700/50 px-1 py-0.5 text-[9px] font-semibold text-sky-100 hover:bg-sky-600/60"
                                title="Open in AniList">
                                <ExternalLink class="inline h-3.5 w-3.5 text-[11px]" />
                                AniList
                            </a>
                            <!-- eslint-enable svelte/no-navigation-without-resolve -->
                        {/if}

                        {#if item.plex_guid}
                            <!-- eslint-disable svelte/no-navigation-without-resolve -->
                            <a
                                href={plexUrl(item)!}
                                target="_blank"
                                rel="noopener"
                                class="inline-flex items-center gap-1 rounded-md border border-amber-600 bg-amber-700/60 px-1.5 py-0.5 text-[10px] text-amber-100 transition-colors hover:bg-amber-600/60"
                                title="Open in Plex">
                                <ExternalLink class="inline h-3.5 w-3.5 text-[11px]" />
                                Plex
                            </a>
                            <!-- eslint-enable svelte/no-navigation-without-resolve -->
                        {/if}
                        <span class="text-xs text-slate-400">
                            {new Date(item.timestamp + "Z").toLocaleString()}
                        </span>
                        <div
                            class="hidden flex-wrap gap-1 text-[9px] text-slate-400 sm:flex">
                            {#if item.anilist?.format}
                                <span
                                    class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase">
                                    {item.anilist.format}
                                </span>
                            {/if}
                            {#if item.anilist?.status}
                                <span
                                    class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase">
                                    {item.anilist.status}
                                </span>
                            {/if}
                            {#if item.anilist?.episodes}
                                <span class="rounded bg-slate-800/70 px-1 py-0.5"
                                    >EP {item.anilist.episodes}</span>
                            {/if}
                        </div>
                    </div>
                    {#if currentPins.length}
                        <div
                            class="mt-3 rounded-lg border border-sky-900/50 bg-sky-950/40 p-3 text-[11px] text-sky-100">
                            <div class="flex flex-wrap items-center gap-2">
                                <span
                                    class="inline-flex items-center gap-1 rounded-full bg-sky-900/70 px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase">
                                    <Pin class="h-3.5 w-3.5 text-sky-300" />
                                    {currentPins.length}
                                    {currentPins.length === 1 ? " field" : " fields"}
                                    pinned
                                </span>
                                <span class="text-[10px] text-slate-400">
                                    Pinned fields stay synced for this entry.
                                </span>
                            </div>
                            <div class="mt-2 flex flex-wrap gap-1.5">
                                {#each currentPins as field (field)}
                                    <span
                                        class="inline-flex items-center gap-1 rounded-md border border-sky-800/70 bg-sky-900/40 px-2 py-0.5 text-[10px] text-sky-100">
                                        {pinFieldLabel(field)}
                                    </span>
                                {/each}
                            </div>
                        </div>
                    {/if}
                </div>
                <div class="flex shrink-0 items-center gap-2">
                    {#if canRetry(item)}
                        <button
                            type="button"
                            disabled={retryLoading || isProfileRunning}
                            onclick={() => retryHistory(item)}
                            class="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-700/40 px-2 text-[11px] font-medium text-emerald-100 hover:bg-emerald-600/50 disabled:opacity-50"
                            title="Retry sync for this item">
                            {#if retryLoading}
                                <LoaderCircle class="inline h-4 w-4 animate-spin" />
                            {:else}
                                <RefreshCcw class="inline h-4 w-4" />
                            {/if}
                        </button>
                    {/if}
                    {#if canUndo(item)}
                        <button
                            type="button"
                            disabled={undoLoading}
                            onclick={() => undoHistory(item)}
                            class="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-violet-600/60 bg-violet-700/40 px-2 text-[11px] font-medium text-violet-100 hover:bg-violet-600/50 disabled:opacity-50"
                            title="Undo this change">
                            {#if undoLoading}
                                <LoaderCircle class="inline h-4 w-4 animate-spin" />
                            {:else}
                                <RotateCw class="inline h-4 w-4" />
                            {/if}
                        </button>
                    {/if}
                    <button
                        type="button"
                        onclick={() => deleteHistory(item)}
                        class="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-red-600/60 bg-red-700/40 px-2 text-[11px] font-medium text-red-100 hover:bg-red-600/50"
                        title="Delete history entry">
                        <Trash2 class="inline h-4 w-4" />
                    </button>
                </div>
            </div>
            {#if item.error_message}
                <div class="text-[11px] text-red-400">{item.error_message}</div>
            {/if}
            <div class="flex flex-wrap items-center gap-3 pt-1">
                {#if canShowDiff(item)}
                    <button
                        type="button"
                        onclick={() => toggleDiff(item.id)}
                        class={`expand-toggle inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 ${openDiff ? "open" : ""}`}
                        aria-expanded={openDiff}>
                        <span
                            class="relative inline-flex h-4 w-4 items-center justify-center overflow-hidden">
                            {#if openDiff}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquareMinus
                                        class="expand-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {:else}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquarePlus
                                        class="expand-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {/if}
                        </span>
                        <span class="relative"
                            >{openDiff ? "Hide diff" : "Show diff"}</span>
                    </button>
                {/if}
                <button
                    type="button"
                    disabled={!item.anilist_id}
                    onclick={() => togglePinEditor(pinEditorKey(), item.anilist_id)}
                    class={`expand-toggle inline-flex items-center gap-1 text-xs text-sky-400 transition hover:text-sky-300 disabled:cursor-not-allowed disabled:text-slate-500 ${isPinEditorOpen() ? "open" : ""}`}
                    aria-expanded={isPinEditorOpen()}
                    title={item.anilist_id
                        ? "Pin AniList fields for this entry"
                        : "Pinning requires an AniList mapping"}>
                    <span
                        class="relative inline-flex h-4 w-4 items-center justify-center overflow-hidden">
                        {#if isPinEditorOpen()}
                            <span
                                in:fade={{ duration: 140 }}
                                out:fade={{ duration: 90 }}
                                class="absolute inset-0 flex items-center justify-center">
                                <SquareMinus
                                    class="expand-icon inline h-4 w-4 text-[14px]" />
                            </span>
                        {:else}
                            <span
                                in:fade={{ duration: 140 }}
                                out:fade={{ duration: 90 }}
                                class="absolute inset-0 flex items-center justify-center">
                                <SquarePlus
                                    class="expand-icon inline h-4 w-4 text-[14px]" />
                            </span>
                        {/if}
                    </span>
                    <span class="relative">
                        {isPinEditorOpen() ? "Hide pins" : "Show pins"}
                    </span>
                    {#if currentPins.length}
                        <span
                            class="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-sky-900/70 px-1.5 py-0.5 text-[10px] font-semibold text-sky-100">
                            {currentPins.length}
                        </span>
                    {/if}
                </button>
            </div>
        </div>
    </div>
</div>
{#if openDiff && canShowDiff(item)}
    <TimelineDiffViewer
        {item}
        ui={ui()} />
{/if}

{#if isPinEditorOpen() && item.anilist_id}
    {@const selectedFields = selection()}
    <section
        in:fade={{ duration: 140 }}
        class="mt-3 space-y-4 rounded-xl border border-slate-800/80 bg-slate-950/50 p-4 text-[11px] text-slate-200 shadow-[0_15px_40px_-20px_rgba(15,23,42,0.75)]">
        <header class="flex flex-wrap items-start justify-between gap-3">
            <div>
                <div
                    class="inline-flex items-center gap-2 text-[12px] font-semibold text-slate-100">
                    <Pin class="h-4 w-4 text-sky-300" /> Pin AniList fields
                </div>
                <p class="mt-1 max-w-prose text-[11px] text-slate-400">
                    Choose which AniList attributes should stay pinned to Plex for this
                    title.
                </p>
            </div>
            <div class="flex flex-col items-end gap-1 text-right text-[10px]">
                <span
                    class="inline-flex items-center gap-1 rounded-full border border-sky-700/60 bg-sky-900/40 px-2 py-0.5 font-medium text-sky-100">
                    <Pin class="h-3 w-3 text-sky-300" />
                    {selectedFields.size}
                    {selectedFields.size === 1 ? "field" : "fields"}
                    selected
                </span>
                {#if currentPins.length === 0}
                    <span class="text-[10px] text-slate-500">No pins saved yet.</span>
                {/if}
            </div>
        </header>
        {#if pinOptions.length}
            <div
                class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-7">
                {#each pinOptions as option (option.value)}
                    {@const isActive = selectedFields.has(option.value)}
                    <label
                        class={`group relative inline-flex overflow-hidden rounded-lg border px-3 py-2 text-left transition focus-within:ring-2 focus-within:ring-sky-500/70 ${isActive ? "border-sky-600/70 bg-sky-900/50 text-sky-100 shadow-[0_0_0_1px_rgba(56,189,248,0.2)]" : "border-slate-700/70 bg-slate-900/60 text-slate-300 hover:border-slate-600/80 hover:bg-slate-900/70"}`}
                        ><input
                            type="checkbox"
                            class="sr-only"
                            checked={isActive}
                            onchange={() =>
                                togglePinField(item.anilist_id!, option.value)} />
                        <div class="flex w-full items-center gap-2">
                            <span
                                class={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] transition ${isActive ? "border-transparent bg-sky-600/80 text-slate-950" : "border-slate-600/80 text-slate-500 group-hover:border-slate-500"}`}>
                                {#if isActive}
                                    <Check class="h-3.5 w-3.5" />
                                {:else}
                                    <Pin class="h-3.5 w-3.5" />
                                {/if}
                            </span>
                            <span class="block text-[11px] font-medium tracking-wide">
                                {option.label}
                            </span>
                        </div>
                    </label>
                {/each}
            </div>
        {:else}
            <div
                class="rounded-md border border-slate-800/70 bg-slate-900/60 p-3 text-slate-400">
                Pin options unavailable. Try refreshing.
            </div>
        {/if}
        <footer
            class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800/70 bg-slate-900/40 p-3">
            <div class="flex items-center gap-2 text-[10px] text-slate-400">
                {#if isPinSaving(item.anilist_id!)}
                    <LoaderCircle class="h-3.5 w-3.5 animate-spin text-sky-300" />
                    Saving changes…
                {:else if isPinDirty(item.anilist_id!)}
                    <span
                        class="inline-flex items-center gap-1 rounded-full bg-amber-900/40 px-2 py-0.5 text-amber-200">
                        <span class="h-1.5 w-1.5 rounded-full bg-amber-400"></span>
                        Unsaved changes
                    </span>
                {:else}
                    <span
                        class="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 px-2 py-0.5 text-emerald-200">
                        <span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                        All changes saved
                    </span>
                {/if}
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-sky-500/70 bg-sky-600/70 px-3 py-1 text-[11px] font-semibold text-sky-50 shadow-sm transition hover:bg-sky-500/70 disabled:opacity-50"
                    disabled={!isPinDirty(item.anilist_id!) ||
                        isPinSaving(item.anilist_id!)}
                    onclick={() => savePins(item.anilist_id!)}>
                    {#if isPinSaving(item.anilist_id!)}
                        <LoaderCircle class="h-3.5 w-3.5 animate-spin" />
                        Saving…
                    {:else}
                        Save pins
                    {/if}
                </button>
                <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-slate-700/70 px-3 py-1 text-[11px] text-slate-200 transition hover:bg-slate-800/60"
                    onclick={() => resetPins(item.anilist_id!)}>
                    Reset
                </button>
                <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-rose-700/70 px-3 py-1 text-[11px] text-rose-200 transition hover:bg-rose-700/60"
                    onclick={() => clearPins(item.anilist_id!)}>
                    <PinOff class="h-3.5 w-3.5" /> Clear all
                </button>
            </div>
        </footer>
    </section>
{/if}

<style>
    :global(.expand-toggle) {
        position: relative;
        transition: color 0.25s ease;
    }
    :global(.expand-toggle.open) {
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
    :global(.expand-toggle) {
        position: relative;
        transition: color 0.25s ease;
    }
    :global(.expand-toggle.open) {
        animation: diffPulse 900ms ease;
    }
    :global(.expand-toggle .expand-icon) {
        transition: transform 220ms ease;
    }
    :global(.expand-toggle.open .expand-icon) {
        transform: rotate(90deg) scale(1.05);
    }
    :global(.expand-toggle:not(.open):hover .expand-icon) {
        transform: rotate(6deg);
    }
    @media (prefers-reduced-motion: reduce) {
        :global(.expand-toggle .expand-icon),
        :global(.expand-toggle.open .expand-icon),
        :global(.expand-toggle:not(.open):hover .expand-icon) {
            transition: none;
            transform: none;
        }
        :global(.expand-toggle.open) {
            animation: none;
        }
    }
</style>
