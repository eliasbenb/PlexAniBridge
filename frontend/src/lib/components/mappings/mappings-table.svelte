<script lang="ts">
    import { ExternalLink } from "@lucide/svelte";
    import { Popover, Tooltip } from "bits-ui";

    import type { Mapping, MappingEdge } from "$lib/types/api";
    import { preferredTitle } from "$lib/utils/anilist";
    import type { ColumnConfig } from "./columns";

    export interface Props {
        items: Mapping[];
        columns?: ColumnConfig[];
        onEdit?: (payload: { mapping: Mapping }) => void;
        onDelete?: (payload: { mapping: Mapping }) => void;
        onNavigateToQuery?: (payload: { query: string }) => void;
    }

    let {
        items = $bindable([]),
        columns = $bindable([]),
        onEdit,
        onDelete,
        onNavigateToQuery,
    }: Props = $props();

    if (!columns.length) {
        columns = [];
    }

    let resizing = $state<{
        columnId: string;
        startX: number;
        startWidth: number;
    } | null>(null);

    function startResize(e: MouseEvent, columnId: string) {
        if (!resizing) {
            const column = columns.find((c) => c.id === columnId);
            if (column && column.resizable) {
                resizing = { columnId, startX: e.clientX, startWidth: column.width };
                e.preventDefault();
            }
        }
    }

    function onMouseMove(e: MouseEvent) {
        if (resizing) {
            const diff = e.clientX - resizing.startX;
            const newWidth = Math.max(
                columns.find((c) => c.id === resizing!.columnId)?.minWidth || 60,
                resizing.startWidth + diff,
            );

            columns = columns.map((col) =>
                col.id === resizing!.columnId ? { ...col, width: newWidth } : col,
            );
        }
    }

    function onMouseUp() {
        if (resizing) {
            resizing = null;
        }
    }

    const visibleColumns = $derived(columns.filter((c) => c.visible));

    function navigate(query: string) {
        const text = query.trim();
        if (!text) return;
        onNavigateToQuery?.({ query: text });
    }

    function providerFromColumn(columnId: string): string | null {
        return columnId.startsWith("provider:") ? columnId.slice(9) : null;
    }

    function externalUrl(provider: string, entryId: string, scope?: string) {
        if (!entryId) return null;
        switch (provider) {
            case "anilist":
                return `https://anilist.co/anime/${entryId}`;
            case "anidb":
                return `https://anidb.net/anime/${entryId}`;
            case "imdb":
                return `https://www.imdb.com/title/${entryId}`;
            case "tmdb":
                return scope === "movie"
                    ? `https://www.themoviedb.org/movie/${entryId}`
                    : `https://www.themoviedb.org/tv/${entryId}`;
            case "tvdb":
                return `https://www.thetvdb.com/series/${entryId}`;
            case "mal":
            case "myanimelist":
                return `https://myanimelist.net/anime/${entryId}`;
            default:
                return null;
        }
    }

    function openExternal(url: string | null) {
        if (!url) return;
        window.open(url, "_blank", "noopener,noreferrer");
    }

    function edgeKey(edge: MappingEdge) {
        return `${edge.target_provider}:${edge.target_entry_id}:${edge.target_scope}:${edge.source_range}:${edge.destination_range ?? "all"}`;
    }
</script>

<svelte:window
    onmousemove={onMouseMove}
    onmouseup={onMouseUp} />

