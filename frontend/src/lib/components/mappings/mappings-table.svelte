<script lang="ts">
    import type { Mapping } from "$lib/types/api";
    import UiTooltip from "$lib/ui/tooltip.svelte";

    export interface Props {
        items: Mapping[];
        onEdit: (m: Mapping) => void;
        onDelete: (m: Mapping) => void;
    }

    let { items = $bindable([]), onEdit, onDelete }: Props = $props();

    function preferredTitle(
        t?: {
            romaji?: string | null;
            english?: string | null;
            native?: string | null;
        } | null,
    ) {
        if (!t) return null;
        let pref: string | null = null;
        try {
            pref = localStorage.getItem("anilist.lang");
        } catch {}
        if (pref && t[pref as keyof typeof t]) return t[pref as keyof typeof t] || null;
        return t.romaji || t.english || t.native || null;
    }
</script>

<div class="flex-1 overflow-auto">
    <div class="min-w-[1000px] sm:min-w-0">
        <table class="w-full align-middle text-xs">
            <thead
                class="sticky top-0 z-10 bg-gradient-to-b from-slate-900/70 to-slate-900/40 text-slate-300"
            >
                <tr class="divide-x divide-slate-800/70 whitespace-nowrap">
                    <th class="px-3 py-2 text-left font-medium">Title</th>
                    <th class="px-3 py-2 text-left font-medium">AniList</th>
                    <th class="px-3 py-2 text-left font-medium">AniDB</th>
                    <th class="px-3 py-2 text-left font-medium">IMDB</th>
                    <th class="px-3 py-2 text-left font-medium">TMDB (Movie)</th>
                    <th class="px-3 py-2 text-left font-medium">TMDB (Show)</th>
                    <th class="px-3 py-2 text-left font-medium">TVDB</th>
                    <th class="px-3 py-2 text-left font-medium">MAL</th>
                    <th class="px-3 py-2 text-left font-medium">Seasons</th>
                    <th class="px-3 py-2 text-left font-medium">Source</th>
                    <th class="px-3 py-2 text-right font-medium">Actions</th>
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
                        <td class="w-64 px-3 py-2">
                            <div class="flex items-start gap-2">
                                <a
                                    href={`https://anilist.co/anime/${m.anilist_id}`}
                                    rel="noopener noreferrer"
                                    target="_blank"
                                    class="w-12 shrink-0"
                                >
                                    {#if coverImage}
                                        <img
                                            alt={(preferredTitle(m.anilist?.title) ||
                                                "Cover") + " cover"}
                                            loading="lazy"
                                            src={coverImage}
                                            class="h-16 w-12 rounded-md object-cover ring-1 ring-slate-700/60"
                                        />
                                    {:else}
                                        <div
                                            class="flex h-16 w-12 shrink-0 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none"
                                        >
                                            No Art
                                        </div>
                                    {/if}
                                </a>
                                <div class="min-w-0 space-y-0.5">
                                    <div class="truncate font-medium">
                                        {#if m?.anilist?.title}{preferredTitle(
                                                m.anilist.title,
                                            )}{:else}AniList {m.anilist_id}{/if}
                                    </div>
                                    {#if m.anilist && (m.anilist.format || m.anilist.status || m.anilist.episodes)}
                                        <div
                                            class="flex flex-wrap gap-1 text-[9px] text-slate-400"
                                        >
                                            {#if m.anilist.format}<span
                                                    class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                    >{m.anilist.format}</span
                                                >{/if}
                                            {#if m.anilist.status}<span
                                                    class="rounded bg-slate-800/70 px-1 py-0.5 tracking-wide uppercase"
                                                    >{m.anilist.status}</span
                                                >{/if}
                                            {#if m.anilist.episodes}<span
                                                    class="rounded bg-slate-800/70 px-1 py-0.5"
                                                    >EP {m.anilist.episodes}</span
                                                >{/if}
                                        </div>
                                    {/if}
                                </div>
                            </div>
                        </td>
                        <td class="px-3 py-2 font-mono"
                            >{#if m.anilist_id}<a
                                    rel="noopener"
                                    target="_blank"
                                    class="text-emerald-400 hover:underline"
                                    href={"https://anilist.co/anime/" + m.anilist_id}
                                    >{m.anilist_id}</a
                                >{:else}-{/if}</td
                        >
                        <td class="px-3 py-2 font-mono"
                            >{#if m.anidb_id}<a
                                    rel="noopener"
                                    target="_blank"
                                    class="text-emerald-400 hover:underline"
                                    href={"https://anidb.net/anime/" + m.anidb_id}
                                    >{m.anidb_id}</a
                                >{:else}-{/if}</td
                        >
                        <td class="px-3 py-2 font-mono">
                            {#if m.imdb_id && m.imdb_id.length}{#each m.imdb_id as imdb, i (imdb)}<a
                                        rel="noopener"
                                        target="_blank"
                                        class="text-emerald-400 hover:underline"
                                        href={"https://www.imdb.com/title/" +
                                            imdb +
                                            "/"}>{imdb}</a
                                    >{#if m.imdb_id && i < m.imdb_id.length - 1},
                                    {/if}{/each}{:else}-{/if}
                        </td>
                        <td class="px-3 py-2 font-mono">
                            {#if m.tmdb_movie_id && m.tmdb_movie_id.length}{#each m.tmdb_movie_id as id, i (id)}<a
                                        rel="noopener"
                                        target="_blank"
                                        class="text-emerald-400 hover:underline"
                                        href={"https://www.themoviedb.org/movie/" + id}
                                        >{id}</a
                                    >{#if m.tmdb_movie_id && i < m.tmdb_movie_id.length - 1},
                                    {/if}{/each}{:else}-{/if}
                        </td>
                        <td class="px-3 py-2 font-mono">
                            {#if m.tmdb_show_id && m.tmdb_show_id.length}{#each m.tmdb_show_id as id, i (id)}<a
                                        rel="noopener"
                                        target="_blank"
                                        class="text-emerald-400 hover:underline"
                                        href={"https://www.themoviedb.org/tv/" + id}
                                        >{id}</a
                                    >{#if m.tmdb_show_id && i < m.tmdb_show_id.length - 1},
                                    {/if}{/each}{:else}-{/if}
                        </td>
                        <td class="px-3 py-2 font-mono"
                            >{#if m.tvdb_id}<a
                                    rel="noopener"
                                    target="_blank"
                                    class="text-emerald-400 hover:underline"
                                    href={"https://thetvdb.com/?tab=series&id=" +
                                        m.tvdb_id}>{m.tvdb_id}</a
                                >{:else}-{/if}</td
                        >
                        <td class="px-3 py-2 font-mono"
                            >{#if m.mal_id && m.mal_id.length}{#each m.mal_id as id, i (id)}<a
                                        rel="noopener"
                                        target="_blank"
                                        class="text-emerald-400 hover:underline"
                                        href={"https://myanimelist.net/anime/" + id}
                                        >{id}</a
                                    >{#if m.mal_id && i < m.mal_id.length - 1},
                                    {/if}{/each}{:else}-{/if}</td
                        >
                        <td class="px-3 py-2">
                            {#key JSON.stringify(m.tvdb_mappings ?? {})}
                                {@const entries = Object.entries(m.tvdb_mappings ?? {})}
                                {@const totalSeasons = entries.length}
                                {#if totalSeasons > 0}
                                    <UiTooltip>
                                        <span
                                            class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                            slot="trigger">{totalSeasons}</span
                                        >
                                        <ol
                                            class="max-h-52 space-y-1 overflow-auto text-[11px]"
                                        >
                                            {#each entries as e (e[0])}
                                                <li class="flex items-start gap-1">
                                                    <span class="text-slate-500"
                                                        >{e[0]}</span
                                                    >
                                                    <span
                                                        class="truncate text-slate-300"
                                                        title={e[1]}
                                                        >{e[1] || "All episodes"}</span
                                                    >
                                                </li>
                                            {/each}
                                        </ol>
                                    </UiTooltip>
                                {:else}
                                    <span class="text-[10px] text-slate-500">-</span>
                                {/if}
                            {/key}
                        </td>
                        <td class="px-3 py-2">
                            {#key (m.sources ?? []).join("|") + ":" + String(m.custom)}
                                {@const total = (m.sources ?? []).length}
                                {#if total > 0}
                                    <UiTooltip>
                                        <span
                                            class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${total > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                            slot="trigger">{total}</span
                                        >
                                        <ol class="space-y-1 text-[11px]">
                                            {#each m.sources ?? [] as s, i (i)}
                                                <li class="flex items-start gap-1">
                                                    <span class="text-slate-500"
                                                        >{i + 1}.</span
                                                    >
                                                    <span class="truncate" title={s}
                                                        >{s}</span
                                                    >
                                                </li>
                                            {/each}
                                        </ol>
                                    </UiTooltip>
                                {:else}
                                    <span class="text-[10px] text-slate-500">-</span>
                                {/if}
                            {/key}
                        </td>
                        <td class="px-3 py-2 text-right whitespace-nowrap">
                            <div class="flex justify-end gap-1">
                                <button
                                    onclick={() => onEdit(m)}
                                    class="inline-flex h-6 items-center rounded-md bg-slate-800 px-2 text-[11px] text-slate-200 hover:bg-slate-700"
                                    >Edit</button
                                >
                                <button
                                    onclick={() => onDelete(m)}
                                    title="Delete mapping"
                                    class="inline-flex h-6 items-center rounded-md bg-rose-700/70 px-2 text-[11px] text-rose-200 hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-35"
                                    >Del</button
                                >
                            </div>
                        </td>
                    </tr>
                {/each}
                {#if !items.length}
                    <tr
                        ><td colspan="11" class="py-8 text-center text-slate-500"
                            >No mappings found</td
                        >
                    </tr>
                {/if}
            </tbody>
        </table>
    </div>
</div>
