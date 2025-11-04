<script lang="ts">
    import { Plus, Trash2 } from "@lucide/svelte";

    import type {
        FieldState,
        OverrideFieldDefinition,
        SeasonRow,
    } from "$lib/components/mappings/columns";
    import type { MappingOverrideMode } from "$lib/types/api";

    interface Props {
        field: OverrideFieldDefinition;
        state: FieldState | undefined;
        modeOptions: MappingOverrideMode[];
        effectiveText: string;
        effectiveSeasonRows: SeasonRow[];
        onModeChange: (mode: MappingOverrideMode) => void;
        onStringChange: (value: string) => void;
        onAddSeason: () => void;
        onUpdateSeason: (index: number, key: keyof SeasonRow, value: string) => void;
        onRemoveSeason: (index: number) => void;
    }

    let {
        field,
        state,
        modeOptions,
        effectiveText,
        effectiveSeasonRows,
        onModeChange,
        onStringChange,
        onAddSeason,
        onUpdateSeason,
        onRemoveSeason,
    }: Props = $props();

    const selectedMode = $derived(state?.mode ?? "omit");
    const rows = $derived(
        Array.isArray(state?.value) ? (state?.value as SeasonRow[]) : [],
    );
    const stringValue = $derived(
        typeof state?.value === "string" ? (state?.value as string) : "",
    );

    function handleModeChange(event: Event) {
        const next = (event.currentTarget as HTMLSelectElement)
            .value as MappingOverrideMode;
        onModeChange(next);
    }

    function handleStringInput(event: Event) {
        const value = (event.currentTarget as HTMLInputElement).value;
        onStringChange(value);
    }

    function handleSeasonInput(event: Event, index: number, key: keyof SeasonRow) {
        const value = (event.currentTarget as HTMLInputElement).value;
        onUpdateSeason(index, key, value);
    }
</script>

<div
    class={`rounded-xl border border-slate-600/40 bg-linear-to-br from-slate-900/75 via-slate-900/55 to-slate-800/45 p-4 shadow-[inset_0_1px_0_rgba(148,163,184,0.1)] ${field.type === "season" ? "md:col-span-2 xl:col-span-3" : ""}`}>
    <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2">
                <span class="text-[12px] font-semibold text-slate-100">
                    {field.label}
                </span>
            </div>
            {#if field.hint}
                <p class="text-[10px] text-slate-300">{field.hint}</p>
            {/if}
        </div>
        <select
            class="h-8 rounded-lg border border-slate-600/40 bg-slate-900/55 px-3 text-[10px] font-medium text-slate-100 transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
            value={selectedMode}
            onchange={handleModeChange}>
            {#each modeOptions as option (option)}
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

    {#if selectedMode === "value"}
        {#if field.type === "season"}
            <div class="mt-3 space-y-2">
                {#each rows as row, index (index)}
                    <div
                        class="flex flex-col gap-2 rounded-lg border border-slate-600/40 bg-slate-900/50 p-3 shadow-inner sm:flex-row sm:items-center">
                        <div class="flex items-center gap-2 sm:w-28">
                            <label
                                class="text-[10px] font-medium tracking-wide text-slate-300 uppercase"
                                for={`season-${field.id}-${index}`}>
                                Season
                            </label>
                            <input
                                id={`season-${field.id}-${index}`}
                                class="h-8 w-full rounded-lg border border-slate-600/45 bg-slate-900/55 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/25 focus:outline-none"
                                placeholder="s1"
                                value={row.season}
                                oninput={(event) =>
                                    handleSeasonInput(event, index, "season")} />
                        </div>
                        <div class="flex-1">
                            <label
                                class="sr-only"
                                for={`pattern-${field.id}-${index}`}>
                                Episode pattern
                            </label>
                            <input
                                id={`pattern-${field.id}-${index}`}
                                class="h-8 w-full rounded-lg border border-slate-600/45 bg-slate-900/55 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/25 focus:outline-none"
                                placeholder="e1-e12"
                                value={row.value}
                                oninput={(event) =>
                                    handleSeasonInput(event, index, "value")} />
                        </div>
                        <button
                            class="inline-flex h-8 items-center gap-1 rounded-lg border border-rose-600/45 bg-rose-900/25 px-3 text-[10px] font-medium text-rose-100 transition hover:bg-rose-900/40"
                            type="button"
                            onclick={() => onRemoveSeason(index)}>
                            <Trash2 class="h-3.5 w-3.5" />
                            Remove
                        </button>
                    </div>
                {/each}
                <button
                    class="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-500/45 bg-slate-800/55 px-3 text-[10px] font-semibold text-slate-100 transition hover:border-emerald-400/60 hover:bg-slate-800/70"
                    type="button"
                    onclick={onAddSeason}>
                    <Plus class="h-3.5 w-3.5" />
                    Add season mapping
                </button>
            </div>
        {:else}
            <input
                class="mt-3 h-9 w-full rounded-lg border border-slate-600/45 bg-slate-900/55 px-3 text-[11px] text-slate-100 shadow-inner transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/25 focus:outline-none"
                placeholder={field.placeholder}
                value={stringValue}
                oninput={handleStringInput} />
        {/if}
    {:else if selectedMode === "null"}
        <p
            class="mt-3 rounded-lg border border-rose-600/35 bg-rose-900/25 p-3 text-[11px] text-rose-100">
            Field will be returned as <strong class="font-semibold text-rose-200"
                >null</strong>
            for this mapping.
        </p>
    {:else if field.type === "season"}
        {#if effectiveSeasonRows.length}
            <div class="mt-3 space-y-2">
                {#each effectiveSeasonRows as row, index (index)}
                    <div
                        class="flex flex-col gap-2 rounded-lg border border-slate-600/40 bg-slate-900/45 p-3 text-slate-200 opacity-85 sm:flex-row sm:items-center">
                        <div class="flex items-center gap-2 sm:w-28">
                            <label
                                class="text-[10px] font-medium tracking-wide text-slate-300 uppercase"
                                for={`effective-${field.id}-season-${index}`}>
                                Season
                            </label>
                            <input
                                id={`effective-${field.id}-season-${index}`}
                                class="h-8 w-full rounded-lg border border-slate-600/40 bg-slate-900/45 px-3 text-[11px] text-slate-200 shadow-inner"
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
                                class="h-8 w-full rounded-lg border border-slate-600/40 bg-slate-900/45 px-3 text-[11px] text-slate-200 shadow-inner"
                                value={row.value}
                                disabled
                                readonly />
                        </div>
                    </div>
                {/each}
            </div>
        {:else}
            <p
                class="mt-3 rounded-lg border border-slate-600/35 bg-slate-900/40 p-3 text-[11px] text-slate-200">
                {effectiveText}
            </p>
        {/if}
    {:else}
        <div class="mt-3 space-y-2">
            <input
                class="h-9 w-full rounded-lg border border-slate-600/40 bg-slate-900/45 px-3 text-[11px] text-slate-200 opacity-85"
                value={effectiveText}
                disabled
                readonly />
            <p class="text-[10px] text-slate-300">Upstream value in effect.</p>
        </div>
    {/if}
</div>
