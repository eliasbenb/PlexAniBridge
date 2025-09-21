<script lang="ts">
    import { onMount } from "svelte";

    import { Check, List, PenLine, Plus, X } from "@lucide/svelte";
    import { Tabs } from "bits-ui";
    import { SvelteURLSearchParams } from "svelte/reactivity";

    import { apiFetch } from "$lib/api";
    import BooruSearch from "$lib/components/booru-search.svelte";
    import JsonCodeBlock from "$lib/components/json-code-block.svelte";
    import { toast } from "$lib/notify";
    import Modal from "$lib/ui/modal.svelte";
    import UiTooltip from "$lib/ui/tooltip.svelte";

    type ExternalIds = {
        anilist_id?: number | null;
        anidb_id?: number | null;
        imdb_id?: string[] | null;
        mal_id?: number[] | null;
        tmdb_movie_id?: number[] | null;
        tmdb_show_id?: number[] | null;
        tvdb_id?: number | null;
        tvdb_mappings?: Record<string, string> | null;
        custom?: boolean;
        sources?: string[];
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

    type FieldMode = "omit" | "null" | "value";

    interface EditForm {
        _isNew: boolean;
        anilist_id: string | number | "";
        anidb_mode: FieldMode;
        anidb_id: string | number | "";
        tvdb_mode: FieldMode;
        tvdb_id: string | number | "";
        imdb_mode: FieldMode;
        imdb_csv: string;
        mal_mode: FieldMode;
        mal_csv: string;
        tmdb_movie_mode: FieldMode;
        tmdb_movie_csv: string;
        tmdb_show_mode: FieldMode;
        tmdb_show_csv: string;
        tvdb_map_mode: FieldMode;
        tvdb_mappings: TvdbMapRow[];
    }

    let form: EditForm = $state(emptyForm());
    let editMode: "form" | "raw" = $state("form");
    let rawJSON = $state("");

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
            const p = new SvelteURLSearchParams({
                page: String(page),
                per_page: String(perPage),
            });
            if (query) p.set("q", query);
            if (customOnly) p.set("custom_only", "true");
            p.set("with_anilist", "true");
            const r = await apiFetch("/api/mappings?" + p.toString());
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            items = d.items || [];
            total = d.total || 0;
            pages = d.pages || 1;
            page = d.page || page;
        } catch (e) {
            console.error("load mappings failed", e);
            toast("Failed to load mappings", "error");
        } finally {
            loading = false;
        }
    }

    function openNew() {
        form = emptyForm();
        editMode = "form";
        rawJSON = JSON.stringify(toPayload(form), null, 2);
        modal = true;
    }

    function openEdit(m: Mapping) {
        const f = emptyForm();
        f._isNew = false;
        f.anilist_id = m.anilist_id ?? "";

        function setScalarField(
            value: unknown,
            modeField: keyof Pick<EditForm, "anidb_mode" | "tvdb_mode">,
            valueField: keyof Pick<EditForm, "anidb_id" | "tvdb_id">,
        ) {
            if (value === undefined) return;
            if (value === null) {
                f[modeField] = "null";
            } else if (typeof value === "number" || typeof value === "string") {
                f[modeField] = "value";
                f[valueField] = value;
            }
        }

        function setArrayField(
            value: unknown,
            modeField: keyof Pick<
                EditForm,
                "imdb_mode" | "mal_mode" | "tmdb_movie_mode" | "tmdb_show_mode"
            >,
            csvField: keyof Pick<
                EditForm,
                "imdb_csv" | "mal_csv" | "tmdb_movie_csv" | "tmdb_show_csv"
            >,
        ) {
            if (value === undefined) return;
            if (value === null) {
                f[modeField] = "null";
            } else if (Array.isArray(value)) {
                f[modeField] = "value";
                f[csvField] = value.map((v) => String(v)).join(",");
            }
        }

        // Set scalar fields
        setScalarField(m.anidb_id, "anidb_mode", "anidb_id");
        setScalarField(m.tvdb_id, "tvdb_mode", "tvdb_id");

        // Set array fields
        setArrayField(m.imdb_id, "imdb_mode", "imdb_csv");
        setArrayField(m.mal_id, "mal_mode", "mal_csv");
        setArrayField(m.tmdb_movie_id, "tmdb_movie_mode", "tmdb_movie_csv");
        setArrayField(m.tmdb_show_id, "tmdb_show_mode", "tmdb_show_csv");

        // Handle tvdb_mappings specially
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
        editMode = "form";
        rawJSON = JSON.stringify(toPayload(f), null, 2);
    }

    function toPayload(f: EditForm) {
        const toInt = (v: unknown) => {
            if (v === "" || v == null) return null;
            const n = Number(v);
            return Number.isFinite(n) ? n : null;
        };

        function parseCSV(s: string, to: "string" | "int"): string[] | number[] | null {
            if (!s || !s.trim()) return null;
            const arr = s
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean);
            if (!arr.length) return null;
            if (to === "int") {
                const nums = arr
                    .map((x) => Number(x))
                    .filter((n) => Number.isFinite(n));
                return nums;
            }
            return arr;
        }

        const out: Mapping = { anilist_id: toInt(f.anilist_id) };

        if (f.anidb_mode === "null") out.anidb_id = null;
        else if (f.anidb_mode === "value") out.anidb_id = toInt(f.anidb_id);

        if (f.tvdb_mode === "null") out.tvdb_id = null;
        else if (f.tvdb_mode === "value") out.tvdb_id = toInt(f.tvdb_id);

        if (f.imdb_mode === "null") out.imdb_id = null;
        else if (f.imdb_mode === "value")
            out.imdb_id = parseCSV(f.imdb_csv, "string") as string[] | null;

        if (f.mal_mode === "null") out.mal_id = null;
        else if (f.mal_mode === "value")
            out.mal_id = parseCSV(f.mal_csv, "int") as number[] | null;

        if (f.tmdb_movie_mode === "null") out.tmdb_movie_id = null;
        else if (f.tmdb_movie_mode === "value")
            out.tmdb_movie_id = parseCSV(f.tmdb_movie_csv, "int") as number[] | null;

        if (f.tmdb_show_mode === "null") out.tmdb_show_id = null;
        else if (f.tmdb_show_mode === "value")
            out.tmdb_show_id = parseCSV(f.tmdb_show_csv, "int") as number[] | null;

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

    function syncFormToRaw() {
        try {
            rawJSON = JSON.stringify(toPayload(form), null, 2);
        } catch (e) {
            console.error("sync form -> raw failed", e);
        }
    }

    function isValidMapping(
        obj: unknown,
    ): obj is Partial<Mapping> & Record<string, unknown> {
        return obj !== null && typeof obj === "object";
    }

    function syncRawToForm() {
        try {
            const parsed: unknown = JSON.parse(rawJSON || "{}");
            if (!isValidMapping(parsed)) {
                throw new Error("Root must be object");
            }

            const f = emptyForm();
            f._isNew = form._isNew;
            f.anilist_id = parsed.anilist_id ?? "";

            function updateScalarField(
                value: unknown,
                modeField: "anidb_mode" | "tvdb_mode",
                valueField: "anidb_id" | "tvdb_id",
            ) {
                if (value === undefined) return;
                if (value === null) {
                    f[modeField] = "null";
                } else if (typeof value === "number" || typeof value === "string") {
                    f[modeField] = "value";
                    f[valueField] = value;
                }
            }

            function updateArrayField(
                value: unknown,
                modeField:
                    | "imdb_mode"
                    | "mal_mode"
                    | "tmdb_movie_mode"
                    | "tmdb_show_mode",
                csvField: "imdb_csv" | "mal_csv" | "tmdb_movie_csv" | "tmdb_show_csv",
            ) {
                if (value === undefined) return;
                if (value === null) {
                    f[modeField] = "null";
                } else if (Array.isArray(value)) {
                    f[modeField] = "value";
                    f[csvField] = value.map((v) => String(v)).join(",");
                }
            }

            updateScalarField(parsed.anidb_id, "anidb_mode", "anidb_id");
            updateScalarField(parsed.tvdb_id, "tvdb_mode", "tvdb_id");
            updateArrayField(parsed.imdb_id, "imdb_mode", "imdb_csv");
            updateArrayField(parsed.mal_id, "mal_mode", "mal_csv");
            updateArrayField(parsed.tmdb_movie_id, "tmdb_movie_mode", "tmdb_movie_csv");
            updateArrayField(parsed.tmdb_show_id, "tmdb_show_mode", "tmdb_show_csv");

            if (Object.prototype.hasOwnProperty.call(parsed, "tvdb_mappings")) {
                const tv = parsed.tvdb_mappings;
                if (tv === null) {
                    f.tvdb_map_mode = "null";
                } else if (tv && typeof tv === "object" && !Array.isArray(tv)) {
                    f.tvdb_map_mode = "value";
                    f.tvdb_mappings = Object.entries(tv).map(([season, pattern]) => ({
                        season,
                        pattern: String(pattern ?? ""),
                    }));
                }
            }
            form = f;
        } catch (e) {
            alert("Invalid JSON: " + (e instanceof Error ? e.message : String(e)));
        }
    }

    async function save() {
        let payload: Record<string, unknown>;
        let aid: number | null = null;
        if (editMode === "raw") {
            try {
                payload = JSON.parse(rawJSON || "{}");
            } catch (e) {
                alert("Invalid JSON: " + (e instanceof Error ? e.message : String(e)));
                return;
            }
            aid = Number(payload?.anilist_id);
            if (!aid || Number.isNaN(aid)) {
                alert("AniList ID (anilist_id) required in JSON");
                return;
            }
        } else {
            aid = Number(form.anilist_id);
            if (!aid || Number.isNaN(aid)) {
                alert("AniList ID required");
                return;
            }
            payload = toPayload(form);
        }
        const isNew = form._isNew; // creation state determined when opening modal
        const url = isNew ? "/api/mappings" : "/api/mappings/" + aid;
        const method = isNew ? "POST" : "PUT";
        try {
            const r = await apiFetch(
                url,
                {
                    method,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                },
                { successMessage: isNew ? "Mapping created" : "Mapping updated" },
            );
            if (!r.ok) throw new Error("HTTP " + r.status);
            modal = false;
            load();
        } catch (e) {
            console.error("save failed", e);
            toast("Save failed", "error");
        }
    }

    async function remove(m: Mapping) {
        if (!confirm("Delete mapping for AniList ID " + m.anilist_id + "?")) return;
        try {
            const r = await apiFetch(
                "/api/mappings/" + m.anilist_id,
                { method: "DELETE" },
                { successMessage: "Mapping deleted" },
            );
            if (!r.ok) throw new Error("HTTP " + r.status);
            load();
        } catch (e) {
            console.error("delete failed", e);
            toast("Delete failed", "error");
        }
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
        if (pref && t[pref as keyof typeof t]) {
            return t[pref as keyof typeof t] || null;
        }
        return t.romaji || t.english || t.native || null;
    }

    onMount(load);
