<script lang="ts">
    import { onMount } from "svelte";

    import { ArrowRight, Check, List, PenLine, Plus, Search, X } from "@lucide/svelte";

    type ExternalIds = {
        anilist_id?: number | null;
        anidb_id?: number | null;
        imdb_id?: string[] | null;
        mal_id?: number[] | null;
        tmdb_movie_id?: number[] | null;
        tmdb_show_id?: number[] | null;
        tvdb_id?: number | null;
        custom?: boolean;
        tvdb_mappings?: Record<string, string> | null;
    };

    interface AniListMediaLite {
        id: number;
        title?: { romaji?: string; english?: string; native?: string };
        coverImage?: {
            medium?: string;
            large?: string;
            extraLarge: string;
            color?: string;
        };
        format?: string;
        status?: string;
        episodes?: number;
    }

    type Mapping = ExternalIds & { anilist?: AniListMediaLite };

    let items: Mapping[] = $state([]);
    let total = $state(0);
    let page = $state(1);
    let pages = $state(1);
    let perPage = $state(25);
    let query = $state("");
    let customOnly = $state(false);
    let loading = $state(false);
    let modal = $state(false);

    interface TvdbMapRow {
        season: string;
        pattern: string;
    }

    interface EditForm {
        _isNew: boolean;
        anilist_id: string | number | "";
        anidb_mode: "omit" | "null" | "value";
        anidb_id: string | number | "";
        tvdb_mode: "omit" | "null" | "value";
        tvdb_id: string | number | "";
        imdb_mode: "omit" | "null" | "value";
        imdb_csv: string;
        mal_mode: "omit" | "null" | "value";
        mal_csv: string;
        tmdb_movie_mode: "omit" | "null" | "value";
        tmdb_movie_csv: string;
        tmdb_show_mode: "omit" | "null" | "value";
        tmdb_show_csv: string;
        tvdb_map_mode: "omit" | "null" | "value";
        tvdb_mappings: TvdbMapRow[];
    }

    let form: EditForm = $state(emptyForm());
    let rawOpen: Record<number, boolean> = $state({});

    function emptyForm(): EditForm {
        return {
            _isNew: true,
            anilist_id: "",
            anidb_mode: "omit",
            anidb_id: "",
            tvdb_mode: "omit",
            tvdb_id: "",
            imdb_mode: "omit",
            imdb_csv: "",
            mal_mode: "omit",
            mal_csv: "",
            tmdb_movie_mode: "omit",
            tmdb_movie_csv: "",
            tmdb_show_mode: "omit",
            tmdb_show_csv: "",
            tvdb_map_mode: "omit",
            tvdb_mappings: [],
        };
    }

    async function load() {
        loading = true;
        try {
            const p = new URLSearchParams({
                page: String(page),
                per_page: String(perPage),
            });
            if (query) p.set("search", query);
            if (customOnly) p.set("custom_only", "true");
            p.set("with_anilist", "true");
            const r = await fetch("/api/mappings?" + p.toString());
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            items = d.items || [];
            total = d.total || 0;
            pages = d.pages || 1;
            page = d.page || page;
        } catch (e) {
            console.error("load mappings failed", e);
        } finally {
            loading = false;
        }
    }

    function openNew() {
        form = emptyForm();
        modal = true;
    }

    function openEdit(m: Mapping) {
        const f = emptyForm();
        f._isNew = false;
        f.anilist_id = m.anilist_id ?? "";
        // Scalar numeric ids
        if (m.anidb_id !== undefined) {
            f.anidb_mode = m.anidb_id === null ? "null" : "value";
            f.anidb_id = (m.anidb_id as number | null) ?? "";
        }
        if (m.tvdb_id !== undefined) {
            f.tvdb_mode = m.tvdb_id === null ? "null" : "value";
            f.tvdb_id = (m.tvdb_id as number | null) ?? "";
        }
        // Arrays / CSV
        if (m.imdb_id !== undefined) {
            f.imdb_mode = m.imdb_id === null ? "null" : "value";
            f.imdb_csv = Array.isArray(m.imdb_id)
                ? m.imdb_id.join(",")
                : m.imdb_id || "";
        }
        if (m.mal_id !== undefined) {
            f.mal_mode = m.mal_id === null ? "null" : "value";
            f.mal_csv = Array.isArray(m.mal_id) ? m.mal_id.join(",") : m.mal_id || "";
        }
        if (m.tmdb_movie_id !== undefined) {
            f.tmdb_movie_mode = m.tmdb_movie_id === null ? "null" : "value";
            f.tmdb_movie_csv = Array.isArray(m.tmdb_movie_id)
                ? m.tmdb_movie_id.join(",")
                : m.tmdb_movie_id || "";
        }
        if (m.tmdb_show_id !== undefined) {
            f.tmdb_show_mode = m.tmdb_show_id === null ? "null" : "value";
            f.tmdb_show_csv = Array.isArray(m.tmdb_show_id)
                ? m.tmdb_show_id.join(",")
                : m.tmdb_show_id || "";
        }
        if (m.tvdb_mappings && typeof m.tvdb_mappings === "object") {
            f.tvdb_map_mode = "value";
            for (const [season, pattern] of Object.entries(m.tvdb_mappings)) {
                f.tvdb_mappings.push({ season, pattern });
            }
        } else if ("tvdb_mappings" in m && m.tvdb_mappings === null) {
            f.tvdb_map_mode = "null";
        }
        modal = true;
        form = f;
    }

    function toPayload(f: EditForm) {
        const toInt = (v: unknown) => {
            if (v === "" || v == null) return null;
            const n = Number(v);
            return Number.isFinite(n) ? n : null;
        };
        function parseCSV(s: string, to: "string"): string[] | null;
        function parseCSV(s: string, to: "int"): number[] | null;
        function parseCSV(
            s: string,
            to: "string" | "int",
        ): (string[] | number[]) | null {
            if (!s || !s.trim()) return null;
            const arr = s
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean);
            if (!arr.length) return null;
            return to === "int"
                ? arr.map((x) => Number(x)).filter((n) => Number.isFinite(n))
                : arr;
        }

        const out: Mapping = { anilist_id: toInt(f.anilist_id) } as Mapping;
        if (f.anidb_mode === "null") out.anidb_id = null;
        else if (f.anidb_mode === "value") out.anidb_id = toInt(f.anidb_id);
        if (f.tvdb_mode === "null") out.tvdb_id = null;
        else if (f.tvdb_mode === "value") out.tvdb_id = toInt(f.tvdb_id);
        if (f.imdb_mode === "null") out.imdb_id = null;
        else if (f.imdb_mode === "value") out.imdb_id = parseCSV(f.imdb_csv, "string");
        if (f.mal_mode === "null") out.mal_id = null;
        else if (f.mal_mode === "value") out.mal_id = parseCSV(f.mal_csv, "int");
        if (f.tmdb_movie_mode === "null") out.tmdb_movie_id = null;
        else if (f.tmdb_movie_mode === "value")
            out.tmdb_movie_id = parseCSV(f.tmdb_movie_csv, "int");
        if (f.tmdb_show_mode === "null") out.tmdb_show_id = null;
        else if (f.tmdb_show_mode === "value")
            out.tmdb_show_id = parseCSV(f.tmdb_show_csv, "int");
        if (f.tvdb_map_mode === "null") out.tvdb_mappings = null;
        else if (f.tvdb_map_mode === "value") {
            const obj: Record<string, string> = {};
            for (const row of f.tvdb_mappings) {
                if (!row || !row.season) continue;
                let key = String(row.season).trim();
                if (!key.toLowerCase().startsWith("s")) key = "s" + key;
                obj[key] = row.pattern ? String(row.pattern) : "";
            }
            out.tvdb_mappings = Object.keys(obj).length ? obj : null;
        }
        return out;
    }

    async function save() {
        const aid = Number(form.anilist_id);
        if (!aid || Number.isNaN(aid)) {
            alert("AniList ID required");
            return;
        }
        const payload = toPayload(form);
        const isNew = form._isNew;
        const url = isNew ? "/api/mappings" : "/api/mappings/" + aid;
        const method = isNew ? "POST" : "PUT";
        try {
            const r = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!r.ok) throw new Error("HTTP " + r.status);
            modal = false;
            load();
        } catch (e) {
            console.error("save failed", e);
            alert("Save failed");
        }
    }

    async function remove(m: Mapping) {
        if (!confirm("Delete override for AniList " + m.anilist_id + "?")) return;
        try {
            const r = await fetch("/api/mappings/" + m.anilist_id, {
                method: "DELETE",
            });
            if (!r.ok) throw new Error("HTTP " + r.status);
            load();
        } catch (e) {
            console.error("delete failed", e);
            alert("Delete failed");
        }
    }

    function toggleRaw(m: Mapping) {
        const id = m.anilist_id;
        if (id == null) return;
        rawOpen[id] = !rawOpen[id];
    }

    function fmtSeasons(m: Mapping) {
        return Object.keys(m.tvdb_mappings || {}).length;
    }

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

    onMount(load);
