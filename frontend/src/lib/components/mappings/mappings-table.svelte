<script lang="ts">
    import { ExternalLink } from "@lucide/svelte";
    import { Popover, Tooltip } from "bits-ui";

    import type { Mapping } from "$lib/types/api";
    import { preferredTitle } from "$lib/utils/anilist";
    import type { ColumnConfig } from "./columns";
    import { defaultColumns } from "./columns";

    export interface Props {
        items: Mapping[];
        columns?: ColumnConfig[];
        onEdit?: (payload: { mapping: Mapping }) => void;
        onDelete?: (payload: { mapping: Mapping; kind: "custom" | "full" }) => void;
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
        columns = [...defaultColumns];
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

    function navigate(prefix: string, value: string | number | null | undefined) {
        if (value === null || value === undefined) return;
        const text = String(value).trim();
        if (!text) return;
        onNavigateToQuery?.({ query: `${prefix}:${text}` });
    }
</script>

<svelte:window
    onmousemove={onMouseMove}
    onmouseup={onMouseUp} />

<div class="flex-1 overflow-auto">
    <div class="relative min-w-[1000px] sm:min-w-0">
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

                            <!-- Resize handle -->
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
                {#each items as m (m.anilist_id)}
                    {@const coverImage =
                        m.anilist?.coverImage?.medium ??
                        m.anilist?.coverImage?.large ??
                        m.anilist?.coverImage?.extraLarge ??
                        null}
                    <tr class="align-top transition-colors hover:bg-slate-800/40">
                        {#each visibleColumns as column (column.id)}
                            <td
                                class="overflow-hidden px-3 py-2"
                                style="width: {column.width}px;">
                                {#if column.id === "title"}
                                    <div class="flex min-w-0 items-start gap-2">
                                        <a
                                            href={`https://anilist.co/anime/${m.anilist_id}`}
                                            rel="noopener noreferrer"
                                            target="_blank"
                                            class="group block w-12 shrink-0">
                                            {#if coverImage}
                                                <div
                                                    class="relative h-16 w-full overflow-hidden rounded-md ring-1 ring-slate-700/60">
                                                    <img
                                                        alt={(preferredTitle(
                                                            m.anilist?.title,
                                                        ) || "Cover") + " cover"}
                                                        loading="lazy"
                                                        src={coverImage}
                                                        class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                                                        class:blur-sm={m.anilist
                                                            ?.isAdult} />
                                                </div>
                                            {:else}
                                                <div
                                                    class="flex h-16 w-12 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                                                    No Art
                                                </div>
                                            {/if}
                                        </a>
                                        <div class="min-w-0 flex-1 space-y-0.5">
                                            <div
                                                class="truncate font-medium"
                                                title={preferredTitle(
                                                    m.anilist?.title,
                                                ) || `AniList ${m.anilist_id}`}>
                                                {#if m?.anilist?.title}{preferredTitle(
                                                        m.anilist.title,
                                                    )}{:else}AniList {m.anilist_id}{/if}
                                            </div>
                                            {#if m.anilist && (m.anilist.format || m.anilist.status || m.anilist.episodes)}
                                                <div
                                                    class="flex flex-wrap gap-1 overflow-hidden text-[9px] text-slate-400">
                                                    {#if m.custom}
                                                        <span
                                                            class="truncate rounded bg-amber-600/30 px-1 py-0.5 tracking-wide text-amber-100 uppercase"
                                                            title="Custom Mapping"
                                                            >Custom</span>
                                                    {/if}
                                                    {#if m.anilist.format}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={m.anilist.format}
                                                            >{m.anilist.format}</span
                                                        >{/if}
                                                    {#if m.anilist.status}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={m.anilist.status}
                                                            >{m.anilist.status}</span
                                                        >{/if}
                                                    {#if m.anilist.season && m.anilist.seasonYear}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                            title={`${m.anilist.season} ${m.anilist.seasonYear}`}
                                                            >{m.anilist.season}
                                                            {m.anilist.seasonYear}</span
                                                        >{/if}
                                                    {#if m.anilist.episodes}<span
                                                            class="truncate rounded bg-slate-800/70 px-1 py-0.5"
                                                            title={`${m.anilist.episodes} episodes`}
                                                            >EP {m.anilist
                                                                .episodes}</span
                                                        >{/if}
                                                    {#if m.anilist?.isAdult}
                                                        <span
                                                            class="rounded bg-rose-800 px-1 py-0.5"
                                                            title="ADULT content"
                                                            >ADULT</span>
                                                    {/if}
                                                </div>
                                            {/if}
                                        </div>
                                    </div>
                                {:else if column.id === "anilist"}
                                    <div class="font-mono">
                                        {#if m.anilist_id}
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <button
                                                        type="button"
                                                        class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                        title={`Filter by AniList ${m.anilist_id}`}
                                                        onclick={() =>
                                                            navigate(
                                                                "anilist",
                                                                m.anilist_id,
                                                            )}>{m.anilist_id}</button>
                                                    <a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-slate-500 transition-colors hover:text-emerald-300"
                                                        aria-label={`Open AniList ${m.anilist_id}`}
                                                        href={`https://anilist.co/anime/${m.anilist_id}`}>
                                                        <ExternalLink class="h-3 w-3" />
                                                    </a>
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "anidb"}
                                    <div class="font-mono">
                                        {#if m.anidb_id}
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <button
                                                        type="button"
                                                        class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                        title={`Filter by AniDB ${m.anidb_id}`}
                                                        onclick={() =>
                                                            navigate(
                                                                "anidb",
                                                                m.anidb_id,
                                                            )}>{m.anidb_id}</button>
                                                    <a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-slate-500 transition-colors hover:text-emerald-300"
                                                        aria-label={`Open AniDB ${m.anidb_id}`}
                                                        href={`https://anidb.net/anime/${m.anidb_id}`}>
                                                        <ExternalLink class="h-3 w-3" />
                                                    </a>
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "imdb"}
                                    <div class="font-mono">
                                        {#if m.imdb_id && m.imdb_id.length}
                                            <div class="scroll-wrapper">
                                                <div
                                                    class="scroll-row"
                                                    title={m.imdb_id.join(", ")}>
                                                    {#each m.imdb_id as imdb (imdb)}
                                                        <div
                                                            class="flex shrink-0 items-center gap-1">
                                                            <button
                                                                type="button"
                                                                class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                                title={`Filter by IMDb ${imdb}`}
                                                                onclick={() =>
                                                                    navigate(
                                                                        "imdb",
                                                                        imdb,
                                                                    )}>{imdb}</button>
                                                            <a
                                                                rel="noopener"
                                                                target="_blank"
                                                                class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                aria-label={`Open IMDb ${imdb}`}
                                                                href={`https://www.imdb.com/title/${imdb}/`}>
                                                                <ExternalLink
                                                                    class="h-3 w-3" />
                                                            </a>
                                                        </div>
                                                    {/each}
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tmdb_movie"}
                                    <div class="font-mono">
                                        {#if m.tmdb_movie_id && m.tmdb_movie_id.length}
                                            <div class="scroll-wrapper">
                                                <div
                                                    class="scroll-row"
                                                    title={m.tmdb_movie_id.join(", ")}>
                                                    {#each m.tmdb_movie_id as id (id)}
                                                        <div
                                                            class="flex shrink-0 items-center gap-1">
                                                            <button
                                                                type="button"
                                                                class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                                title={`Filter by TMDB Movie ${id}`}
                                                                onclick={() =>
                                                                    navigate(
                                                                        "tmdb_movie",
                                                                        id,
                                                                    )}>{id}</button>
                                                            <a
                                                                rel="noopener"
                                                                target="_blank"
                                                                class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                aria-label={`Open TMDB Movie ${id}`}
                                                                href={`https://www.themoviedb.org/movie/${id}`}>
                                                                <ExternalLink
                                                                    class="h-3 w-3" />
                                                            </a>
                                                        </div>
                                                    {/each}
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tmdb_show"}
                                    <div class="font-mono">
                                        {#if m.tmdb_show_id}
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <button
                                                        type="button"
                                                        class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                        title={`Filter by TMDB Show ${m.tmdb_show_id}`}
                                                        onclick={() =>
                                                            navigate(
                                                                "tmdb_show",
                                                                m.tmdb_show_id,
                                                            )}>{m.tmdb_show_id}</button>
                                                    <a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-slate-500 transition-colors hover:text-emerald-300"
                                                        aria-label={`Open TMDB Show ${m.tmdb_show_id}`}
                                                        href={`https://www.themoviedb.org/tv/${m.tmdb_show_id}`}>
                                                        <ExternalLink class="h-3 w-3" />
                                                    </a>
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tvdb"}
                                    <div class="font-mono">
                                        {#if m.tvdb_id}
                                            <div class="scroll-wrapper">
                                                <div class="scroll-row">
                                                    <button
                                                        type="button"
                                                        class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                        title={`Filter by TVDB ${m.tvdb_id}`}
                                                        onclick={() =>
                                                            navigate("tvdb", m.tvdb_id)}
                                                        >{m.tvdb_id}</button>
                                                    <a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-slate-500 transition-colors hover:text-emerald-300"
                                                        aria-label={`Open TVDB ${m.tvdb_id}`}
                                                        href={`https://thetvdb.com/?tab=series&id=${m.tvdb_id}`}>
                                                        <ExternalLink class="h-3 w-3" />
                                                    </a>
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "mal"}
                                    <div class="font-mono">
                                        {#if m.mal_id && m.mal_id.length}
                                            <div class="scroll-wrapper">
                                                <div
                                                    class="scroll-row"
                                                    title={m.mal_id.join(", ")}>
                                                    {#each m.mal_id as id (id)}
                                                        <div
                                                            class="flex shrink-0 items-center gap-1">
                                                            <button
                                                                type="button"
                                                                class="cursor-pointer rounded px-0.5 text-left text-emerald-400 select-text hover:underline focus:ring-1 focus:ring-emerald-500/40 focus:outline-none"
                                                                title={`Filter by MAL ${id}`}
                                                                onclick={() =>
                                                                    navigate("mal", id)}
                                                                >{id}</button>
                                                            <a
                                                                rel="noopener"
                                                                target="_blank"
                                                                class="text-slate-500 transition-colors hover:text-emerald-300"
                                                                aria-label={`Open MAL ${id}`}
                                                                href={`https://myanimelist.net/anime/${id}`}>
                                                                <ExternalLink
                                                                    class="h-3 w-3" />
                                                            </a>
                                                        </div>
                                                    {/each}
                                                </div>
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tmdb_mappings"}
                                    {#key JSON.stringify(m.tmdb_mappings ?? {})}
                                        {@const entries = Object.entries(
                                            m.tmdb_mappings ?? {},
                                        )}
                                        {@const totalSeasons = entries.length}
                                        <div class="flex justify-center">
                                            {#if totalSeasons > 0}
                                                <Tooltip.Root>
                                                    <Tooltip.Trigger>
                                                        <span
                                                            class={`inline-flex h-5 min-w-5 items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                                            >{totalSeasons}</span>
                                                    </Tooltip.Trigger>
                                                    <Tooltip.Portal>
                                                        <Tooltip.Content
                                                            collisionPadding={12}
                                                            side="bottom"
                                                            sideOffset={6}
                                                            class="max-h-27 max-w-[90vw] overflow-auto rounded-md border border-slate-700 bg-slate-900 p-2 text-left text-[11px] shadow-lg">
                                                            <ol class="space-y-1">
                                                                {#each entries as e (e[0])}
                                                                    <li
                                                                        class="flex items-start gap-1 wrap-break-word">
                                                                        <span
                                                                            class="text-slate-500"
                                                                            >{e[0]}</span>
                                                                        <span
                                                                            class="text-slate-300"
                                                                            title={e[1]}
                                                                            >{e[1] ||
                                                                                "All episodes"}</span>
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
                                {:else if column.id === "tvdb_mappings"}
                                    {#key JSON.stringify(m.tvdb_mappings ?? {})}
                                        {@const entries = Object.entries(
                                            m.tvdb_mappings ?? {},
                                        )}
                                        {@const totalSeasons = entries.length}
                                        <div class="flex justify-center">
                                            {#if totalSeasons > 0}
                                                <Tooltip.Root>
                                                    <Tooltip.Trigger>
                                                        <span
                                                            class={`inline-flex h-5 min-w-5 items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                                            >{totalSeasons}</span>
                                                    </Tooltip.Trigger>
                                                    <Tooltip.Portal>
                                                        <Tooltip.Content
                                                            collisionPadding={12}
                                                            side="bottom"
                                                            sideOffset={6}
                                                            class="max-h-27 max-w-[90vw] overflow-auto rounded-md border border-slate-700 bg-slate-900 p-2 text-left text-[11px] shadow-lg">
                                                            <ol class="space-y-1">
                                                                {#each entries as e (e[0])}
                                                                    <li
                                                                        class="flex items-start gap-1 wrap-break-word">
                                                                        <span
                                                                            class="text-slate-500"
                                                                            >{e[0]}</span>
                                                                        <span
                                                                            class="text-slate-300"
                                                                            title={e[1]}
                                                                            >{e[1] ||
                                                                                "All episodes"}</span>
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
                                {:else if column.id === "source"}
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
                                                                            >{i +
                                                                                1}.</span>
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
                                                aria-label="Delete mapping options"
                                                title="Delete mapping options">
                                                Del
                                            </Popover.Trigger>
                                            <Popover.Content
                                                align="end"
                                                side="top"
                                                sideOffset={6}
                                                class="z-50 w-44 rounded-md border border-rose-800/60 bg-slate-950/95 p-2 text-left text-[11px] shadow-lg">
                                                <div class="space-y-1">
                                                    <Popover.Close
                                                        class="flex w-full items-center justify-start rounded px-2 py-1 text-left text-[11px] text-slate-100 hover:bg-rose-900/60"
                                                        onclick={() =>
                                                            onDelete?.({
                                                                mapping: m,
                                                                kind: "custom",
                                                            })}
                                                        >Reset to upstream</Popover.Close>
                                                    <Popover.Close
                                                        class="flex w-full items-center justify-start rounded px-2 py-1 text-left text-[11px] text-rose-100 hover:bg-rose-900/60"
                                                        onclick={() =>
                                                            onDelete?.({
                                                                mapping: m,
                                                                kind: "full",
                                                            })}
                                                        >Remove mapping</Popover.Close>
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
