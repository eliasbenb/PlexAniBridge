<script lang="ts">
    import { Globe, Loader2, Plus, Trash2 } from "@lucide/svelte";
    import { Tabs } from "bits-ui";
    import type * as Monaco from "monaco-editor/esm/vs/editor/editor.api";

    import CodeEditor from "$lib/components/code-editor.svelte";
    import type {
        Mapping,
        MappingDetail,
        MappingOverrideFieldInput,
        MappingOverrideMode,
        MappingOverridePayload,
    } from "$lib/types/api";
    import Modal from "$lib/ui/modal.svelte";
    import { preferredTitle } from "$lib/utils/anilist";
    import { apiFetch, isAbortError } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

    interface SeasonRow {
        season: string;
        value: string;
    }

    type OverrideFieldType = "number" | "number_list" | "string_list" | "season";

    interface OverrideFieldDefinition {
        id: string;
        label: string;
        type: OverrideFieldType;
        placeholder?: string;
        hint?: string;
    }

    interface Props {
        open: boolean;
        mode?: "create" | "edit";
        mapping?: Mapping | null;
        onSaved?: (detail: MappingDetail) => void;
    }

    let {
        open = $bindable(false),
        mode = "create",
        mapping = null,
        onSaved,
    }: Props = $props();

    const FIELD_DEFS: OverrideFieldDefinition[] = [
        {
            id: "anidb_id",
            label: "AniDB ID",
            type: "number",
            placeholder: "e.g. 12345",
        },
        {
            id: "imdb_id",
            label: "IMDb IDs",
            type: "string_list",
            placeholder: "tt12345, tt67890",
        },
        {
            id: "mal_id",
            label: "MyAnimeList IDs",
            type: "number_list",
            placeholder: "12345, 67890",
        },
        {
            id: "tmdb_movie_id",
            label: "TMDB Movie IDs",
            type: "number_list",
            placeholder: "12345, 67890",
        },
        {
            id: "tmdb_show_id",
            label: "TMDB Show ID",
            type: "number",
            placeholder: "12345",
        },
        { id: "tvdb_id", label: "TVDB ID", type: "number", placeholder: "12345" },
        {
            id: "tmdb_mappings",
            label: "TMDB Season Mappings",
            type: "season",
            hint: "Season key (e.g. s1) mapped to episode pattern",
        },
        {
            id: "tvdb_mappings",
            label: "TVDB Season Mappings",
            type: "season",
            hint: "Season key (e.g. s1) mapped to episode pattern",
        },
    ];

    type FieldId = (typeof FIELD_DEFS)[number]["id"];
    type FieldStateValue = string | SeasonRow[];

    interface FieldState {
        mode: MappingOverrideMode;
        value: FieldStateValue;
    }

    type FieldStateMap = Record<FieldId, FieldState>;

    const jsonSchema: Monaco.languages.json.JSONSchema = {
        title: "PlexAniBridge Mapping Override",
        type: "object",
        required: ["anilist_id"],
        additionalProperties: false,
        properties: {
            anilist_id: { type: ["integer", "null"], description: "The AniList ID" },
            anidb_id: { type: ["integer", "null"], description: "The AniDB ID" },
            imdb_id: {
                anyOf: [
                    {
                        type: "array",
                        items: { type: "string", pattern: "^tt[0-9]{7,}$" },
                    },
                    { type: "null" },
                ],
                description: "Array of IMDB IDs in the format tt1234567 (or null)",
            },
            mal_id: {
                anyOf: [
                    { type: "array", items: { type: "integer" } },
                    { type: "null" },
                ],
                description: "Array of MyAnimeList IDs (or null)",
            },
            tmdb_movie_id: {
                anyOf: [
                    { type: "array", items: { type: "integer" } },
                    { type: "null" },
                ],
                description: "Array of TMDB movie IDs (or null)",
            },
            tmdb_show_id: {
                type: ["integer", "null"],
                description: "The TMDB Show ID",
            },
            tvdb_id: { type: ["integer", "null"], description: "The TVDB ID" },
            tmdb_mappings: {
                anyOf: [
                    {
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
                    },
                    { type: "null" },
                ],
            },
            tvdb_mappings: {
                anyOf: [
                    {
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
                    },
                    { type: "null" },
                ],
            },
        },
    };

    const MODE_OPTIONS: MappingOverrideMode[] = ["omit", "null", "value"];

    function defaultValueFor(type: OverrideFieldType): FieldStateValue {
        return type === "season" ? [] : "";
    }

    function createEmptyFieldState(): FieldStateMap {
        const state: FieldStateMap = {} as FieldStateMap;
        for (const def of FIELD_DEFS) {
            state[def.id] = { mode: "omit", value: defaultValueFor(def.type) };
        }
        return state;
    }

    let fieldState = $state<FieldStateMap>(createEmptyFieldState());
    let detail = $state<MappingDetail | null>(null);
    let anilistIdInput = $state<string>("");
    let activeTab = $state<"form" | "json">("form");
    let rawJson = $state<string>("{}");
    let formError = $state<string | null>(null);
    let jsonError = $state<string | null>(null);
    let loadingDetail = $state(false);
    let saving = $state(false);
    let loadedDetailId: number | null = null;
    let initialised = $state(false);
    let currentAbort: AbortController | null = null;

    function updateFieldStateFromOverride(
        override: Record<string, unknown> | null,
    ): void {
        const next = createEmptyFieldState();
        for (const def of FIELD_DEFS) {
            const value = override ? override[def.id] : undefined;
            if (value === undefined) {
                continue;
            }
            if (value === null) {
                next[def.id] = { mode: "null", value: defaultValueFor(def.type) };
                continue;
            }
            next[def.id] = {
                mode: "value",
                value: convertOverrideToStateValue(def, value),
            };
        }
        fieldState = next;
    }

    function convertOverrideToStateValue(
        def: OverrideFieldDefinition,
        value: unknown,
    ): FieldStateValue {
        if (def.type === "season") {
            if (!value || typeof value !== "object") return [];
            return Object.entries(value as Record<string, string | null>).map(
                ([season, pattern]) => ({
                    season,
                    value: pattern ? String(pattern) : "",
                }),
            );
        }
        if (Array.isArray(value)) {
            return value.map((item) => String(item)).join(", ");
        }
        return value == null ? "" : String(value);
    }

    function setFieldMode(fieldId: FieldId, modeValue: MappingOverrideMode) {
        const def = FIELD_DEFS.find((f) => f.id === fieldId);
        if (!def) return;
        const current = fieldState[fieldId];
        const previousMode = current?.mode ?? "omit";
        let nextValue: FieldStateValue = current?.value ?? defaultValueFor(def.type);

        if (modeValue === "value") {
            if (def.type === "season") {
                let rows = Array.isArray(nextValue)
                    ? (nextValue as SeasonRow[]).map((row) => ({ ...row }))
                    : [];
                if (previousMode !== "value" || !rows.length) {
                    const effectiveRows = getEffectiveSeasonRows(def);
                    if (effectiveRows.length) {
                        rows = effectiveRows;
                    }
                }
                if (!rows.length) {
                    rows = [{ season: "", value: "" }];
                }
                nextValue = rows;
            } else if (previousMode !== "value") {
                const effectiveValue = getEffectiveStateValue(def);
                if (typeof effectiveValue === "string") {
                    nextValue = effectiveValue;
                } else if (typeof nextValue === "string") {
                    nextValue = "";
                } else {
                    nextValue = defaultValueFor(def.type);
                }
            }
        } else {
            nextValue = defaultValueFor(def.type);
        }

        fieldState = {
            ...fieldState,
            [fieldId]: { mode: modeValue, value: nextValue },
        };
    }

    function setFieldStringValue(fieldId: FieldId, value: string) {
        if (!fieldState[fieldId]) return;
        fieldState = { ...fieldState, [fieldId]: { ...fieldState[fieldId], value } };
    }

    function addSeasonRow(fieldId: FieldId) {
        const state = fieldState[fieldId];
        if (!state) return;
        const rows = Array.isArray(state.value)
            ? [...(state.value as SeasonRow[])]
            : [];
        rows.push({ season: "", value: "" });
        fieldState = { ...fieldState, [fieldId]: { ...state, value: rows } };
    }

    function updateSeasonRow(
        fieldId: FieldId,
        index: number,
        key: keyof SeasonRow,
        value: string,
    ) {
        const state = fieldState[fieldId];
        if (!state || !Array.isArray(state.value)) return;
        const rows = [...state.value];
        rows[index] = { ...rows[index], [key]: value };
        fieldState = { ...fieldState, [fieldId]: { ...state, value: rows } };
    }

    function removeSeasonRow(fieldId: FieldId, index: number) {
        const state = fieldState[fieldId];
        if (!state || !Array.isArray(state.value)) return;
        const rows = [...state.value];
        rows.splice(index, 1);
        fieldState = { ...fieldState, [fieldId]: { ...state, value: rows } };
    }

    function formatEffective(def: OverrideFieldDefinition): string {
        if (!detail) return "unknown";
        const value = (detail as unknown as Record<string, unknown>)[def.id];
        if (value === undefined) return "unknown";
        if (value === null) return "null";
        if (def.type === "season") {
            if (typeof value !== "object" || value === null) return "-";
            const entries = Object.entries(value as Record<string, string | null>);
            if (!entries.length) return "-";
            return entries
                .map(([season, pattern]) => `${season}: ${pattern ?? ""}`)
                .join(", ");
        }
        if (Array.isArray(value)) {
            return value.join(", ");
        }
        return String(value);
    }

    function getEffectiveStateValue(
        def: OverrideFieldDefinition,
    ): FieldStateValue | null {
        if (!detail) return null;
        const value = (detail as unknown as Record<string, unknown>)[def.id];
        if (value === undefined || value === null) {
            return null;
        }
        const converted = convertOverrideToStateValue(def, value);
        if (def.type === "season") {
            const rows = Array.isArray(converted) ? (converted as SeasonRow[]) : [];
            return rows.map((row) => ({ ...row }));
        }
        return typeof converted === "string" ? converted : String(converted ?? "");
    }

    function getEffectiveSeasonRows(def: OverrideFieldDefinition): SeasonRow[] {
        if (def.type !== "season") return [];
        const value = getEffectiveStateValue(def);
        return Array.isArray(value)
            ? (value as SeasonRow[]).map((row) => ({ ...row }))
            : [];
    }

    function parseNumberList(input: string): number[] {
        const tokens = input
            .split(/[\s,]+/)
            .map((token) => token.trim())
            .filter(Boolean);
        const result: number[] = [];
        for (const token of tokens) {
            const parsed = Number(token);
            if (!Number.isInteger(parsed)) {
                throw new Error(`Invalid integer '${token}'`);
            }
            result.push(parsed);
        }
        return result;
    }

    function parseStringList(input: string): string[] {
        return input
            .split(/[\s,]+/)
            .map((token) => token.trim())
            .filter(Boolean);
    }

    function buildSeasonMapping(rows: SeasonRow[]): Record<string, string> {
        const mapping: Record<string, string> = {};
        for (const row of rows) {
            const season = row.season.trim();
            const value = row.value.trim();
            if (!season && !value) continue;
            if (!season) {
                throw new Error("Season key is required (e.g. s1)");
            }
            mapping[season] = value;
        }
        return mapping;
    }

    function buildFieldsPayload(): Record<string, MappingOverrideFieldInput> {
        const payload: Record<string, MappingOverrideFieldInput> = {};
        for (const def of FIELD_DEFS) {
            const state = fieldState[def.id];
            if (!state || state.mode === "omit") continue;
            if (state.mode === "null") {
                payload[def.id] = { mode: "null" };
                continue;
            }
            if (def.type === "season") {
                payload[def.id] = {
                    mode: "value",
                    value: buildSeasonMapping((state.value as SeasonRow[]) || []),
                };
                continue;
            }
            const valueText = String(state.value || "").trim();
            if (def.type === "number") {
                if (!valueText) {
                    throw new Error(`${def.label}: value is required`);
                }
                const parsed = Number(valueText);
                if (!Number.isInteger(parsed)) {
                    throw new Error(`${def.label}: value must be an integer`);
                }
                payload[def.id] = { mode: "value", value: parsed };
                continue;
            }
            if (def.type === "number_list") {
                payload[def.id] = {
                    mode: "value",
                    value: valueText ? parseNumberList(valueText) : [],
                };
                continue;
            }
            if (def.type === "string_list") {
                payload[def.id] = {
                    mode: "value",
                    value: valueText ? parseStringList(valueText) : [],
                };
            }
        }
        return payload;
    }

    function normaliseOverride(
        override: Record<string, unknown> | null | undefined,
    ): Record<string, unknown> {
        return override ? { ...override } : {};
    }

    function parseAnilistIdValue(value: unknown): number | null {
        if (value == null) return null;
        if (typeof value === "number") {
            return Number.isInteger(value) && value > 0 ? value : null;
        }
        if (typeof value === "string") {
            const parsed = Number(value.trim());
            return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
        }
        const coerced = Number(value);
        return Number.isInteger(coerced) && coerced > 0 ? coerced : null;
    }

    function resolveExistingAnilistId(): number | null {
        return mapping?.anilist_id ?? detail?.anilist_id ?? loadedDetailId ?? null;
    }

    function resolveAnilistIdFromForm(): number | null {
        if (mode === "edit") {
            return resolveExistingAnilistId();
        }
        const parsed = parseAnilistIdValue(anilistIdInput);
        return parsed ?? resolveExistingAnilistId();
    }

    function composeOverrideWithAnilistId(
        anilistId: number | null,
        override: Record<string, unknown>,
    ): Record<string, unknown> {
        const payload = { ...override };
        return anilistId ? { anilist_id: anilistId, ...payload } : payload;
    }

    function extractOverrideFromJson(input: Record<string, unknown>): {
        anilistId: number | null;
        override: Record<string, unknown>;
    } {
        const { anilist_id, ...rest } = input;
        return { anilistId: parseAnilistIdValue(anilist_id), override: { ...rest } };
    }

    async function fetchDetail(anilistId: number, { silent = false } = {}) {
        if (currentAbort) {
            currentAbort.abort();
        }
        const controller = new AbortController();
        currentAbort = controller;
        loadingDetail = true;
        try {
            const res = await apiFetch(
                `/api/mappings/${anilistId}`,
                { signal: controller.signal },
                { silent: true },
            );
            if (!res.ok) {
                detail = null;
                loadedDetailId = null;
                updateFieldStateFromOverride(null);
                rawJson = JSON.stringify(
                    composeOverrideWithAnilistId(anilistId, {}),
                    null,
                    4,
                );
                if (!silent) {
                    if (res.status === 404) {
                        toast("No existing mapping found for this AniList ID", "info");
                    } else {
                        toast(`Failed to load mapping (HTTP ${res.status})`, "error");
                    }
                }
                return;
            }
            const data = (await res.json()) as MappingDetail;
            detail = data;
            loadedDetailId = anilistId;
            updateFieldStateFromOverride(data.override ?? null);
            rawJson = JSON.stringify(
                composeOverrideWithAnilistId(
                    anilistId,
                    normaliseOverride(data.override),
                ),
                null,
                4,
            );
            if (mode !== "edit") {
                anilistIdInput = String(anilistId);
            }
        } catch (error) {
            if (isAbortError(error)) return;
            detail = null;
            loadedDetailId = null;
            updateFieldStateFromOverride(null);
            rawJson = JSON.stringify(
                composeOverrideWithAnilistId(anilistId, {}),
                null,
                4,
            );
            if (!silent) {
                toast("Failed to load mapping details", "error");
            }
        } finally {
            if (currentAbort === controller) {
                currentAbort = null;
            }
            loadingDetail = false;
        }
    }

    function resetEditorState() {
        fieldState = createEmptyFieldState();
        detail = null;
        rawJson = "{}";
        formError = null;
        jsonError = null;
        loadingDetail = false;
        saving = false;
        loadedDetailId = null;
    }

    $effect(() => {
        if (!open) {
            initialised = false;
            resetEditorState();
            return;
        }
        if (!initialised) {
            if (mode === "edit" && mapping) {
                anilistIdInput = String(mapping.anilist_id);
                fetchDetail(mapping.anilist_id);
            } else {
                anilistIdInput = "";
                rawJson = "{}";
                updateFieldStateFromOverride(null);
            }
            initialised = true;
        }
    });

    $effect(() => {
        if (!open) return;
        if (mode === "edit" && mapping) {
            if (loadedDetailId !== mapping.anilist_id && !loadingDetail) {
                anilistIdInput = String(mapping.anilist_id);
                fetchDetail(mapping.anilist_id, { silent: true });
            }
        }
    });

    $effect(() => {
        if (!open || activeTab !== "form") return;
        try {
            const snapshot = composeOverrideWithAnilistId(
                resolveAnilistIdFromForm(),
                buildOverrideFromState(),
            );
            rawJson = JSON.stringify(snapshot, null, 4);
        } catch {
            // ignore invalid form state while the user is editing
        }
    });

    function handleAddSeason(fieldId: FieldId) {
        addSeasonRow(fieldId);
    }

    function switchTab(next: "form" | "json") {
        if (next === activeTab) return;
        if (next === "json") {
            try {
                const snapshot = composeOverrideWithAnilistId(
                    resolveAnilistIdFromForm(),
                    buildOverrideFromState(),
                );
                rawJson = JSON.stringify(snapshot, null, 4);
                formError = null;
                jsonError = null;
                activeTab = next;
            } catch (error) {
                formError = (error as Error).message;
            }
            return;
        }
        try {
            const parsed = rawJson.trim() ? JSON.parse(rawJson) : {};
            if (parsed !== null && typeof parsed !== "object") {
                throw new Error("Override must be an object");
            }
            const { anilistId: parsedAnilistId, override } = extractOverrideFromJson(
                parsed as Record<string, unknown>,
            );
            if (mode !== "edit" && parsedAnilistId) {
                anilistIdInput = String(parsedAnilistId);
            }
            updateFieldStateFromOverride(override);
            formError = null;
            jsonError = null;
            activeTab = next;
        } catch (error) {
            jsonError = `Invalid JSON: ${(error as Error).message}`;
        }
    }

    function buildOverrideFromState(): Record<string, unknown> {
        const entry: Record<string, unknown> = {};
        for (const def of FIELD_DEFS) {
            const state = fieldState[def.id];
            if (!state || state.mode === "omit") continue;
            if (state.mode === "null") {
                entry[def.id] = null;
                continue;
            }
            if (def.type === "season") {
                entry[def.id] = buildSeasonMapping((state.value as SeasonRow[]) || []);
                continue;
            }
            const text = String(state.value || "");
            entry[def.id] =
                def.type === "number"
                    ? Number(text.trim())
                    : def.type === "number_list"
                      ? parseNumberList(text)
                      : parseStringList(text);
        }
        return entry;
    }

    async function save() {
        formError = null;
        jsonError = null;

        let payload: MappingOverridePayload | null = null;
        let targetAnilistId: number | null = null;

        if (activeTab === "json") {
            let parsed: unknown;
            try {
                parsed = rawJson.trim() ? JSON.parse(rawJson) : {};
                if (parsed !== null && typeof parsed !== "object") {
                    throw new Error("Override must be an object");
                }
            } catch (error) {
                jsonError = `Invalid JSON: ${(error as Error).message}`;
                return;
            }

            const parsedRecord = parsed as Record<string, unknown>;
            const { anilistId: jsonAnilistId } = extractOverrideFromJson(parsedRecord);
            targetAnilistId =
                mode === "edit"
                    ? resolveExistingAnilistId()
                    : (jsonAnilistId ?? parseAnilistIdValue(anilistIdInput));

            if (!targetAnilistId) {
                jsonError = "AniList ID is required";
                return;
            }

            if (mode !== "edit") {
                anilistIdInput = String(targetAnilistId);
            }

            payload = {
                anilist_id: targetAnilistId,
                raw: { ...parsedRecord },
                fields: null,
            };
        } else {
            targetAnilistId = resolveAnilistIdFromForm();
            if (!targetAnilistId) {
                formError = "AniList ID is required";
                return;
            }

            try {
                const fieldsPayload = buildFieldsPayload();
                payload = {
                    anilist_id: targetAnilistId,
                    fields: Object.keys(fieldsPayload).length ? fieldsPayload : {},
                    raw: null,
                };
            } catch (error) {
                formError = (error as Error).message;
                return;
            }
        }

        if (!payload || !targetAnilistId) {
            formError = "AniList ID is required";
            return;
        }

        saving = true;
        try {
            const res = await apiFetch(
                mode === "edit" ? `/api/mappings/${targetAnilistId}` : "/api/mappings",
                {
                    method: mode === "edit" ? "PUT" : "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                },
                {
                    successMessage:
                        mode === "edit" ? "Override updated" : "Override created",
                },
            );
            if (!res.ok) return;
            const data = (await res.json()) as MappingDetail;
            detail = data;
            loadedDetailId = data.anilist_id;
            updateFieldStateFromOverride(data.override ?? null);
            rawJson = JSON.stringify(
                composeOverrideWithAnilistId(
                    data.anilist_id,
                    normaliseOverride(data.override),
                ),
                null,
                4,
            );
            if (mode !== "edit") {
                anilistIdInput = String(data.anilist_id);
            }
            onSaved?.(data);
            open = false;
        } finally {
            saving = false;
        }
    }

    async function loadEffectiveForCreate() {
        formError = null;
        jsonError = null;
        const parsed = parseAnilistIdValue(anilistIdInput);
        if (!parsed) {
            formError = "Enter a valid AniList ID";
            return;
        }
        await fetchDetail(parsed);
    }
</script>

<Modal
    bind:open
    contentClass="fixed left-1/2 top-1/2 z-50 w-full max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-slate-800/70 bg-slate-950/95 shadow-[0_32px_120px_-48px_rgba(15,23,42,0.85)] ring-1 ring-emerald-500/10"
    headerWrapperClass="px-6 pt-6 pb-4 border-b border-slate-800/60 bg-slate-950/85"
    footerClass="border-t border-slate-800/60 bg-slate-950/85 px-6 py-4"
    titleClass="flex items-center gap-3 text-base font-semibold tracking-wide text-slate-100">
    {#snippet titleChildren()}
        <span class="flex items-center gap-2">
            {mode === "edit" ? "Edit Mapping Override" : "New Mapping Override"}
        </span>
    {/snippet}
    {#snippet footerChildren()}
        <div class="flex w-full flex-wrap items-center justify-between gap-3">
            <div class="text-xs text-rose-300">{formError}</div>
            <div class="flex items-center gap-2">
                <button
                    class="inline-flex h-9 items-center rounded-lg border border-slate-700/70 bg-slate-900/60 px-3 text-[11px] font-semibold text-slate-200 transition hover:border-slate-500/70 hover:bg-slate-900/80"
                    onclick={() => (open = false)}
                    type="button">
                    Cancel
                </button>
                <button
                    class="inline-flex h-9 items-center rounded-lg bg-emerald-600/90 px-4 text-[11px] font-semibold text-emerald-50 transition hover:bg-emerald-500 disabled:opacity-60"
                    disabled={saving}
                    onclick={save}
                    type="button">
                    {saving ? "Saving…" : "Save Override"}
                </button>
            </div>
        </div>
    {/snippet}
    <div class="max-h-[70vh] overflow-y-auto px-6 py-5">
        <div
            class="space-y-5 rounded-xl border border-slate-800/70 bg-slate-950/80 p-5 text-[11px] shadow-[0_24px_64px_-32px_rgba(2,6,23,0.9)] ring-1 ring-slate-900/60 backdrop-blur">
            <div
                class="rounded-lg border border-slate-800/60 bg-linear-to-br from-slate-950/95 via-slate-950/80 to-slate-900/70 p-5 shadow-inner">
                <div
                    class={`grid gap-4 ${detail?.anilist ? "md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]" : ""}`}>
                    <div class="space-y-2">
                        <label
                            for="anilist-id"
                            class="block text-[12px] font-semibold tracking-[0.08em] text-slate-300 uppercase">
                            AniList Identifier
                        </label>
                        <div class="mt-1 flex flex-wrap items-center gap-2">
                            <input
                                id="anilist-id"
                                class="h-9 w-full rounded-lg border border-slate-800/60 bg-slate-950/80 px-3 text-[12px] text-slate-100 shadow-inner transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none"
                                type="number"
                                placeholder="e.g. 12345"
                                bind:value={anilistIdInput}
                                disabled={mode === "edit"} />
                            {#if mode === "create"}
                                <button
                                    class="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-700/70 bg-slate-900/60 px-3 text-[11px] font-semibold text-slate-200 transition hover:border-emerald-500/70 hover:bg-slate-900/80"
                                    type="button"
                                    onclick={loadEffectiveForCreate}>
                                    {#if loadingDetail}
                                        <Loader2 class="h-3.5 w-3.5 animate-spin" />
                                    {:else}
                                        <Globe class="h-3.5 w-3.5" />
                                    {/if}
                                    Prefill
                                </button>
                            {/if}
                        </div>
                        <p class="text-[10px] text-slate-500">
                            Provide an AniList anime identifier to inspect and override
                            downstream provider mappings.
                        </p>
                    </div>
                    {#if detail?.anilist}
                        {@const coverImage =
                            detail.anilist?.coverImage?.medium ??
                            detail.anilist?.coverImage?.large ??
                            detail.anilist?.coverImage?.extraLarge ??
                            null}
                        <div
                            class="h-full rounded-lg border border-slate-800/60 bg-linear-to-br from-slate-950/95 via-slate-950/80 to-slate-900/70 p-4 shadow-inner">
                            <div class="flex min-w-0 items-start gap-3">
                                <a
                                    href={`https://anilist.co/anime/${detail.anilist_id}`}
                                    rel="noopener noreferrer"
                                    target="_blank"
                                    class="group block w-12 shrink-0">
                                    {#if coverImage}
                                        <div
                                            class="relative h-16 w-full overflow-hidden rounded-md ring-1 ring-slate-700/60">
                                            <img
                                                alt={(preferredTitle(
                                                    detail.anilist.title,
                                                ) || "Cover") + " cover"}
                                                loading="lazy"
                                                src={coverImage}
                                                class="h-full w-full object-cover transition-[filter] duration-150 ease-out group-hover:blur-none"
                                                class:blur-sm={detail.anilist
                                                    ?.isAdult} />
                                        </div>
                                    {:else}
                                        <div
                                            class="flex h-20 w-14 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                                            No Art
                                        </div>
                                    {/if}
                                </a>
                                <div class="min-w-0 flex-1 space-y-1">
                                    <div class="flex items-start justify-between gap-2">
                                        <div class="min-w-0 space-y-2">
                                            <div
                                                class="truncate font-medium"
                                                title={preferredTitle(
                                                    detail.anilist.title,
                                                ) || `AniList ${detail.anilist_id}`}>
                                                {#if detail?.anilist?.title}
                                                    {preferredTitle(
                                                        detail.anilist.title,
                                                    )}
                                                {:else}
                                                    AniList {detail.anilist_id}
                                                {/if}
                                            </div>
                                            <div
                                                class="mt-1 flex flex-wrap gap-1 text-[9px] text-slate-400">
                                                {#if detail.anilist.format}<span
                                                        class="truncate rounded bg-slate-800/70 px-1.5 py-0.5 tracking-wide uppercase"
                                                        title={detail.anilist.format}
                                                        >{detail.anilist.format}</span>
                                                {/if}
                                                {#if detail.anilist.status}<span
                                                        class="truncate rounded bg-slate-800/70 px-1.5 py-0.5 tracking-wide uppercase"
                                                        title={detail.anilist.status}
                                                        >{detail.anilist.status}</span>
                                                {/if}
                                                {#if detail.anilist.season && detail.anilist.seasonYear}<span
                                                        class="truncate rounded bg-slate-800/70 px-1.5 py-0.5 tracking-wide uppercase"
                                                        title={`${detail.anilist.season} ${detail.anilist.seasonYear}`}
                                                        >{detail.anilist.season}
                                                        {detail.anilist
                                                            .seasonYear}</span>
                                                {/if}
                                                {#if detail.anilist.episodes}<span
                                                        class="truncate rounded bg-slate-800/70 px-1.5 py-0.5"
                                                        title={`${detail.anilist.episodes} episodes`}
                                                        >EP {detail.anilist
                                                            .episodes}</span>
                                                {/if}
                                                {#if detail.anilist?.isAdult}
                                                    <span
                                                        class="rounded bg-rose-800 px-1.5 py-0.5 text-rose-100"
                                                        title="ADULT content"
                                                        >ADULT</span>
                                                {/if}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    {/if}
                </div>
            </div>
            {#if loadingDetail}
                <div
                    class="rounded-md border border-slate-800/60 bg-slate-950/70 p-4 text-center text-[11px] text-slate-300">
                    Loading mapping details…
                </div>
            {:else}
                <Tabs.Root
                    value={activeTab}
                    onValueChange={(v) => switchTab(v as typeof activeTab)}
                    class="space-y-4">
                    <Tabs.List
                        class="flex items-center gap-1 rounded-lg border border-slate-800/60 bg-slate-950/60 p-1 text-[11px]">
                        <Tabs.Trigger
                            value="form"
                            class="inline-flex h-8 items-center gap-1 rounded-md px-3 font-medium text-slate-400 transition data-[state=active]:bg-emerald-900/40 data-[state=active]:text-emerald-100">
                            Form
                        </Tabs.Trigger>
                        <Tabs.Trigger
                            value="json"
                            class="inline-flex h-8 items-center gap-1 rounded-md px-3 font-medium text-slate-400 transition data-[state=active]:bg-emerald-900/40 data-[state=active]:text-emerald-100">
                            JSON
                        </Tabs.Trigger>
                    </Tabs.List>
                    <Tabs.Content value="form">
                        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                            {#each FIELD_DEFS as field (field.id)}
                                {@const state = fieldState[field.id]}
                                <div
                                    class={`rounded-xl border border-slate-800/60 bg-linear-to-br from-slate-950/90 via-slate-950/70 to-slate-900/70 p-4 shadow-[inset_0_1px_0_rgba(148,163,184,0.05)] ${field.type === "season" ? "md:col-span-2 xl:col-span-3" : ""}`}>
                                    <div
                                        class="flex flex-wrap items-start justify-between gap-3">
                                        <div class="space-y-1">
                                            <div
                                                class="flex flex-wrap items-center gap-2">
                                                <span
                                                    class="text-[12px] font-semibold text-slate-100">
                                                    {field.label}
                                                </span>
                                            </div>
                                            {#if field.hint}
                                                <p class="text-[10px] text-slate-500">
                                                    {field.hint}
                                                </p>
                                            {/if}
                                        </div>
                                        <select
                                            class="h-8 rounded-lg border border-slate-800/60 bg-slate-950/70 px-3 text-[10px] font-medium text-slate-100 transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none"
                                            value={state.mode}
                                            onchange={(e) =>
                                                setFieldMode(
                                                    field.id,
                                                    (e.currentTarget
                                                        .value as MappingOverrideMode) ??
                                                        "omit",
                                                )}>
                                            {#each MODE_OPTIONS as option (option)}
                                                <option value={option}>
                                                    {option === "omit"
                                                        ? "Use Upstream"
                                                        : option === "null"
                                                          ? "Force Null"
                                                          : "Custom Value"}
                                                </option>
                                            {/each}
                                        </select>
                                    </div>
                                    {#if state.mode === "value"}
                                        {#if field.type === "season"}
                                            {@const rows = Array.isArray(state.value)
                                                ? (state.value as SeasonRow[])
                                                : []}
                                            <div class="mt-3 space-y-2">
                                                {#each rows as row, index (index)}
                                                    <div
                                                        class="flex flex-col gap-2 rounded-lg border border-slate-800/60 bg-slate-950/70 p-3 shadow-inner sm:flex-row sm:items-center">
                                                        <div
                                                            class="flex items-center gap-2 sm:w-28">
                                                            <label
                                                                class="text-[10px] font-medium tracking-wide text-slate-500 uppercase"
                                                                for={`season-${field.id}-${index}`}>
                                                                Season
                                                            </label>
                                                            <input
                                                                id={`season-${field.id}-${index}`}
                                                                class="h-8 w-full rounded-lg border border-slate-800/60 bg-slate-950/80 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30 focus:outline-none"
                                                                placeholder="s1"
                                                                bind:value={row.season}
                                                                oninput={(e) =>
                                                                    updateSeasonRow(
                                                                        field.id,
                                                                        index,
                                                                        "season",
                                                                        (
                                                                            e.currentTarget as HTMLInputElement
                                                                        ).value,
                                                                    )} />
                                                        </div>
                                                        <div class="flex-1">
                                                            <label
                                                                class="sr-only"
                                                                for={`pattern-${field.id}-${index}`}>
                                                                Episode pattern
                                                            </label>
                                                            <input
                                                                id={`pattern-${field.id}-${index}`}
                                                                class="h-8 w-full rounded-lg border border-slate-800/60 bg-slate-950/80 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30 focus:outline-none"
                                                                placeholder="e1-e12"
                                                                bind:value={row.value}
                                                                oninput={(e) =>
                                                                    updateSeasonRow(
                                                                        field.id,
                                                                        index,
                                                                        "value",
                                                                        (
                                                                            e.currentTarget as HTMLInputElement
                                                                        ).value,
                                                                    )} />
                                                        </div>
                                                        <button
                                                            class="inline-flex h-8 items-center gap-1 rounded-lg border border-rose-800/50 bg-rose-950/30 px-3 text-[10px] font-medium text-rose-200 transition hover:bg-rose-900/40"
                                                            type="button"
                                                            onclick={() =>
                                                                removeSeasonRow(
                                                                    field.id,
                                                                    index,
                                                                )}>
                                                            <Trash2
                                                                class="h-3.5 w-3.5" />
                                                            Remove
                                                        </button>
                                                    </div>
                                                {/each}
                                                <button
                                                    class="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700/60 bg-slate-900/60 px-3 text-[10px] font-semibold text-slate-100 transition hover:border-emerald-500/70 hover:bg-slate-900/80"
                                                    type="button"
                                                    onclick={() =>
                                                        handleAddSeason(field.id)}>
                                                    <Plus class="h-3.5 w-3.5" />
                                                    Add season mapping
                                                </button>
                                            </div>
                                        {:else}
                                            <input
                                                class="mt-3 h-9 w-full rounded-lg border border-slate-800/60 bg-slate-950/80 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30 focus:outline-none"
                                                placeholder={field.placeholder}
                                                bind:value={state.value as string}
                                                oninput={(e) =>
                                                    setFieldStringValue(
                                                        field.id,
                                                        (
                                                            e.currentTarget as HTMLInputElement
                                                        ).value,
                                                    )} />
                                        {/if}
                                    {:else if state.mode === "null"}
                                        <p
                                            class="mt-3 rounded-lg border border-rose-800/40 bg-rose-950/30 p-3 text-[11px] text-rose-100">
                                            Field will be returned as <strong
                                                class="font-semibold text-rose-200"
                                                >null</strong>
                                            for this mapping.
                                        </p>
                                    {:else if field.type === "season"}
                                        {@const effectiveRows =
                                            getEffectiveSeasonRows(field)}
                                        {#if effectiveRows.length}
                                            <div class="mt-3 space-y-2">
                                                {#each effectiveRows as row, index (index)}
                                                    <div
                                                        class="flex flex-col gap-2 rounded-lg border border-slate-800/60 bg-slate-950/60 p-3 text-slate-400 opacity-80 sm:flex-row sm:items-center">
                                                        <div
                                                            class="flex items-center gap-2 sm:w-28">
                                                            <label
                                                                class="text-[10px] font-medium tracking-wide text-slate-500 uppercase"
                                                                for={`effective-${field.id}-season-${index}`}>
                                                                Season
                                                            </label>
                                                            <input
                                                                id={`effective-${field.id}-season-${index}`}
                                                                class="h-8 w-full rounded-lg border border-slate-800/60 bg-slate-950/60 px-3 text-[11px] text-slate-400 shadow-inner"
                                                                value={row.season}
                                                                disabled
                                                                readonly />
                                                        </div>
                                                        <div class="flex-1">
                                                            <label
                                                                class="sr-only"
                                                                for={`effective-${field.id}-pattern-${index}`}>
                                                                Episode pattern
                                                            </label>
                                                            <input
                                                                id={`effective-${field.id}-pattern-${index}`}
                                                                class="h-8 w-full rounded-lg border border-slate-800/60 bg-slate-950/60 px-3 text-[11px] text-slate-400 shadow-inner"
                                                                value={row.value}
                                                                disabled
                                                                readonly />
                                                        </div>
                                                    </div>
                                                {/each}
                                            </div>
                                        {:else}
                                            <p
                                                class="mt-3 rounded-lg border border-slate-800/50 bg-slate-950/50 p-3 text-[11px] text-slate-400">
                                                {formatEffective(field)}
                                            </p>
                                        {/if}
                                    {:else}
                                        {@const effectiveText = formatEffective(field)}
                                        <div class="mt-3 space-y-2">
                                            <input
                                                class="h-9 w-full rounded-lg border border-slate-800/60 bg-slate-950/60 px-3 text-[11px] text-slate-400 opacity-70"
                                                value={effectiveText}
                                                disabled
                                                readonly />
                                            <p class="text-[10px] text-slate-500">
                                                Upstream value in effect.
                                            </p>
                                        </div>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    </Tabs.Content>
                    <Tabs.Content value="json">
                        <CodeEditor
                            bind:value={rawJson}
                            {jsonSchema}
                            performanceMode={true} />
                        {#if jsonError}
                            <p class="mt-2 text-xs text-rose-400">{jsonError}</p>
                        {/if}
                    </Tabs.Content>
                </Tabs.Root>
            {/if}
        </div>
    </div>
</Modal>
