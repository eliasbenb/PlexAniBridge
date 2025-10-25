<script lang="ts">
    import { Tooltip } from "bits-ui";

    import type { Mapping } from "$lib/types/api";
    import { preferredTitle } from "$lib/utils/anilist";
    import type { ColumnConfig } from "./columns";
    import { defaultColumns } from "./columns";

    export interface Props {
        items: Mapping[];
        columns?: ColumnConfig[];
        onEdit: (m: Mapping) => void;
        onDelete: (m: Mapping) => void;
    }

    let {
        items = $bindable([]),
        columns = $bindable([]),
        onEdit,
        onDelete,
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
                class="sticky top-0 z-10 bg-gradient-to-b from-slate-900/70 to-slate-900/40 text-slate-300">
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
                                    <div class="truncate font-mono">
                                        {#if m.anilist_id}<a
                                                rel="noopener"
                                                target="_blank"
                                                class="block truncate text-emerald-400 hover:underline"
                                                title={m.anilist_id.toString()}
                                                href={"https://anilist.co/anime/" +
                                                    m.anilist_id}>{m.anilist_id}</a
                                            >{:else}-{/if}
                                    </div>
                                {:else if column.id === "anidb"}
                                    <div class="truncate font-mono">
                                        {#if m.anidb_id}<a
                                                rel="noopener"
                                                target="_blank"
                                                class="block truncate text-emerald-400 hover:underline"
                                                title={m.anidb_id.toString()}
                                                href={"https://anidb.net/anime/" +
                                                    m.anidb_id}>{m.anidb_id}</a
                                            >{:else}-{/if}
                                    </div>
                                {:else if column.id === "imdb"}
                                    <div class="truncate font-mono">
                                        {#if m.imdb_id && m.imdb_id.length}
                                            <div
                                                class="truncate"
                                                title={m.imdb_id.join(", ")}>
                                                {#each m.imdb_id as imdb, i (imdb)}<a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-emerald-400 hover:underline"
                                                        href={"https://www.imdb.com/title/" +
                                                            imdb +
                                                            "/"}>{imdb}</a
                                                    >{#if m.imdb_id && i < m.imdb_id.length - 1},
                                                    {/if}{/each}
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tmdb_movie"}
                                    <div class="truncate font-mono">
                                        {#if m.tmdb_movie_id && m.tmdb_movie_id.length}
                                            <div
                                                class="truncate"
                                                title={m.tmdb_movie_id.join(", ")}>
                                                {#each m.tmdb_movie_id as id, i (id)}<a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-emerald-400 hover:underline"
                                                        href={"https://www.themoviedb.org/movie/" +
                                                            id}>{id}</a
                                                    >{#if m.tmdb_movie_id && i < m.tmdb_movie_id.length - 1},
                                                    {/if}{/each}
                                            </div>
                                        {:else}-{/if}
                                    </div>
                                {:else if column.id === "tmdb_show"}
                                    <div class="truncate font-mono">
                                        {#if m.tmdb_show_id}<a
                                                rel="noopener"
                                                target="_blank"
                                                class="block truncate text-emerald-400 hover:underline"
                                                title={m.tmdb_show_id.toString()}
                                                href={"https://www.themoviedb.org/tv/" +
                                                    m.tmdb_show_id}>{m.tmdb_show_id}</a
                                            >{:else}-{/if}
                                    </div>
                                {:else if column.id === "tvdb"}
                                    <div class="truncate font-mono">
                                        {#if m.tvdb_id}<a
                                                rel="noopener"
                                                target="_blank"
                                                class="block truncate text-emerald-400 hover:underline"
                                                title={m.tvdb_id.toString()}
                                                href={"https://thetvdb.com/?tab=series&id=" +
                                                    m.tvdb_id}>{m.tvdb_id}</a
                                            >{:else}-{/if}
                                    </div>
                                {:else if column.id === "mal"}
                                    <div class="truncate font-mono">
                                        {#if m.mal_id && m.mal_id.length}
                                            <div
                                                class="truncate"
                                                title={m.mal_id.join(", ")}>
                                                {#each m.mal_id as id, i (id)}<a
                                                        rel="noopener"
                                                        target="_blank"
                                                        class="text-emerald-400 hover:underline"
                                                        href={"https://myanimelist.net/anime/" +
                                                            id}>{id}</a
                                                    >{#if m.mal_id && i < m.mal_id.length - 1},
                                                    {/if}{/each}
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
                                                            class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
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
                                                                        class="flex items-start gap-1 break-words">
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
                                                            class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
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
                                                                        class="flex items-start gap-1 break-words">
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
                                                            class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${total > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
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
                                                                        class="flex items-start gap-1 break-words">
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
                                            onclick={() => onEdit(m)}
                                            class="inline-flex h-6 items-center rounded-md bg-slate-800 px-2 text-[11px] text-slate-200 hover:bg-slate-700"
                                            >Edit</button>
                                        <button
                                            onclick={() => onDelete(m)}
                                            title="Delete mapping"
                                            class="inline-flex h-6 items-center rounded-md bg-rose-700/70 px-2 text-[11px] text-rose-200 hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-35"
                                            >Del</button>
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
