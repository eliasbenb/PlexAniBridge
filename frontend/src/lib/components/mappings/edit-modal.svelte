<script lang="ts">
    import { PenLine, Plus, X } from "@lucide/svelte";
    import { Tabs } from "bits-ui";
    import type * as Monaco from "monaco-editor/esm/vs/editor/editor.api";

    import CodeEditor from "$lib/components/code-editor.svelte";
    import JsonCodeBlock from "$lib/components/json-code-block.svelte";
    import type { Mapping } from "$lib/types/api";
    import Modal from "$lib/ui/modal.svelte";

    export interface Props {
        form: EditForm;
        open: boolean;
        editMode: "form" | "raw";
        rawJSON: string;
        save: () => void;
        syncFormToRaw: () => void;
        syncRawToForm: () => void;
        toPayload: (f: EditForm) => Mapping;
    }

    let {
        form = $bindable<EditForm>(),
        open = $bindable(false),
        editMode = $bindable("form"),
        rawJSON = $bindable(""),
        toPayload,
        syncFormToRaw,
        syncRawToForm,
        save,
    }: Props = $props();

    export type FieldMode = "omit" | "null" | "value";
    export interface EpisodeMapRow {
        season: string;
        pattern: string;
    }
    export interface EditForm {
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
        tmdb_map_mode: FieldMode;
        tmdb_mappings: EpisodeMapRow[];
        tvdb_map_mode: FieldMode;
        tvdb_mappings: EpisodeMapRow[];
    }

    function addTmdbMapping() {
        form.tmdb_mappings.push({ season: "", pattern: "" });
        form.tmdb_mappings = [...form.tmdb_mappings];
    }
    function removeTmdbMapping(i: number) {
        form.tmdb_mappings.splice(i, 1);
        form.tmdb_mappings = [...form.tmdb_mappings];
    }

    function addTvdbMapping() {
        form.tvdb_mappings.push({ season: "", pattern: "" });
        form.tvdb_mappings = [...form.tvdb_mappings];
    }
    function removeTvdbMapping(i: number) {
        form.tvdb_mappings.splice(i, 1);
        form.tvdb_mappings = [...form.tvdb_mappings];
    }

    const mappingSchema: Monaco.languages.json.JSONSchema = {
        title: "PlexAniBridge Mapping Override",
        type: "object",
        required: ["anilist_id"],
        additionalProperties: false,
        properties: {
            anilist_id: {
                type: ["integer"],
                description: "The AniList ID",
                examples: [12345],
            },
            anidb_id: {
                type: ["integer", "null"],
                description: "The AniDB ID",
                examples: [12345],
            },
            imdb_id: {
                anyOf: [
                    {
                        type: "array",
                        items: { type: "string", pattern: "^tt[0-9]{7,}$" },
                    },
                    { type: "null" },
                ],
                description: "Array of IMDB IDs in the format tt1234567",
                examples: [["tt1234567", "tt7654321"]],
            },
            mal_id: {
                anyOf: [
                    { type: "array", items: { type: "integer" } },
                    { type: "null" },
                ],
                description: "Array of MyAnimeList IDs",
                examples: [[12345, 67890]],
            },
            tmdb_movie_id: {
                anyOf: [
                    { type: "array", items: { type: "integer" } },
                    { type: "null" },
                ],
                description: "Array of TMDB movie IDs",
                examples: [[12345, 67890]],
            },
            tmdb_show_id: {
                anyOf: [
                    { type: "array", items: { type: "integer" } },
                    { type: "null" },
                ],
                description: "Array of TMDB show IDs",
                examples: [[12345, 67890]],
            },
            tvdb_id: { type: ["integer", "null"] },
            tmdb_mappings: {
                type: "object",
                patternProperties: {
                    "^s[0-9]+$": {
                        type: "string",
                        description: "TMDB episode mappings pattern",
                        examples: ["e1-e12"],
                    },
                },
                additionalProperties: false,
                description: "Season to episode mapping patterns",
                examples: [{ s1: "e1-e12", s2: "e13-e24" }],
            },
            tvdb_mappings: {
                type: "object",
                patternProperties: {
                    "^s[0-9]+$": {
                        type: "string",
                        description: "TVDB episode mappings pattern",
                        examples: ["e1-e12"],
                    },
                },
                additionalProperties: false,
                description: "Season to episode mapping patterns",
                examples: [{ s1: "e1-e12", s2: "e13-e24" }],
            },
        },
    };
</script>

