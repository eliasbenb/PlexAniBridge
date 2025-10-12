<script lang="ts">
    import { createEventDispatcher, onDestroy, onMount } from "svelte";

    import { LoaderCircle, Pin, PinOff, RefreshCcw } from "@lucide/svelte";
    import { SvelteSet } from "svelte/reactivity";

    import type { HistoryItem, PinFieldOption, PinResponse } from "$lib/types/api";
    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

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
    let saving = $state(false);
    let error: string | null = $state(null);
    let selected: string[] = $state([]);
    let initial: string[] = $state([]);

    const selectedCount = $derived(selected.length);
    const hasAniListId = $derived(Boolean(item.anilist_id));
    const hasChanges = $derived(!arraysEqual(selected, initial));
    const allSelected = $derived(
        options.length > 0 &&
            arraysEqual(
                selected,
                options.map((option) => option.value),
            ),
    );
    const showNoOptions = $derived(!optionsLoading && !options.length && !optionsError);
    const isBusy = $derived(saving || optionsLoading);

    interface PinOptionsState {
        cache: PinFieldOption[] | null;
        promise: Promise<PinFieldOption[]> | null;
        errorNotified: boolean;
    }

    function getPinOptionsState(): PinOptionsState {
        const root = globalThis as typeof globalThis & {
            __timelinePinOptionsState?: PinOptionsState;
        };
        if (!root.__timelinePinOptionsState) {
            root.__timelinePinOptionsState = {
                cache: null,
                promise: null,
                errorNotified: false,
            };
        }
        return root.__timelinePinOptionsState;
    }

    function arraysEqual(a: string[], b: string[]): boolean {
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
        return true;
    }

    function emitBusy(value: boolean) {
        dispatch("busy", { value });
    }

    function updateSelection(fields: string[], setInitial = false) {
        selected = [...fields];
        if (setInitial) initial = [...fields];
        dispatch("draft", { fields: [...selected] });
    }

    async function loadOptions(force = false) {
        const state = getPinOptionsState();

        if (force) {
            state.cache = null;
            state.promise = null;
            state.errorNotified = false;
        }

        if (state.cache && !force) {
            options = [...state.cache];
            optionsError = null;
            return;
        }

        optionsLoading = true;
        optionsError = null;

        let isInitiator = false;
        if (!state.promise) {
            isInitiator = true;
            state.promise = (async () => {
                const res = await apiFetch("/api/pins/fields", undefined, {
                    silent: true,
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = (await res.json()) as { options?: PinFieldOption[] };
                const fetched = [...(data.options ?? [])];
                state.cache = fetched;
                return fetched;
            })();
        }

        try {
            const result = await state.promise;
            options = [...result];
            optionsError = null;
            state.errorNotified = false;
        } catch (e) {
            console.error("Failed to load pin options", e);
            optionsError = (e as Error)?.message || "Failed to load pin options";
            if (isInitiator || !state.errorNotified) {
                toast("Failed to load pin options", "error");
                state.errorNotified = true;
            }
            state.cache = null;
        } finally {
            optionsLoading = false;
            state.promise = null;
        }
    }

    async function initialize() {
        emitBusy(true);
        try {
            await loadOptions();
        } finally {
            emitBusy(false);
        }
    }

    function toggleField(value: string) {
        const current = new SvelteSet(selected);
        if (current.has(value)) current.delete(value);
        else current.add(value);
        const ordered = options.length
            ? options.map((opt) => opt.value).filter((v) => current.has(v))
            : Array.from(current);
        updateSelection(ordered);
    }

    function resetSelection() {
        if (!hasChanges) return;
        updateSelection(initial);
    }

    function clearSelection() {
        if (!selected.length) return;
        updateSelection([]);
    }

    function selectAll() {
        if (!options.length) return;
        const allValues = options.map((option) => option.value);
        if (arraysEqual(selected, allValues)) return;
        updateSelection(allValues);
    }

    async function saveSelection() {
        if (!item.anilist_id) {
            toast("Pins require a linked AniList entry.", "error");
            return;
        }
        if (!hasChanges) return;
        saving = true;
        error = null;
        emitBusy(true);
        const fields = [...selected];
        try {
            if (fields.length === 0) {
                const res = await apiFetch(
                    `/api/pins/${profile}/${item.anilist_id}`,
                    { method: "DELETE" },
                    { successMessage: "Pins cleared" },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                updateSelection([], true);
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
            updateSelection(next, true);
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

    async function retryOptions() {
        emitBusy(true);
        try {
            await loadOptions(true);
        } finally {
            emitBusy(false);
        }
    }

    async function refreshAll() {
        emitBusy(true);
        try {
            await loadOptions(true);
            error = null;
            updateSelection(
                Array.isArray(item.pinned_fields) ? item.pinned_fields : [],
                true,
            );
        } finally {
            emitBusy(false);
        }
    }

    onMount(() => {
        updateSelection(
            Array.isArray(item.pinned_fields) ? item.pinned_fields : [],
            true,
        );
        void initialize();
    });

    onDestroy(() => {
        emitBusy(false);
    });

    $effect(() => {
        const base = Array.isArray(item.pinned_fields) ? item.pinned_fields : [];
        if (!hasChanges && !saving && !arraysEqual(base, initial)) {
            updateSelection(base, true);
        }
    });
</script>

<div class="mt-3 ml-6 text-[11px]">
    <div class="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
        <div
            class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-3 py-2">
            <div class="flex items-start gap-2 text-[10px]">
                <Pin class="mt-[2px] h-3.5 w-3.5" />
                <div class="flex items-center gap-2">
                    <span class="font-semibold tracking-wide text-slate-100 uppercase"
                        >Pin fields</span>
                    <span
                        class="text-[11px] leading-tight font-normal text-slate-500 normal-case">
                        Choose the fields to keep unchanged for this entry when syncing.
                    </span>
                </div>
            </div>
            <div class="flex items-center gap-2 text-[11px] text-slate-400">
                <span
                    class={`inline-flex items-center gap-1 rounded-md border px-2 py-1 ${
                        hasChanges
                            ? "border-sky-500/60 bg-sky-500/10 text-sky-100"
                            : "border-slate-700 bg-slate-900/60"
                    }`}>
                    <Pin class="h-3.5 w-3.5" />
                    <span class="font-semibold text-slate-100">{selectedCount}</span>
                    selected
                </span>
                <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-slate-200 hover:border-slate-600 disabled:opacity-60"
                    onclick={refreshAll}
                    disabled={isBusy}>
                    <RefreshCcw class={`h-3.5 w-3.5 ${isBusy ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>
        </div>
        <div class="space-y-3 p-3">
            {#if error}
                <div
                    class="rounded-md border border-red-700/60 bg-red-900/20 px-3 py-2 text-red-100">
                    <span>{error}</span>
                </div>
            {/if}
            {#if !hasAniListId}
                <div
                    class="rounded-md border border-amber-600/60 bg-amber-900/20 px-3 py-2 text-amber-100">
                    Pins require a linked AniList entry.
                </div>
            {/if}
            {#if showNoOptions}
                <div
                    class="flex w-full items-center gap-2 rounded-md border border-dashed border-slate-800 px-3 py-2 text-slate-400">
                    <PinOff class="h-4 w-4" />
                    No pin fields available.
                </div>
            {:else}
                <div class="flex flex-wrap gap-2">
                    {#each options as option (option.value)}
                        {@const checked = selected.includes(option.value)}
                        <button
                            type="button"
                            class={`pin-option inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium transition ${
                                checked
                                    ? "border-sky-500/60 bg-sky-500/15 text-sky-100"
                                    : "border-slate-700 bg-slate-900/40 text-slate-300 hover:border-slate-600 hover:text-slate-100"
                            }`}
                            onclick={() => toggleField(option.value)}
                            aria-pressed={checked}
                            title={`${option.label} (${option.value})`}>
                            <span
                                class={`inline-block h-2.5 w-2.5 rounded-full ${
                                    checked
                                        ? "bg-sky-300 shadow-[0_0_0_1px_rgba(56,189,248,0.35)]"
                                        : "border border-slate-500 bg-slate-800"
                                }`}></span>
                            <span>{option.label}</span>
                        </button>
                    {/each}
                </div>
                {#if optionsLoading && options.length}
                    <div
                        class="flex w-full items-center gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-slate-400">
                        <LoaderCircle class="inline h-3.5 w-3.5 animate-spin" />
                        Updating options…
                    </div>
                {/if}
            {/if}
            {#if optionsError}
                <div
                    class="flex flex-wrap items-center gap-2 rounded-md border border-amber-600/60 bg-amber-900/20 px-3 py-2 text-amber-100">
                    <span>{optionsError}</span>
                    <button
                        type="button"
                        class="ml-auto inline-flex items-center gap-1 rounded-md border border-amber-500/70 px-2.5 py-1 hover:border-amber-400"
                        onclick={retryOptions}>
                        <RefreshCcw class="h-3.5 w-3.5" />
                        Retry
                    </button>
                </div>
            {/if}
            {#if optionsLoading && !options.length}
                <div class="flex items-center gap-2 text-slate-400">
                    <LoaderCircle class="inline h-3.5 w-3.5 animate-spin" />
                    Loading pin options…
                </div>
            {/if}
        </div>
        <div
            class="flex flex-wrap items-center gap-2 border-t border-slate-800 bg-slate-950/60 px-3 py-2">
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-sky-500/60 bg-sky-500/15 px-3 py-1.5 font-semibold text-sky-100 hover:bg-sky-500/25 disabled:opacity-60"
                onclick={saveSelection}
                disabled={!hasChanges || saving || optionsLoading || !hasAniListId}>
                {#if saving}
                    <LoaderCircle class="inline h-3.5 w-3.5 animate-spin" />
                {/if}
                Save pins
            </button>
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900/40 px-3 py-1.5 text-slate-200 hover:border-slate-500 disabled:opacity-60"
                onclick={resetSelection}
                disabled={!hasChanges || saving || optionsLoading}>
                Reset
            </button>
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900/40 px-3 py-1.5 text-slate-300 hover:border-slate-500 disabled:opacity-60"
                onclick={clearSelection}
                disabled={!selectedCount || saving || optionsLoading}>
                Clear
            </button>
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900/40 px-3 py-1.5 text-slate-200 hover:border-slate-500 disabled:opacity-60"
                onclick={selectAll}
                disabled={allSelected || saving || optionsLoading || !options.length}>
                Select all
            </button>
        </div>
    </div>
</div>
