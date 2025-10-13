<script lang="ts">
    import { createEventDispatcher, onDestroy, onMount } from "svelte";

    import PinFieldsEditor from "$lib/components/timeline/pin-fields-editor.svelte";
    import type { HistoryItem, PinFieldOption, PinResponse } from "$lib/types/api";
    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";
    import { loadPinOptions } from "$lib/utils/pin-options";

    interface Props {
        profile: string;
        item: HistoryItem;
    }

    let { profile, item }: Props = $props();

    const dispatch = createEventDispatcher<{
        draft: { fields: string[] };
        saved: { fields: string[] };
        busy: { value: boolean };
    }>();

    let options: PinFieldOption[] = $state([]);
    let optionsLoading = $state(false);
    let optionsError: string | null = $state(null);
    let optionsErrorNotified = false;
    let saving = $state(false);
    let error: string | null = $state(null);
    let selected: string[] = $state([]);
    let baseline: string[] = $state([]);

    const hasAniListId = $derived(Boolean(item.anilist_id));

    function arraysEqual(a: string[], b: string[]): boolean {
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
        return true;
    }

    function emitBusy(value: boolean) {
        dispatch("busy", { value });
    }

    function setSelection(fields: string[], updateBaseline = false) {
        selected = [...fields];
        if (updateBaseline) baseline = [...fields];
        dispatch("draft", { fields: [...fields] });
    }

    async function loadOptions(force = false) {
        optionsLoading = true;
        if (force) optionsErrorNotified = false;
        optionsError = null;
        try {
            const loaded = await loadPinOptions(force);
            options = [...loaded];
            optionsError = null;
        } catch (e) {
            console.error("Failed to load pin options", e);
            optionsError = (e as Error)?.message || "Failed to load pin options";
            if (!optionsErrorNotified) {
                toast("Failed to load pin options", "error");
                optionsErrorNotified = true;
            }
        } finally {
            optionsLoading = false;
        }
    }

    async function initialize() {
        emitBusy(true);
        try {
            await loadOptions(false);
        } finally {
            emitBusy(false);
        }
    }

    async function saveSelection(fields: string[] = selected) {
        if (!item.anilist_id) {
            toast("Pins require a linked AniList entry.", "error");
            return;
        }
        if (arraysEqual(fields, baseline)) return;
        saving = true;
        error = null;
        emitBusy(true);
        try {
            if (!fields.length) {
                const res = await apiFetch(
                    `/api/pins/${profile}/${item.anilist_id}`,
                    { method: "DELETE" },
                    { successMessage: "Pins cleared" },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                setSelection([], true);
                dispatch("saved", { fields: [] });
                return;
            }
            const res = await apiFetch(
                `/api/pins/${profile}/${item.anilist_id}`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fields }),
                },
                { successMessage: "Pins updated" },
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as PinResponse;
            const next = data.fields ?? [];
            setSelection(next, true);
            dispatch("saved", { fields: [...next] });
        } catch (e) {
            console.error("Failed to save pins", e);
            error = (e as Error)?.message || "Failed to save pins";
            toast("Failed to save pins", "error");
        } finally {
            saving = false;
            emitBusy(false);
        }
    }

    async function refreshAll(force = true) {
        emitBusy(true);
        try {
            await loadOptions(force);
            error = null;
            const base = Array.isArray(item.pinned_fields) ? item.pinned_fields : [];
            setSelection(base, true);
        } finally {
            emitBusy(false);
        }
    }

    onMount(() => {
        const base = Array.isArray(item.pinned_fields) ? item.pinned_fields : [];
        setSelection(base, true);
        void initialize();
    });

    onDestroy(() => {
        emitBusy(false);
    });

    $effect(() => {
        const base = Array.isArray(item.pinned_fields) ? item.pinned_fields : [];
        if (!saving && !arraysEqual(base, baseline)) {
            setSelection(base, true);
        }
    });
</script>

<PinFieldsEditor
    bind:value={selected}
    {baseline}
    {options}
    loading={optionsLoading}
    {saving}
    {error}
    {optionsError}
    missingMessage={hasAniListId ? null : "Pins require a linked AniList entry."}
    title="Pin fields"
    subtitle="Choose the fields to keep unchanged for this entry when syncing."
    disabled={!hasAniListId}
    on:save={(event) => void saveSelection(event.detail.value)}
    on:refresh={(event) => void refreshAll(event.detail.force)}
    on:change={(event) => dispatch("draft", { fields: [...event.detail.value] })} />
