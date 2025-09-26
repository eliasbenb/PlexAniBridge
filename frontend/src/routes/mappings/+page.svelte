<script lang="ts">
    import { onMount } from "svelte";

    import { List } from "@lucide/svelte";
    import { SvelteURLSearchParams } from "svelte/reactivity";

    import EditModal from "$lib/components/mappings/edit-modal.svelte";
    import MappingsTable from "$lib/components/mappings/mappings-table.svelte";
    import SearchBar from "$lib/components/mappings/tool-bar.svelte";
    import Pagination from "$lib/components/pagination.svelte";
    import type { Mapping } from "$lib/types/api";
    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

    let items: Mapping[] = $state([]);
    let total = $state(0);
    let page = $state(1);
    let pages = $state(1);
    let perPage = $state(25);
    let query = $state("");
    let customOnly = $state(false);
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

        const aid = toInt(f.anilist_id);
        const out: Partial<Mapping> = {};
        if (aid !== null) out.anilist_id = aid;

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
        return out as Mapping; // caller ensures anilist_id present before send
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
            payload = toPayload(form) as unknown as Record<string, unknown>;
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
        <SearchBar
            bind:query
            bind:customOnly
            bind:page
            onLoad={load}
            onNew={openNew} />
    </div>
    <div
        class="relative flex h-[70vh] flex-col overflow-hidden rounded-md border border-slate-800/70 bg-slate-900/40 backdrop-blur-sm">
        <div
            class="flex items-center gap-4 border-b border-slate-800/60 bg-slate-950/50 px-3 py-2 text-[11px]">
            <span class="text-slate-400"
                >Showing <span class="font-medium text-slate-200">{items.length}</span
                >/<span class="text-slate-500">{total}</span></span>
            {#if pages > 1}<span class="text-slate-500">Page {page} / {pages}</span
                >{/if}
            {#if customOnly}<span class="text-emerald-400">Custom overrides only</span
                >{/if}
        </div>
        <MappingsTable
            {items}
            onEdit={openEdit}
            onDelete={remove} />
    </div>
    <Pagination
        class="mt-3"
        bind:page
        bind:perPage
        bind:pages
        onChange={load} />

    <EditModal
        bind:open={modal}
        bind:form
        bind:editMode
        bind:rawJSON
        {toPayload}
        {syncFormToRaw}
        {syncRawToForm}
        {save} />
</div>