</script>

<div class="space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="space-y-1 sm:flex-1">
            <div class="flex items-center gap-2">
                <List class="inline h-4 w-4 text-slate-300" />
                <h2 class="text-lg font-semibold">Mappings</h2>
            </div>
            <p class="text-xs text-slate-400">
                Browse and override external ID mappings
            </p>
        </div>
        <div class="hidden items-center gap-2 text-[11px] sm:flex">
            <div class="relative w-72">
                <BooruSearch
                    bind:value={query}
                    size="sm"
                    onSubmit={() => {
                        page = 1;
                        load();
                    }}
                />
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
        <!-- Mobile filters -->
        <div
            class="flex flex-col gap-3 rounded-md border border-slate-800/70 bg-slate-900/60 p-3 text-[11px] sm:hidden"
        >
            <div class="relative">
                <BooruSearch
                    bind:value={query}
                    size="md"
                    onSubmit={() => {
                        page = 1;
                        load();
                    }}
                />
            </div>
            <div class="flex flex-wrap items-center justify-between">
                <button
                    onclick={() => {
                        customOnly = !customOnly;
                        page = 1;
                        load();
                    }}
                    class={`inline-flex h-8 items-center gap-1 rounded-md px-3 text-[11px] font-medium ring-1 ${customOnly ? "bg-emerald-600/90 text-white ring-emerald-500/40 hover:bg-emerald-500" : "bg-slate-800 text-slate-300 ring-slate-700/60 hover:bg-slate-700"}`}
                >
                    {#if customOnly}
                        <Check class="inline h-3.5 w-3.5" />
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
                            <th class="px-3 py-2 text-left font-medium">TMDB (Movie)</th
                            >
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
                            <tr
                                class="align-top transition-colors hover:bg-slate-800/40"
                            >
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
                                                            >EP {m.anilist
                                                                .episodes}</span
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
                                            href={"https://anidb.net/anime/" +
                                                m.anidb_id}>{m.anidb_id}</a
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
                                                href={"https://www.themoviedb.org/tv/" +
                                                    id}>{id}</a
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
                                                href={"https://myanimelist.net/anime/" +
                                                    id}>{id}</a
                                            >{#if m.mal_id && i < m.mal_id.length - 1},
                                            {/if}{/each}{:else}-{/if}</td
                                >
                                <td class="px-3 py-2">
                                    {#key JSON.stringify(m.tvdb_mappings ?? {})}
                                        {@const entries = Object.entries(
                                            m.tvdb_mappings ?? {},
                                        )}
                                        {@const totalSeasons = entries.length}
                                        {#if totalSeasons > 0}
                                            <UiTooltip>
                                                <span
                                                    class={`inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1.5 text-[10px] ring-1 ${totalSeasons > 1 ? "bg-amber-600/30 text-amber-100 ring-amber-700/40" : "bg-slate-800/60 text-slate-300 ring-slate-700/50"}`}
                                                    slot="trigger"
                                                >
                                                    {totalSeasons}
                                                </span>
                                                <ol
                                                    class="max-h-52 space-y-1 overflow-auto text-[11px]"
                                                >
                                                    {#each entries as e (e[0])}
                                                        <li
                                                            class="flex items-start gap-1"
                                                        >
                                                            <span class="text-slate-500"
                                                                >{e[0]}</span
                                                            >
                                                            <span
                                                                class="truncate text-slate-300"
                                                                title={e[1]}
                                                            >
                                                                {e[1] || "All episodes"}
                                                            </span>
                                                        </li>
                                                    {/each}
                                                </ol>
                                            </UiTooltip>
                                        {:else}
                                            <span class="text-[10px] text-slate-500"
                                                >-</span
                                            >
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
                                                    slot="trigger"
                                                >
                                                    {total}
                                                </span>
                                                <ol class="space-y-1 text-[11px]">
                                                    {#each m.sources ?? [] as s, i (i)}
                                                        <li
                                                            class="flex items-start gap-1"
                                                        >
                                                            <span class="text-slate-500"
                                                                >{i + 1}.</span
                                                            >
                                                            <span
                                                                class="truncate"
                                                                title={s}>{s}</span
                                                            >
                                                        </li>
                                                    {/each}
                                                </ol>
                                            </UiTooltip>
                                        {:else}
                                            <span class="text-[10px] text-slate-500"
                                                >-</span
                                            >
                                        {/if}
                                    {/key}
                                </td>
                                <td class="px-3 py-2 text-right whitespace-nowrap">
                                    <div class="flex justify-end gap-1">
                                        <button
                                            onclick={() => openEdit(m)}
                                            class="inline-flex h-6 items-center rounded-md bg-slate-800 px-2 text-[11px] text-slate-200 hover:bg-slate-700"
                                            >Edit</button
                                        >
                                        <button
                                            onclick={() => remove(m)}
                                            title="Delete mapping"
                                            class="inline-flex h-6 items-center rounded-md bg-rose-700/70 px-2 text-[11px] text-rose-200 hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-35"
                                            >Del</button
                                        >
                                    </div>
                                </td>
                            </tr>
                        {/each}
                        {#if !items.length && !loading}
                            <tr
                                ><td
                                    colspan="11"
                                    class="py-8 text-center text-slate-500"
                                    >No mappings found</td
                                ></tr
                            >
                        {/if}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
        {#if pages > 1}
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
        {/if}
        <span class="ml-auto flex items-center gap-2">
            <label for="perPageBottom" class="text-[11px] text-slate-400"
                >Per Page</label
            >
            <select
                id="perPageBottom"
                bind:value={perPage}
                class="h-8 rounded-md border border-slate-700/70 bg-slate-950/70 px-2 text-[11px] shadow-sm focus:border-slate-600 focus:bg-slate-950"
                onchange={() => ((page = 1), load())}
            >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
            </select>
        </span>
    </div>

    {#if modal}
        <Modal bind:open={modal} onOpenAutoFocus={(e: Event) => e.preventDefault()}>
            <svelte:fragment slot="title">
                <div
                    class="flex items-center gap-2 text-sm font-semibold tracking-wide"
                >
                    <PenLine class="inline h-4 w-4 text-slate-400" />
                    {form._isNew ? "New Override" : "Edit Override #" + form.anilist_id}
                </div>
            </svelte:fragment>

            <div class="max-h-[calc(100vh-6rem)] space-y-3 overflow-auto p-4">
                <Tabs.Root
                    value={editMode}
                    onValueChange={(v: string) => {
                        const next = v as typeof editMode;
                        if (next === "raw" && editMode !== "raw") {
                            syncFormToRaw();
                        }
                        if (next === "form" && editMode !== "form") {
                            syncRawToForm();
                        }
                        editMode = next;
                    }}
                >
                    <Tabs.List class="flex gap-2 text-[11px]">
                        <Tabs.Trigger
                            value="form"
                            class="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-slate-400 ring-1 ring-slate-700 transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-emerald-500/50 data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-300 data-[state=active]:ring-slate-600"
                            >Form</Tabs.Trigger
                        >
                        <Tabs.Trigger
                            value="raw"
                            class="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-slate-400 ring-1 ring-slate-700 transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-emerald-500/50 data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-300 data-[state=active]:ring-slate-600"
                            >Raw JSON</Tabs.Trigger
                        >
                    </Tabs.List>
                    <Tabs.Content value="form" class="mt-3 space-y-2">
                        <div
                            class="rounded-md border border-slate-700/50 bg-slate-950/40 p-3"
                        >
                            <div class="mb-2 flex items-center justify-between">
                                <span
                                    class="text-[10px] font-medium tracking-wide text-slate-400 uppercase"
                                    >JSON Preview</span
                                >
                                <button
                                    class="rounded bg-slate-800 px-2 py-0.5 text-[9px] text-slate-300 hover:bg-slate-700"
                                    onclick={syncFormToRaw}
                                    title="Refresh preview"
                                >
                                    Refresh
                                </button>
                            </div>
                            <JsonCodeBlock
                                value={toPayload(form)}
                                maxHeight="max-h-32"
                            />
                        </div>
                        <div class="space-y-2">
                            <div class="flex items-center gap-2">
                                <label
                                    for="f-anilist"
                                    class="text-[11px] text-slate-400">AniList ID</label
                                ><input
                                    id="f-anilist"
                                    bind:value={form.anilist_id}
                                    type="number"
                                    class="h-8 w-full flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={!form._isNew}
                                />
                            </div>
                            <div class="grid grid-cols-2 gap-3">
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
                                            ><option value="value">Value</option
                                            ></select
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
                                            ><option value="value">Value</option
                                            ></select
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
                                            >IMDB IDs <span
                                                class="text-xs text-slate-500"
                                                >(comma separated)</span
                                            ></label
                                        ><select
                                            id="f-imdb-mode"
                                            bind:value={form.imdb_mode}
                                            class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                            ><option value="omit">Omit</option><option
                                                value="null">Null</option
                                            ><option value="value">Value</option
                                            ></select
                                        >
                                    </div>
                                    <input
                                        bind:value={form.imdb_csv}
                                        type="text"
                                        class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                        disabled={form.imdb_mode !== "value"}
                                    />
                                </div>
                                <div class="col-span-2">
                                    <div class="flex items-center justify-between">
                                        <label
                                            for="f-mal-mode"
                                            class="text-[11px] text-slate-400"
                                            >MAL IDs <span
                                                class="text-xs text-slate-500"
                                                >(comma separated)</span
                                            ></label
                                        ><select
                                            id="f-mal-mode"
                                            bind:value={form.mal_mode}
                                            class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                            ><option value="omit">Omit</option><option
                                                value="null">Null</option
                                            ><option value="value">Value</option
                                            ></select
                                        >
                                    </div>
                                    <input
                                        bind:value={form.mal_csv}
                                        type="text"
                                        class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                        disabled={form.mal_mode !== "value"}
                                    />
                                </div>
                                <div class="col-span-2">
                                    <div class="flex items-center justify-between">
                                        <label
                                            for="f-tmdb-movie-mode"
                                            class="text-[11px] text-slate-400"
                                            >TMDB Movie IDs <span
                                                class="text-xs text-slate-500"
                                                >(comma separated)</span
                                            ></label
                                        ><select
                                            id="f-tmdb-movie-mode"
                                            bind:value={form.tmdb_movie_mode}
                                            class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                            ><option value="omit">Omit</option><option
                                                value="null">Null</option
                                            ><option value="value">Value</option
                                            ></select
                                        >
                                    </div>
                                    <input
                                        bind:value={form.tmdb_movie_csv}
                                        type="text"
                                        class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                        disabled={form.tmdb_movie_mode !== "value"}
                                    />
                                </div>
                                <div class="col-span-2">
                                    <div class="flex items-center justify-between">
                                        <label
                                            for="f-tmdb-show-mode"
                                            class="text-[11px] text-slate-400"
                                            >TMDB Show IDs <span
                                                class="text-xs text-slate-500"
                                                >(comma separated)</span
                                            ></label
                                        ><select
                                            id="f-tmdb-show-mode"
                                            bind:value={form.tmdb_show_mode}
                                            class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                            ><option value="omit">Omit</option><option
                                                value="null">Null</option
                                            ><option value="value">Value</option
                                            ></select
                                        >
                                    </div>
                                    <input
                                        bind:value={form.tmdb_show_csv}
                                        type="text"
                                        class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                        disabled={form.tmdb_show_mode !== "value"}
                                    />
                                </div>
                                <div class="col-span-2">
                                    <div class="flex items-center justify-between">
                                        <label
                                            for="f-tvdb-map-mode"
                                            class="text-[11px] text-slate-400"
                                            >TVDB Season Mappings</label
                                        ><select
                                            id="f-tvdb-map-mode"
                                            bind:value={form.tvdb_map_mode}
                                            class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]"
                                            ><option value="omit">Omit</option><option
                                                value="null">Null</option
                                            ><option value="value">Value</option
                                            ></select
                                        >
                                    </div>
                                    {#if form.tvdb_map_mode === "value"}
                                        <div class="mt-2 space-y-2">
                                            {#each form.tvdb_mappings as mapping, i (i)}
                                                <div class="flex items-center gap-2">
                                                    <input
                                                        bind:value={mapping.season}
                                                        placeholder="Season (e.g., s1, s2)"
                                                        class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]"
                                                    />
                                                    <input
                                                        bind:value={mapping.pattern}
                                                        placeholder="Pattern"
                                                        class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]"
                                                    />
                                                    <button
                                                        onclick={() => {
                                                            form.tvdb_mappings.splice(
                                                                i,
                                                                1,
                                                            );
                                                            form.tvdb_mappings = [
                                                                ...form.tvdb_mappings,
                                                            ];
                                                        }}
                                                        class="inline-flex h-7 w-7 items-center justify-center rounded-md bg-rose-700/70 text-rose-200 hover:bg-rose-600"
                                                        title="Remove mapping"
                                                    >
                                                        <X class="h-3 w-3" />
                                                    </button>
                                                </div>
                                            {/each}
                                            <button
                                                onclick={() => {
                                                    form.tvdb_mappings.push({
                                                        season: "",
                                                        pattern: "",
                                                    });
                                                    form.tvdb_mappings = [
                                                        ...form.tvdb_mappings,
                                                    ];
                                                }}
                                                class="inline-flex h-7 items-center gap-1 rounded-md bg-slate-800 px-2 text-[11px] text-slate-300 hover:bg-slate-700"
                                            >
                                                <Plus class="h-3 w-3" />
                                                Add Mapping
                                            </button>
                                        </div>
                                    {/if}
                                </div>
                            </div>
                        </div>
                    </Tabs.Content>
                    <Tabs.Content value="raw" class="mt-3 space-y-2">
                        <div
                            class="flex items-center justify-between text-[11px] text-slate-400"
                        >
                            <span>Raw Mapping JSON</span>
                            <button
                                class="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-700"
                                onclick={syncFormToRaw}>Refresh from Form</button
                            >
                        </div>
                        <textarea
                            bind:value={rawJSON}
                            class="h-72 w-full resize-none rounded-md border border-slate-700 bg-slate-950/80 px-2 py-2 font-mono text-[11px] leading-snug text-slate-200 focus:border-emerald-600 focus:outline-none"
                            spellcheck={false}
                        ></textarea>
                        <p class="text-[10px] text-slate-500">
                            Provide a JSON object. Required: <code class="font-mono"
                                >anilist_id</code
                            >. Unknown keys will be sent as-is.
                        </p>
                    </Tabs.Content>
                </Tabs.Root>
                <div class="flex justify-end gap-2 pt-1">
                    <button
                        class="rounded-md bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
                        onclick={() => (modal = false)}
                    >
                        Cancel
                    </button>
                    <button
                        onclick={save}
                        class="rounded-md bg-emerald-600/90 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
                    >
                        Save
                    </button>
                </div>
            </div>
        </Modal>
    {/if}
</div>
