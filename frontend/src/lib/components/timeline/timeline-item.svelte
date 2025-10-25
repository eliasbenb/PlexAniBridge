<script lang="ts">
    import {
        ExternalLink,
        LoaderCircle,
        RefreshCcw,
        RotateCw,
        SquareMinus,
        SquarePlus,
        Trash2,
    } from "@lucide/svelte";
    import { fade } from "svelte/transition";

    import TimelineDiffViewer from "$lib/components/timeline/timeline-diff-viewer.svelte";
    import TimelineManagePins from "$lib/components/timeline/timeline-manage-pins.svelte";
    import type { ItemDiffUi, OutcomeMeta } from "$lib/components/timeline/types";
    import type { HistoryItem } from "$lib/types/api";

    interface Props {
        item: HistoryItem;
        meta: OutcomeMeta;
        displayTitle: (item: HistoryItem) => string | null;
        coverImage: (item: HistoryItem) => string | null;
        anilistUrl: (item: HistoryItem) => string | null;
        plexUrl: (item: HistoryItem) => string | null;
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
        diffCount?: number;
        hasPins?: boolean;
        togglePins?: (item: HistoryItem) => void;
        openPins?: boolean;
        pinButtonLoading?: boolean;
        pinCount?: number;
        profile: string;
        onPinsDraft?: (item: HistoryItem, fields: string[]) => void;
        onPinsSaved?: (item: HistoryItem, fields: string[]) => void;
        onPinsBusy?: (item: HistoryItem, value: boolean) => void;
    }

    let {
        item,
        meta,
        displayTitle,
        coverImage,
        anilistUrl,
        plexUrl,
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
        diffCount,
        hasPins = false,
        togglePins,
        openPins = false,
        pinButtonLoading = false,
        pinCount,
        profile,
        onPinsDraft,
        onPinsSaved,
        onPinsBusy,
    }: Props = $props();

    const coverHref = anilistUrl(item);

    const ui = () => ensureDiffUi(item.id);
</script>

<div
    class="group flex gap-3 overflow-hidden rounded-md border border-slate-800 bg-slate-900/60 p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md">
    <div class={`w-1 rounded-md ${meta.color}`}></div>
    <div class="flex min-w-0 flex-1 gap-3">
        {#if coverHref}
            <!-- eslint-disable svelte/no-navigation-without-resolve -->
            <a
                href={coverHref}
                target="_blank"
                rel="noopener"
                class="block h-20 w-14 shrink-0">
                {#if coverImage(item)}
                    <div
                        class="relative h-full w-full overflow-hidden rounded-md border border-slate-800 bg-slate-800/40">
                        <img
                            src={coverImage(item)!}
                            alt={displayTitle(item) || "Cover"}
                            loading="lazy"
                            class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                            class:blur-sm={item.anilist?.isAdult} />
                    </div>
                {:else}
                    <div
                        class="flex h-full w-full items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                        No Art
                    </div>
                {/if}
            </a>
            <!-- eslint-enable svelte/no-navigation-without-resolve -->
        {:else if coverImage(item)}
            <div
                class="relative h-20 w-14 shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-800/40">
                <img
                    src={coverImage(item)!}
                    alt={displayTitle(item) || "Cover"}
                    loading="lazy"
                    class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                    class:blur-sm={item.anilist?.isAdult} />
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
                            {#if item.anilist?.season && item.anilist?.seasonYear}
                                <span
                                    class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase">
                                    {item.anilist.season}
                                    {item.anilist.seasonYear}
                                </span>
                            {/if}
                            {#if item.anilist?.episodes}
                                <span class="rounded bg-slate-800/70 px-1 py-0.5"
                                    >EP {item.anilist.episodes}</span>
                            {/if}
                            {#if item.anilist?.isAdult}
                                <span
                                    class="rounded bg-rose-800 px-1 py-0.5"
                                    title="ADULT content">ADULT</span>
                            {/if}
                        </div>
                    </div>
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
            <div class="flex gap-3 pt-1">
                {#if canShowDiff(item)}
                    <button
                        type="button"
                        onclick={() => toggleDiff(item.id)}
                        class={`diff-toggle inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 ${openDiff ? "open" : ""}`}
                        aria-expanded={openDiff}>
                        <span
                            class="relative inline-flex h-4 w-4 items-center justify-center overflow-hidden">
                            {#if openDiff}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquareMinus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {:else}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquarePlus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {/if}
                        </span>
                        <span class="diff-label relative"
                            >{openDiff ? "Hide diff" : "Show diff"}</span>
                        {#if diffCount !== undefined}
                            <span
                                class="rounded bg-slate-800/70 px-1 text-[10px] font-semibold text-slate-300">
                                {diffCount}
                            </span>
                        {/if}
                    </button>
                {/if}
                {#if hasPins && togglePins}
                    <button
                        type="button"
                        class={`diff-toggle inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 ${
                            openPins ? "open" : ""
                        }`}
                        onclick={() => togglePins(item)}
                        aria-expanded={openPins}
                        aria-pressed={openPins}
                        aria-busy={pinButtonLoading}
                        disabled={pinButtonLoading}>
                        <span
                            class="relative inline-flex h-4 w-4 items-center justify-center overflow-hidden">
                            {#if openPins}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquareMinus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {:else}
                                <span
                                    in:fade={{ duration: 140 }}
                                    out:fade={{ duration: 90 }}
                                    class="absolute inset-0 flex items-center justify-center">
                                    <SquarePlus
                                        class="diff-icon inline h-4 w-4 text-[14px]" />
                                </span>
                            {/if}
                            {#if pinButtonLoading}
                                <span
                                    class="absolute inset-0 flex items-center justify-center rounded-full bg-slate-950/70"
                                    in:fade={{ duration: 100 }}
                                    out:fade={{ duration: 100 }}>
                                    <LoaderCircle
                                        class="inline h-3.5 w-3.5 animate-spin text-sky-300" />
                                </span>
                            {/if}
                        </span>
                        <span class="diff-label relative"
                            >{openPins ? "Hide pins" : "Show pins"}</span>
                        {#if pinCount !== undefined}
                            <span
                                class="rounded bg-slate-800/70 px-1 text-[10px] font-semibold text-slate-300">
                                {pinCount}
                            </span>
                        {/if}
                    </button>
                {/if}
            </div>
        </div>
    </div>
</div>
{#if openDiff && canShowDiff(item)}
    <TimelineDiffViewer
        {item}
        ui={ui()} />
{/if}
{#if openPins && hasPins}
    <TimelineManagePins
        {profile}
        {item}
        on:draft={(event) =>
            onPinsDraft?.(
                item,
                (event as CustomEvent<{ fields: string[] }>).detail.fields,
            )}
        on:saved={(event) =>
            onPinsSaved?.(
                item,
                (event as CustomEvent<{ fields: string[] }>).detail.fields,
            )}
        on:busy={(event) =>
            onPinsBusy?.(
                item,
                (event as CustomEvent<{ value: boolean }>).detail.value,
            )} />
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
