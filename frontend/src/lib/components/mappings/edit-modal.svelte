<script lang="ts">
    import { Tabs } from "bits-ui";

    import CodeEditor from "$lib/components/code-editor.svelte";
    import {
        FIELD_DEFS,
        mappingSchema,
        type FieldId,
        type FieldStateMap,
        type FieldStateValue,
        type OverrideFieldDefinition,
        type OverrideFieldType,
        type SeasonRow,
    } from "$lib/components/mappings/columns";
    import type {
        Mapping,
        MappingDetail,
        MappingOverrideFieldInput,
        MappingOverrideMode,
        MappingOverridePayload,
    } from "$lib/types/api";
    import Modal from "$lib/ui/modal.svelte";
    import { apiFetch, isAbortError } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";
    import MappingDetailPreview from "./mapping-detail-preview.svelte";
    import MappingFieldCard from "./mapping-field-card.svelte";

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
    const pendingPrefillId = $derived(parseAnilistIdValue(anilistIdInput));
    let activeTab = $state<"form" | "json">("form");
    let rawJson = $state<string>("{}");
    let formError = $state<string | null>(null);
    let jsonError = $state<string | null>(null);
    let loadingDetail = $state(false);
    let saving = $state(false);
    let loadedDetailId: number | null = $state(null);
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

    function mutateSeasonRows(
        fieldId: FieldId,
        mutator: (rows: SeasonRow[]) => SeasonRow[],
    ) {
        const state = fieldState[fieldId];
        if (!state) return;
        const rows = Array.isArray(state.value) ? (state.value as SeasonRow[]) : [];
        const nextRows = mutator([...rows]);
        fieldState = { ...fieldState, [fieldId]: { ...state, value: nextRows } };
    }

    function addSeasonRow(fieldId: FieldId) {
        mutateSeasonRows(fieldId, (rows) => [...rows, { season: "", value: "" }]);
    }

    function updateSeasonRow(
        fieldId: FieldId,
        index: number,
        key: keyof SeasonRow,
        value: string,
    ) {
        mutateSeasonRows(fieldId, (rows) => {
            if (!rows[index]) return rows;
            rows[index] = { ...rows[index], [key]: value };
            return rows;
        });
    }

    function removeSeasonRow(fieldId: FieldId, index: number) {
        mutateSeasonRows(fieldId, (rows) => {
            rows.splice(index, 1);
            return rows;
        });
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

    function parseTokens(input: string): string[] {
        return input
            .split(/[\s,]+/)
            .map((token) => token.trim())
            .filter(Boolean);
    }

    function parseNumberList(input: string): number[] {
        const tokens = parseTokens(input);
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
        return parseTokens(input);
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

    function resolveFieldValue(
        def: OverrideFieldDefinition,
        state: { value: FieldStateValue },
    ): unknown {
        if (def.type === "season") {
            return buildSeasonMapping((state.value as SeasonRow[]) || []);
        }
        const text = String(state.value ?? "").trim();
        if (def.type === "number") {
            if (!text) {
                throw new Error(`${def.label}: value is required`);
            }
            const parsed = Number(text);
            if (!Number.isInteger(parsed)) {
                throw new Error(`${def.label}: value must be an integer`);
            }
            return parsed;
        }
        if (def.type === "number_list") {
            return text ? parseNumberList(text) : [];
        }
        return text ? parseStringList(text) : [];
    }

    function buildFieldsPayload(): Record<string, MappingOverrideFieldInput> {
        const payload: Record<string, MappingOverrideFieldInput> = {};
        for (const def of FIELD_DEFS) {
            const state = fieldState[def.id];
            if (!state || state.mode === "omit") continue;
            payload[def.id] =
                state.mode === "null"
                    ? { mode: "null" }
                    : { mode: "value", value: resolveFieldValue(def, state) };
        }
        return payload;
    }

    function normaliseOverride(
        override: Record<string, unknown> | null | undefined,
    ): Record<string, unknown> {
        return override ? { ...override } : {};
    }

    function toJsonString(
        anilistId: number | null,
        override: Record<string, unknown> = {},
    ): string {
        const payload =
            anilistId != null
                ? composeOverrideWithAnilistId(anilistId, override)
                : override;
        return JSON.stringify(payload, null, 4);
    }

    function applyDetailState(
        anilistId: number | null,
        nextDetail: MappingDetail | null,
    ): void {
        detail = nextDetail;
        loadedDetailId = nextDetail?.anilist_id ?? null;
        updateFieldStateFromOverride(nextDetail?.override ?? null);
        rawJson = toJsonString(
            nextDetail?.anilist_id ?? anilistId,
            normaliseOverride(nextDetail?.override),
        );
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
                applyDetailState(anilistId, null);
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
            applyDetailState(anilistId, data);
            if (mode !== "edit") {
                anilistIdInput = String(anilistId);
            }
        } catch (error) {
            if (isAbortError(error)) return;
            applyDetailState(anilistId, null);
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
        rawJson = toJsonString(null);
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
                rawJson = toJsonString(null);
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
            rawJson = toJsonString(
                resolveAnilistIdFromForm(),
                buildOverrideFromState(),
            );
        } catch {
            // ignore invalid form state while the user is editing
        }
    });

    $effect(() => {
        if (!open || mode !== "create") return;
        const parsedInput = parseAnilistIdValue(anilistIdInput);
        if (detail && (!parsedInput || parsedInput !== loadedDetailId)) {
            detail = null;
        }
    });

    function handleAddSeason(fieldId: FieldId) {
        addSeasonRow(fieldId);
    }

    function switchTab(next: "form" | "json") {
        if (next === activeTab) return;
        if (next === "json") {
            try {
                rawJson = toJsonString(
                    resolveAnilistIdFromForm(),
                    buildOverrideFromState(),
                );
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
            entry[def.id] =
                state.mode === "null" ? null : resolveFieldValue(def, state);
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
                    fields: fieldsPayload,
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
            applyDetailState(data.anilist_id, data);
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
                <div class="grid gap-4 md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
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
                        </div>
                        <p class="text-[10px] text-slate-500">
                            Provide an AniList anime identifier to inspect and override
                            downstream provider mappings.
                        </p>
                    </div>
                    <MappingDetailPreview
                        {detail}
                        {mode}
                        {loadingDetail}
                        {pendingPrefillId}
                        {loadedDetailId}
                        on:prefill={loadEffectiveForCreate} />
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
                                <MappingFieldCard
                                    {field}
                                    {state}
                                    modeOptions={MODE_OPTIONS}
                                    effectiveText={formatEffective(field)}
                                    effectiveSeasonRows={getEffectiveSeasonRows(field)}
                                    onModeChange={(modeValue) =>
                                        setFieldMode(field.id, modeValue)}
                                    onStringChange={(value) =>
                                        setFieldStringValue(field.id, value)}
                                    onAddSeason={() => handleAddSeason(field.id)}
                                    onUpdateSeason={(index, key, value) =>
                                        updateSeasonRow(field.id, index, key, value)}
                                    onRemoveSeason={(index) =>
                                        removeSeasonRow(field.id, index)} />
                            {/each}
                        </div>
                    </Tabs.Content>
                    <Tabs.Content value="json">
                        <CodeEditor
                            bind:value={rawJson}
                            jsonSchema={mappingSchema}
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