<div class="flex-1 overflow-auto">
    <div class="relative min-w-250 sm:min-w-0">
        <table
            class="w-full align-middle text-xs"
            style="table-layout: fixed;">
            <thead
                class="sticky top-0 z-10 bg-linear-to-b from-slate-900/70 to-slate-900/40 text-slate-300">
                <tr class="divide-x divide-slate-800/70 whitespace-nowrap">
                    {#each visibleColumns as column, i (column.id)}
                        <th
                            class="relative px-3 py-2 text-left font-medium"
                            style="width: {column.width}px;">
                            <div class="flex items-center justify-between">
                                <span
                                    class="truncate"
                                    title={column.title}>{column.title}</span>
                            </div>

                            {#if column.resizable && i < visibleColumns.length - 1}
                                <div
                                    class="absolute top-0 right-0 h-full w-1 cursor-col-resize opacity-0 transition-opacity hover:bg-slate-500 hover:opacity-100"
                                    onmousedown={(e) => startResize(e, column.id)}
                                    role="button"
                                    tabindex="-1"
                                    aria-label="Resize column">
                                </div>
                            {/if}
                        </th>
                    {/each}
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/60">
                {#each items as m (m.descriptor)}
                    <tr class="align-top transition-colors hover:bg-slate-800/40">
                        {#each visibleColumns as column (column.id)}
                            <td
                                class="overflow-hidden px-3 py-2"
                                style="width: {column.width}px;">
                                {#if column.id === "title"}
                                    <div class="flex min-w-0 items-start gap-2">
                                        {#if m.anilist}
                                            {@const coverImage =
                                                m.anilist?.coverImage?.medium ??
                                                m.anilist?.coverImage?.large ??
                                                m.anilist?.coverImage?.extraLarge ??
                                                null}
                                            {#if coverImage}
                                                <div
                                                    class="relative h-16 w-12 overflow-hidden rounded-md ring-1 ring-slate-700/60">
                                                    <img
                                                        alt={(preferredTitle(m.anilist?.title) || "Cover") + " cover"}
                                                        loading="lazy"
                                                        src={coverImage}
                                                        class="h-full w-full object-cover"
                                                        class:blur-sm={m.anilist?.isAdult} />
                                                </div>
                                            {:else}
                                                <div
                                                    class="flex h-16 w-12 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                                                    No Art
                                                </div>
                                            {/if}
                                        {:else}
                                            <div
                                                class="flex h-16 w-12 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                                                No Art
                                            </div>
                                        {/if}
                                        <div class="min-w-0 flex-1 space-y-0.5">
                                            <div
                                                class="truncate font-medium text-slate-100"
                                                title={preferredTitle(m.anilist?.title) || m.descriptor}>
                                                {#if m?.anilist?.title}{preferredTitle(m.anilist.title)}{:else}{m.descriptor}{/if}
                                            </div>
                                            {#if m.anilist && (m.anilist.format || m.anilist.status || m.anilist.episodes)}
                                                <div class="flex flex-wrap gap-1 overflow-hidden text-[9px] text-slate-400">
                                                    {#if m.custom}
                                                        <span
                                                            class="truncate rounded bg-amber-600/30 px-1 py-0.5 tracking-wide text-amber-100 uppercase"
                                                            title="Custom Mapping"
                                                            >Custom</span>
                                                    {/if}
                                                    {#if m.anilist.format}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={m.anilist.format}
                                                            >{m.anilist.format}</span>
                                                        {/if}
                                                    {#if m.anilist.status}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={m.anilist.status}
                                                            >{m.anilist.status}</span>
                                                        {/if}
                                                    {#if m.anilist.season && m.anilist.seasonYear}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={`${m.anilist.season} ${m.anilist.seasonYear}`}
                                                            >{m.anilist.season} {m.anilist.seasonYear}</span>
                                                        {/if}
                                                    {#if m.anilist.episodes}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5"
                                                            title={`${m.anilist.episodes} episodes`}
                                                            >EP {m.anilist.episodes}</span>
                                                        {/if}
                                                    {#if m.anilist?.isAdult}
                                                        <span
                                                            class="rounded bg-rose-800 px-1 py-0.5"
                                                            title="Adult content"
                                                            >ADULT</span>
                                                    {/if}
                                                </div>
                                            {:else if m.custom}
                                                <span class="rounded bg-amber-600/30 px-1 py-0.5 text-[10px] uppercase text-amber-100">Custom</span>
                                            {/if}
                                        </div>
                                    </div>
                                {:else if column.id === "descriptor"}
                                    <div class="space-y-1">
                                        <div class="flex items-center gap-2 text-sm font-semibold text-slate-100">
                                            <span class="truncate" title={m.descriptor}>{m.descriptor}</span>
                                            {#if m.custom}
                                                <span class="rounded bg-amber-600/30 px-1.5 py-0.5 text-[10px] uppercase text-amber-100 ring-1 ring-amber-700/50"
                                                    >Custom</span>
                                            {/if}
                                        </div>
                                        {#if m.anilist?.title}
                                            <div class="truncate text-[11px] text-slate-400" title={preferredTitle(m.anilist?.title) || ""}>
                                                {preferredTitle(m.anilist?.title) || ""}
                                            </div>
                                        {/if}
                                    </div>
                                {:else if column.id === "provider"}
                                    <div class="space-y-1 font-mono text-[11px]">
                                        <div class="flex items-center gap-2">
                                            <span class="rounded bg-slate-800 px-1.5 py-0.5 text-slate-100 uppercase">{m.provider}</span>
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <div class="flex shrink-0 items-center gap-1">
                                                        <button
                                                            class="cursor-pointer rounded px-0.5 text-left text-emerald-300 select-text hover:underline focus:outline-none"
                                                            type="button"
                                                            title={`Filter by ${m.provider} ${m.entry_id}`}
                                                            onclick={() => navigate(`provider:${m.provider} entry_id:${m.entry_id}`)}>{m.entry_id}</button>
                                                        {#if externalUrl(m.provider, m.entry_id, m.scope)}
                                                            <button
                                                                type="button"
                                                                class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                aria-label={`Open ${m.provider} ${m.entry_id}`}
                                                                onclick={() => openExternal(externalUrl(m.provider, m.entry_id, m.scope))}>
                                                                <ExternalLink class="h-3 w-3" />
                                                            </button>
                                                        {/if}
                                                        <span class="rounded bg-slate-700/70 px-1 py-0.5 text-[10px] uppercase text-slate-200">{m.scope}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                {:else if providerFromColumn(column.id)}
                                    {@const provider = providerFromColumn(column.id)!}
                                    {@const edges = m.edges.filter((e) => e.target_provider === provider)}
                                    {#if m.provider === provider}
                                        <div class="flex items-center gap-1 font-mono text-[11px]">
                                            <span class="rounded bg-emerald-700/30 px-1 py-0.5 text-emerald-100">source</span>
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <div class="flex shrink-0 items-center gap-1">
                                                        <button
                                                            class="cursor-pointer rounded px-0.5 text-left text-emerald-300 select-text hover:underline focus:outline-none"
                                                            type="button"
                                                            title={`Filter by ${provider} ${m.entry_id}`}
                                                            onclick={() => navigate(`provider:${provider} entry_id:${m.entry_id}`)}>{m.entry_id}</button>
                                                        {#if externalUrl(provider, m.entry_id, m.scope)}
                                                            <button
                                                                type="button"
                                                                class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                aria-label={`Open ${provider} ${m.entry_id}`}
                                                                onclick={() => openExternal(externalUrl(provider, m.entry_id, m.scope))}>
                                                                <ExternalLink class="h-3 w-3" />
                                                            </button>
                                                        {/if}
                                                        <span class="rounded bg-slate-800 px-1 py-0.5 text-[10px] uppercase text-slate-200">{m.scope}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    {:else if edges.length}
                                        <div class="scroll-wrapper">
                                            <div class="scroll-row" title={`Targets mapped from ${provider}`}>
                                                {#each edges as edge (edgeKey(edge))}
                                                    <div class="flex items-center gap-1">
                                                        <span class="rounded bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-200 ring-1 ring-slate-700/50">{edge.source_range}→{edge.destination_range ?? "all"}</span>
                                                        <div class="flex shrink-0 items-center gap-1">
                                                            <button
                                                                class="cursor-pointer rounded px-0.5 text-left text-emerald-300 select-text hover:underline focus:outline-none"
                                                                type="button"
                                                                title={`Filter by ${edge.target_provider} ${edge.target_entry_id}`}
                                                                onclick={() => navigate(`provider:${edge.target_provider} entry_id:${edge.target_entry_id}`)}>{edge.target_entry_id}</button>
                                                            {#if externalUrl(edge.target_provider, edge.target_entry_id, edge.target_scope)}
                                                                <button
                                                                    type="button"
                                                                    class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                    aria-label={`Open ${edge.target_provider} ${edge.target_entry_id}`}
                                                                    onclick={() => openExternal(externalUrl(edge.target_provider, edge.target_entry_id, edge.target_scope))}>
                                                                    <ExternalLink class="h-3 w-3" />
                                                                </button>
                                                            {/if}
                                                            <span class="rounded bg-slate-800 px-1 py-0.5 text-[10px] uppercase text-slate-200">{edge.target_scope}</span>
                                                        </div>
                                                    </div>
                                                {/each}
                                            </div>
                                        </div>
                                    {:else}
                                        <span class="text-[10px] text-slate-500">-</span>
                                    {/if}
                                {:else if column.id === "sources"}
                                    {#key (m.sources ?? []).join("|") + ":" + String(m.custom)}
                                        {@const total = (m.sources ?? []).length}
                                        <div class="flex justify-center">
                                            {#if total > 0}
                                                <Tooltip.Root>
                                                    <Tooltip.Trigger>
                                                        <span
                                                            class={`inline-flex h-5 min-w-5 items-center justify-center rounded px-1.5 text-[10px] ring-1 ${total > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                                            >{total}</span>
                                                    </Tooltip.Trigger>
                                                    <Tooltip.Portal>
                                                        <Tooltip.Content
                                                            collisionPadding={12}
                                                            side="bottom"
                                                            sideOffset={6}
                                                            class="max-h-27 max-w-[90vw] overflow-auto rounded-md border border-slate-700 bg-slate-900 p-2 text-left text-[11px] shadow-lg">
                                                            <ol class="space-y-1">
                                                                {#each m.sources ?? [] as s, i (i)}
                                                                    <li
                                                                        class="flex items-start gap-1 wrap-break-word">
                                                                        <span
                                                                            class="text-slate-500"
                                                                            >{i + 1}.</span>
                                                                        <span
                                                                            class="text-slate-300"
                                                                            title={s}
                                                                            >{s}</span>
                                                                    </li>
                                                                {/each}
                                                            </ol>
                                                        </Tooltip.Content>
                                                    </Tooltip.Portal>
                                                </Tooltip.Root>
                                            {:else}
                                                <span class="text-[10px] text-slate-500"
                                                    >-</span>
                                            {/if}
                                        </div>
                                    {/key}
                                {:else if column.id === "actions"}
                                    <div
                                        class="flex justify-end gap-1 whitespace-nowrap">
                                        <button
                                            class="inline-flex h-6 items-center rounded-md bg-slate-800 px-2 text-[11px] text-slate-200 hover:bg-slate-700"
                                            onclick={() => onEdit?.({ mapping: m })}
                                            >Edit</button>
                                        <Popover.Root>
                                            <Popover.Trigger
                                                class="inline-flex h-6 items-center rounded-md bg-rose-700/70 px-2 text-[11px] text-rose-200 hover:bg-rose-600"
                                                aria-label="Delete mapping"
                                                title="Delete mapping">
                                                Del
                                            </Popover.Trigger>
                                            <Popover.Content
                                                align="end"
                                                side="top"
                                                sideOffset={6}
                                                class="z-50 w-44 rounded-md border border-rose-800/60 bg-slate-950/95 p-2 text-left text-[11px] shadow-lg">
                                                <div class="space-y-1">
                                                    <Popover.Close
                                                        class="flex w-full items-center justify-start rounded px-2 py-1 text-left text-[11px] text-rose-100 hover:bg-rose-900/60"
                                                        onclick={() => onDelete?.({ mapping: m })}
                                                        >Remove override</Popover.Close>
                                                </div>
                                            </Popover.Content>
                                        </Popover.Root>
                                    </div>
                                {/if}
                            </td>
                        {/each}
                    </tr>
                {/each}
                {#if !items.length}
                    <tr>
                        <td
                            colspan={visibleColumns.length}
                            class="py-8 text-center text-slate-500"
                            >No mappings found</td>
                    </tr>
                {/if}
            </tbody>
        </table>
    </div>
</div>

<style>
    .scroll-wrapper {
        position: relative;
    }

    .scroll-wrapper:hover::after,
    .scroll-wrapper:focus-within::after {
        opacity: 0.85;
    }

    .scroll-row {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        overflow-x: auto;
        white-space: nowrap;
        padding-bottom: 0.35rem;
        padding-right: 0.75rem;
        scrollbar-width: thin;
        scrollbar-gutter: stable both-edges;
    }

    .scroll-row::-webkit-scrollbar {
        height: 6px;
    }

    .scroll-row::-webkit-scrollbar-track {
        background: rgba(71, 85, 105, 0.35);
        border-radius: 9999px;
    }

    .scroll-row::-webkit-scrollbar-thumb {
        background: rgba(16, 185, 129, 0.45);
        border-radius: 9999px;
    }

    .scroll-row:hover::-webkit-scrollbar-thumb {
        background: rgba(16, 185, 129, 0.8);
    }
</style>