</script>

<div class="space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div class="space-y-1">
            <div class="flex items-center gap-2">
                <List class="inline h-4 w-4 text-slate-300" />
                <h2 class="text-lg font-semibold">Mappings</h2>
            </div>
            <p class="text-xs text-slate-400">
                Browse & override external ID relationships
            </p>
        </div>
        <div class="flex items-center gap-2 text-[11px]">
            <div class="relative">
                <input
                    bind:value={query}
                    placeholder="Search (AniList, TMDB, IMDB, etc)"
                    aria-label="Search mappings"
                    class="h-8 w-72 rounded-md border border-slate-700/70 bg-slate-900/70 pr-9 pl-8 text-[11px] shadow-sm placeholder:text-slate-500 focus:border-slate-600 focus:bg-slate-900"
                    onkeydown={(e) => e.key === "Enter" && ((page = 1), load())}
                />
                <Search
                    class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                />
                <button
                    class="absolute top-1/2 right-1 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700"
                    aria-label="Run search"
                    onclick={() => ((page = 1), load())}
                >
                    <ArrowRight class="inline h-3 w-3" />
                </button>
            </div>
            <button
                onclick={() => {
                    customOnly = !customOnly;
                    page = 1;
                    load();
                }}
                class={`inline-flex h-8 items-center gap-1 rounded-md px-3 text-[11px] font-medium ring-1 ${customOnly ? "bg-emerald-600/90 text-white ring-emerald-500/40 hover:bg-emerald-500" : "bg-slate-800 text-slate-300 ring-slate-700/60 hover:bg-slate-700"}`}
            >
                {#if customOnly}
                    <Check class="inline h-3.5 w-3.5 text-[14px]" />
                {:else}
                    <svg
                        class="inline h-3.5 w-3.5"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        ><rect x="3" y="3" width="18" height="18" rx="2" ry="2"
                        ></rect></svg
                    >
                {/if}
                <span>Custom Only</span>
            </button>
            <div class="ml-auto flex items-center gap-2">
                <label for="perPage" class="text-[11px] text-slate-400">Per Page</label>
                <select
                    id="perPage"
                    bind:value={perPage}
                    class="h-8 rounded-md border border-slate-700/70 bg-slate-950/70 px-2 text-[11px] shadow-sm focus:border-slate-600 focus:bg-slate-950"
                    onchange={() => ((page = 1), load())}
                >
                    <option value={10}>10</option>
                    <option value={25}>25</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                </select>
                <button
                    title="New Override"
                    aria-label="New Override"
                    class="inline-flex h-8 items-center gap-1 rounded-md bg-emerald-600/90 px-3 text-[11px] font-medium text-emerald-50 hover:bg-emerald-500"
                    onclick={openNew}
                >
                    <Plus class="inline h-3.5 w-3.5 text-[14px]" />
                </button>
            </div>
        </div>
    </div>
    <div
        class="relative flex h-[70vh] flex-col overflow-hidden rounded-md border border-slate-800/70 bg-slate-900/40 backdrop-blur-sm"
    >
        <div
            class="flex items-center gap-4 border-b border-slate-800/60 bg-slate-950/50 px-3 py-2 text-[11px]"
        >
            <span class="text-slate-400"
                >Showing <span class="font-medium text-slate-200">{items.length}</span
                >/<span class="text-slate-500">{total}</span></span
            >
            {#if pages > 1}<span class="text-slate-500">Page {page} / {pages}</span
                >{/if}
            {#if customOnly}<span class="text-emerald-400">Custom overrides only</span
                >{/if}
        </div>
        <div class="flex-1 overflow-auto">
            <table class="min-w-full align-middle text-xs">
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
                                                alt={(preferredTitle(
                                                    m.anilist?.title,
                                                ) || "Cover") + " cover"}
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
                                            {#if m?.anilist?.title}
                                                {preferredTitle(m.anilist.title)}
                                            {:else}AniList {m.anilist_id}{/if}
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
                                        href={"https://anilist.co/anime/" +
                                            m.anilist_id}>{m.anilist_id}</a
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
                                        {/if}{/each}{:else}-{/if}</td
                            >
                            <td class="px-3 py-2 font-mono">
                                {#if m.tmdb_movie_id && m.tmdb_movie_id.length}{#each m.tmdb_movie_id as id, i (id)}<a
                                            rel="noopener"
                                            target="_blank"
                                            class="text-emerald-400 hover:underline"
                                            href={"https://www.themoviedb.org/movie/" +
                                                id}>{id}</a
                                        >{#if m.tmdb_movie_id && i < m.tmdb_movie_id.length - 1},
                                        {/if}{/each}{:else}-{/if}</td
                            >
                            <td class="px-3 py-2 font-mono">
                                {#if m.tmdb_show_id && m.tmdb_show_id.length}{#each m.tmdb_show_id as id, i (id)}<a
                                            rel="noopener"
                                            target="_blank"
                                            class="text-emerald-400 hover:underline"
                                            href={"https://www.themoviedb.org/tv/" + id}
                                            >{id}</a
                                        >{#if m.tmdb_show_id && i < m.tmdb_show_id.length - 1},
                                        {/if}{/each}{:else}-{/if}</td
                            >
                            <td class="px-3 py-2 font-mono"
                                >{#if m.tvdb_id}<a
                                        rel="noopener"
                                        target="_blank"
                                        class="text-emerald-400 hover:underline"
                                        href={"https://thetvdb.com/?tab=series&id=" +
                                            m.tvdb_id}>{m.tvdb_id}</a
                                    >{:else}-{/if}</td
                            >
                            <td class="px-3 py-2 font-mono">
                                {#if m.mal_id && m.mal_id.length}{#each m.mal_id as id, i (id)}<a
                                            rel="noopener"
                                            target="_blank"
                                            class="text-emerald-400 hover:underline"
                                            href={"https://myanimelist.net/anime/" + id}
                                            >{id}</a
                                        >{#if m.mal_id && i < m.mal_id.length - 1},
                                        {/if}{/each}{:else}-{/if}</td
                            >
                            <td class="px-3 py-2 font-mono">{fmtSeasons(m)}</td>
                            <td class="px-3 py-2 text-right whitespace-nowrap">
                                <div class="flex flex-col items-end gap-1">
                                    <div class="flex gap-1">
                                        <button
                                            onclick={() => openEdit(m)}
                                            class="inline-flex h-6 items-center rounded-md bg-slate-800 px-2 text-[11px] text-slate-200 hover:bg-slate-700"
                                            >Edit</button
                                        >
                                        <button
                                            onclick={() => remove(m)}
                                            disabled={m.custom === false}
                                            title={m.custom === false
                                                ? "Not deletable"
                                                : "Delete mapping"}
                                            class="inline-flex h-6 items-center rounded-md bg-rose-700/70 px-2 text-[11px] text-rose-200 hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-35"
                                            >Del</button
                                        >
                                    </div>
                                    <button
                                        onclick={() => toggleRaw(m)}
                                        class="text-[10px] text-sky-400 hover:text-sky-300"
                                        >{m.anilist_id != null && rawOpen[m.anilist_id]
                                            ? "Hide JSON"
                                            : "Show JSON"}</button
                                    >
                                </div>
                                {#if m.anilist_id != null && rawOpen[m.anilist_id]}
                                    <div
                                        class="mt-2 max-h-40 w-80 overflow-auto rounded-md border border-slate-800 bg-slate-950/80 p-2 text-left font-mono text-[10px]"
                                    >
                                        <pre
                                            class="whitespace-pre-wrap">{JSON.stringify(
                                                m,
                                                null,
                                                2,
                                            )}</pre>
                                    </div>
                                {/if}
                            </td>
                        </tr>
                    {/each}
                    {#if !items.length && !loading}
                        <tr
                            ><td colspan="10" class="py-8 text-center text-slate-500"
                                >No mappings found</td
                            ></tr
                        >
                    {/if}
                </tbody>
            </table>
        </div>
    </div>
    {#if pages > 1}
        <div class="flex flex-wrap items-center gap-2 text-xs">
            <button
                onclick={() => page > 1 && (page--, load())}
                disabled={page === 1}
                class="rounded-md bg-slate-800 px-3 py-1.5 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                >Prev</button
            >
            <div class="flex items-center gap-1 rounded-md bg-slate-800/60 px-2 py-1">
                Page <input
                    type="number"
                    min="1"
                    max={pages}
                    bind:value={page}
                    class="h-6 w-12 [appearance:textfield] rounded-md border border-slate-700 bg-slate-900 px-1 text-center text-xs font-semibold [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    onchange={load}
                />
                / {pages}
            </div>
            <button
                onclick={() => page < pages && (page++, load())}
                disabled={page === pages}
                class="rounded-md bg-slate-800 px-3 py-1.5 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                >Next</button
            >
        </div>
    {/if}

    {#if modal}
        <div
            class="fixed inset-0 z-40 flex items-start justify-center overflow-auto bg-black/70 p-4 py-8 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-label={form._isNew ? "New Mapping Override" : "Edit Mapping Override"}
            tabindex="-1"
            onclick={(e) => e.target === e.currentTarget && (modal = false)}
            onkeydown={(e) => e.key === "Escape" && (modal = false)}
        >
            <div
                class="relative max-h-[calc(100vh-6rem)] w-full max-w-lg overflow-auto rounded-md border border-slate-700/70 bg-slate-900/95 shadow-xl ring-1 ring-slate-700/40"
            >
                <div class="space-y-3 p-4">
                    <div class="flex items-start justify-between gap-4">
                        <h3
                            class="flex items-center gap-2 text-sm font-semibold tracking-wide"
                        >
                            <PenLine class="inline h-4 w-4 text-slate-400" /><span
                                >{form._isNew
                                    ? "New Override"
                                    : "Edit Override #" + form.anilist_id}</span
                            >
                        </h3>
                        <button
                            onclick={() => (modal = false)}
                            class="text-slate-400 hover:text-slate-200"
                            ><X class="inline h-3.5 w-3.5" /></button
                        >
                    </div>
                    <div class="space-y-2">
                        <div class="flex items-center gap-2">
                            <label for="f-anilist" class="text-[11px] text-slate-400"
                                >AniList ID</label
                            ><input
                                id="f-anilist"
                                bind:value={form.anilist_id}
                                type="number"
                                class="h-8 w-full flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                                disabled={!form._isNew}
                            />
                        </div>
                        <div class="grid grid-cols-2 gap-3">
                            <!-- Scalar + array fields (subset for brevity) -->
                            <div>
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-anidb-mode"
                                        class="text-[11px] text-slate-400"
                                        >AniDB ID</label
                                    ><select
                                        id="f-anidb-mode"
                                        bind:value={form.anidb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                        ><option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option></select
                                    >
                                </div>
                                <input
                                    bind:value={form.anidb_id}
                                    type="number"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.anidb_mode !== "value"}
                                />
                            </div>
                            <div>
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tvdb-mode"
                                        class="text-[11px] text-slate-400"
                                        >TVDB ID</label
                                    ><select
                                        id="f-tvdb-mode"
                                        bind:value={form.tvdb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                        ><option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option></select
                                    >
                                </div>
                                <input
                                    bind:value={form.tvdb_id}
                                    type="number"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.tvdb_mode !== "value"}
                                />
                            </div>
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-imdb-mode"
                                        class="text-[11px] text-slate-400"
                                        >IMDB IDs <span class="text-xs text-slate-500"
                                            >(comma separated)</span
                                        ></label
                                    ><select
                                        id="f-imdb-mode"
                                        bind:value={form.imdb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                        ><option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option></select
                                    >
                                </div>
                                <input
                                    bind:value={form.imdb_csv}
                                    type="text"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.imdb_mode !== "value"}
                                />
                            </div>
                        </div>
                    </div>
                    <div class="flex justify-end gap-2 pt-1">
                        <button
                            onclick={() => (modal = false)}
                            class="rounded-md bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
                            >Cancel</button
                        ><button
                            onclick={save}
                            class="rounded-md bg-emerald-600/90 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
                            >Save</button
                        >
                    </div>
                </div>
            </div>
        </div>
    {/if}
</div>