{#if open}
    <Modal
        bind:open
        onOpenAutoFocus={(e: Event) => e.preventDefault()}>
        {#snippet titleChildren()}
            <div class="flex items-center gap-2 text-sm font-semibold tracking-wide">
                <PenLine class="inline h-4 w-4 text-slate-400" />
                {form._isNew ? "New Override" : "Edit Override #" + form.anilist_id}
            </div>
        {/snippet}
        <div class="max-h-[calc(100vh-6rem)] space-y-3 overflow-auto p-4">
            <Tabs.Root
                value={editMode}
                onValueChange={(v: string) => {
                    const next = v as typeof editMode;
                    if (next === "raw" && editMode !== "raw") syncFormToRaw();
                    if (next === "form" && editMode !== "form") syncRawToForm();
                    editMode = next;
                }}>
                <Tabs.List class="flex gap-2 text-[11px]">
                    <Tabs.Trigger
                        value="form"
                        class="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-slate-400 ring-1 ring-slate-700 transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-emerald-500/50 data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-300 data-[state=active]:ring-slate-600"
                        >Form</Tabs.Trigger>
                    <Tabs.Trigger
                        value="raw"
                        class="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-slate-400 ring-1 ring-slate-700 transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-emerald-500/50 data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-300 data-[state=active]:ring-slate-600"
                        >Raw JSON</Tabs.Trigger>
                </Tabs.List>
                <Tabs.Content
                    value="form"
                    class="mt-3 space-y-2">
                    <div
                        class="rounded-md border border-slate-700/50 bg-slate-950/40 p-3">
                        <div class="mb-2 flex items-center justify-between">
                            <span
                                class="text-[10px] font-medium tracking-wide text-slate-400 uppercase"
                                >JSON Preview</span>
                            <button
                                class="rounded bg-slate-800 px-2 py-0.5 text-[9px] text-slate-300 hover:bg-slate-700"
                                onclick={syncFormToRaw}
                                title="Refresh preview">Refresh</button>
                        </div>
                        <JsonCodeBlock
                            value={toPayload(form)}
                            class="max-h-32" />
                    </div>
                    <div class="space-y-2">
                        <div class="flex items-center gap-2">
                            <label
                                for="f-anilist"
                                class="text-[11px] text-slate-400">AniList ID</label>
                            <input
                                id="f-anilist"
                                bind:value={form.anilist_id}
                                type="number"
                                class="h-8 w-full flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                                disabled={!form._isNew} />
                        </div>
                        <!-- Scalar + Array fields grid -->
                        <div class="grid grid-cols-2 gap-3">
                            <!-- AniDB -->
                            <div>
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-anidb-mode"
                                        class="text-[11px] text-slate-400"
                                        >AniDB ID</label>
                                    <select
                                        id="f-anidb-mode"
                                        bind:value={form.anidb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.anidb_id}
                                    type="number"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.anidb_mode !== "value"} />
                            </div>
                            <!-- TVDB -->
                            <div>
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tvdb-mode"
                                        class="text-[11px] text-slate-400"
                                        >TVDB ID</label>
                                    <select
                                        id="f-tvdb-mode"
                                        bind:value={form.tvdb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.tvdb_id}
                                    type="number"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.tvdb_mode !== "value"} />
                            </div>
                            <!-- IMDB -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-imdb-mode"
                                        class="text-[11px] text-slate-400"
                                        >IMDB IDs <span class="text-xs text-slate-500"
                                            >(comma separated)</span
                                        ></label>
                                    <select
                                        id="f-imdb-mode"
                                        bind:value={form.imdb_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.imdb_csv}
                                    type="text"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.imdb_mode !== "value"} />
                            </div>
                            <!-- MAL -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-mal-mode"
                                        class="text-[11px] text-slate-400"
                                        >MAL IDs <span class="text-xs text-slate-500"
                                            >(comma separated)</span
                                        ></label>
                                    <select
                                        id="f-mal-mode"
                                        bind:value={form.mal_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.mal_csv}
                                    type="text"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.mal_mode !== "value"} />
                            </div>
                            <!-- TMDB Movie -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tmdb-movie-mode"
                                        class="text-[11px] text-slate-400"
                                        >TMDB Movie IDs <span
                                            class="text-xs text-slate-500"
                                            >(comma separated)</span
                                        ></label>
                                    <select
                                        id="f-tmdb-movie-mode"
                                        bind:value={form.tmdb_movie_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.tmdb_movie_csv}
                                    type="text"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.tmdb_movie_mode !== "value"} />
                            </div>
                            <!-- TMDB Show -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tmdb-show-mode"
                                        class="text-[11px] text-slate-400"
                                        >TMDB Show IDs <span
                                            class="text-xs text-slate-500"
                                            >(comma separated)</span
                                        ></label>
                                    <select
                                        id="f-tmdb-show-mode"
                                        bind:value={form.tmdb_show_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                <input
                                    bind:value={form.tmdb_show_csv}
                                    type="text"
                                    class="mt-1 h-8 w-full rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                                    disabled={form.tmdb_show_mode !== "value"} />
                            </div>
                            <!-- TMDB Season Mappings -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tmdb-map-mode"
                                        class="text-[11px] text-slate-400"
                                        >TMDB Season Mappings</label>
                                    <select
                                        id="f-tmdb-map-mode"
                                        bind:value={form.tmdb_map_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                {#if form.tmdb_map_mode === "value"}
                                    <div class="mt-2 space-y-2">
                                        {#each form.tmdb_mappings as mapping, i (i)}
                                            <div class="flex items-center gap-2">
                                                <input
                                                    bind:value={mapping.season}
                                                    placeholder="Season (e.g., s1, s2)"
                                                    class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]" />
                                                <input
                                                    bind:value={mapping.pattern}
                                                    placeholder="Pattern"
                                                    class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]" />
                                                <button
                                                    onclick={() => removeTmdbMapping(i)}
                                                    class="inline-flex h-7 w-7 items-center justify-center rounded-md bg-rose-700/70 text-rose-200 hover:bg-rose-600"
                                                    title="Remove mapping"
                                                    ><X class="h-3 w-3" /></button>
                                            </div>
                                        {/each}
                                        <button
                                            onclick={addTmdbMapping}
                                            class="inline-flex h-7 items-center gap-1 rounded-md bg-slate-800 px-2 text-[11px] text-slate-300 hover:bg-slate-700"
                                            ><Plus class="h-3 w-3" />Add Mapping</button>
                                    </div>
                                {/if}
                            </div>
                            <!-- TVDB Season Mappings -->
                            <div class="col-span-2">
                                <div class="flex items-center justify-between">
                                    <label
                                        for="f-tvdb-map-mode"
                                        class="text-[11px] text-slate-400"
                                        >TVDB Season Mappings</label>
                                    <select
                                        id="f-tvdb-map-mode"
                                        bind:value={form.tvdb_map_mode}
                                        class="h-7 rounded-md border border-slate-700 bg-slate-900 px-2 text-[11px]">
                                        <option value="omit">Omit</option><option
                                            value="null">Null</option
                                        ><option value="value">Value</option>
                                    </select>
                                </div>
                                {#if form.tvdb_map_mode === "value"}
                                    <div class="mt-2 space-y-2">
                                        {#each form.tvdb_mappings as mapping, i (i)}
                                            <div class="flex items-center gap-2">
                                                <input
                                                    bind:value={mapping.season}
                                                    placeholder="Season (e.g., s1, s2)"
                                                    class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]" />
                                                <input
                                                    bind:value={mapping.pattern}
                                                    placeholder="Pattern"
                                                    class="h-7 flex-1 rounded-md border border-slate-800 bg-slate-950/80 px-2 text-[11px]" />
                                                <button
                                                    onclick={() => removeTvdbMapping(i)}
                                                    class="inline-flex h-7 w-7 items-center justify-center rounded-md bg-rose-700/70 text-rose-200 hover:bg-rose-600"
                                                    title="Remove mapping"
                                                    ><X class="h-3 w-3" /></button>
                                            </div>
                                        {/each}
                                        <button
                                            onclick={addTvdbMapping}
                                            class="inline-flex h-7 items-center gap-1 rounded-md bg-slate-800 px-2 text-[11px] text-slate-300 hover:bg-slate-700"
                                            ><Plus class="h-3 w-3" />Add Mapping</button>
                                    </div>
                                {/if}
                            </div>
                        </div>
                    </div>
                </Tabs.Content>
                <Tabs.Content
                    value="raw"
                    class="mt-3 space-y-2">
                    <div
                        class="flex items-center justify-between text-[11px] text-slate-400">
                        <span>Raw Mapping JSON</span>
                        <button
                            class="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-700"
                            onclick={syncFormToRaw}>Refresh from Form</button>
                    </div>
                    <CodeEditor
                        bind:value={rawJSON}
                        language="json"
                        class="h-96"
                        jsonSchema={mappingSchema} />
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
                    onclick={() => (open = false)}>Cancel</button>
                <button
                    onclick={save}
                    class="rounded-md bg-emerald-600/90 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
                    >Save
                </button>
            </div>
        </div>
    </Modal>
{/if}
