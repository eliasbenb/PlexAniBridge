<script lang="ts">
    import { createEventDispatcher } from "svelte";

    import { ArrowUp, LoaderCircle, Pin, PinOff, RefreshCcw } from "@lucide/svelte";

    import type { PinFieldOption, PinResponse } from "$lib/types/api";

    interface Props {
        pinEntries?: PinResponse[];
        pinOptions?: PinFieldOption[];
        managePinsExpanded?: boolean;
        managePinsLoading?: boolean;
        pinCount?: number;
        pinEntryTitle: (anilistId: number) => string;
        pinFieldLabel: (field: string) => string;
        editorIsOpen: (key: string) => boolean;
        ensurePinSelection: (anilistId: number) => Set<string>;
        isPinDirty: (anilistId: number) => boolean;
        isPinSaving: (anilistId: number) => boolean;
    }

    let {
        pinEntries = [],
        pinOptions = [],
        managePinsExpanded = false,
        managePinsLoading = false,
        pinCount = 0,
        pinEntryTitle,
        pinFieldLabel,
        editorIsOpen,
        ensurePinSelection,
        isPinDirty,
        isPinSaving,
    }: Props = $props();

    const dispatch = createEventDispatcher<{
        refresh: void;
        toggleExpanded: void;
        toggleEditor: { key: string; anilistId: number | null | undefined };
        clear: { anilistId: number };
        toggleField: { anilistId: number; field: string };
        save: { anilistId: number };
        reset: { anilistId: number };
    }>();

    const hasEntries = () => pinEntries.length > 0;
</script>

<div class="rounded-md border border-slate-800/60 bg-slate-900/40 p-4 shadow-sm">
    <div
        class="flex flex-wrap items-center justify-between gap-3 text-[12px] text-slate-300">
        <div class="inline-flex items-center gap-2 font-semibold">
            <Pin class="h-4 w-4 text-sky-400" /> Manage Pins
            <span class="rounded bg-slate-800/80 px-2 py-0.5 text-[10px] text-slate-300"
                >{pinCount} active</span>
        </div>
        <div class="flex items-center gap-2">
            <button
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 px-2 py-0.5 text-[11px] text-slate-200 hover:bg-slate-800/70"
                onclick={() => dispatch("refresh")}
                ><RefreshCcw class="h-3.5 w-3.5" /> Refresh</button>
            <button
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-sky-700/60 px-2 py-0.5 text-[11px] text-sky-200 hover:bg-sky-800/60"
                onclick={() => dispatch("toggleExpanded")}
                >{managePinsExpanded ? "Hide" : "Show"} details
                <ArrowUp
                    class={`h-3.5 w-3.5 transition-transform ${managePinsExpanded ? "rotate-0" : "rotate-180"}`} /></button>
        </div>
    </div>
    {#if managePinsExpanded}
        <div class="mt-3 border-t border-slate-800/70 pt-3 text-[12px] text-slate-300">
            {#if managePinsLoading}
                <div class="flex items-center gap-2 text-slate-400">
                    <LoaderCircle class="h-4 w-4 animate-spin" /> Loading pinned entries…
                </div>
            {:else if !hasEntries()}
                <div class="flex items-center gap-2 text-slate-400">
                    <PinOff class="h-4 w-4" /> No pins configured yet.
                    <span class="text-[11px] text-slate-500"
                        >Use the Pin buttons on timeline entries to get started.</span>
                </div>
            {:else}
                <div class="space-y-3">
                    {#each pinEntries as entry (entry.anilist_id)}
                        {@const editorKey = `manage-${entry.anilist_id}`}
                        <div
                            class="rounded-md border border-slate-800/70 bg-slate-900/50 p-3">
                            <div
                                class="flex flex-wrap items-center justify-between gap-3">
                                <div class="min-w-0">
                                    <div class="text-[13px] font-medium text-slate-200">
                                        {pinEntryTitle(entry.anilist_id)}
                                    </div>
                                    <div class="text-[10px] text-slate-500">
                                        AniList #{entry.anilist_id} • Updated
                                        {new Date(entry.updated_at).toLocaleString()}
                                    </div>
                                    <div
                                        class="mt-2 flex flex-wrap gap-1 text-[10px] text-slate-300">
                                        {#if entry.fields.length}
                                            {#each entry.fields as field (field)}
                                                <span
                                                    class="rounded bg-sky-900/40 px-1.5 py-0.5 text-sky-200">
                                                    {pinFieldLabel(field)}
                                                </span>
                                            {/each}
                                        {:else}
                                            <span class="text-slate-500"
                                                >No fields pinned</span>
                                        {/if}
                                    </div>
                                </div>
                                <div class="flex items-center gap-2 text-[11px]">
                                    <button
                                        type="button"
                                        class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 px-2 py-0.5 hover:bg-slate-800/60"
                                        onclick={() =>
                                            dispatch("toggleEditor", {
                                                key: editorKey,
                                                anilistId: entry.anilist_id,
                                            })}
                                        >{editorIsOpen(editorKey)
                                            ? "Close"
                                            : "Edit"}</button>
                                    <button
                                        type="button"
                                        class="inline-flex items-center gap-1 rounded-md border border-rose-700/60 px-2 py-0.5 text-rose-200 hover:bg-rose-700/60"
                                        onclick={() =>
                                            dispatch("clear", {
                                                anilistId: entry.anilist_id,
                                            })}
                                        ><PinOff class="h-3.5 w-3.5" /> Clear</button>
                                </div>
                            </div>
                            {#if editorIsOpen(editorKey)}
                                <div
                                    class="mt-3 space-y-3 rounded-md border border-slate-800/70 bg-slate-950/50 p-3 text-[11px] text-slate-200">
                                    {#if pinOptions.length}
                                        <div class="flex flex-wrap gap-2">
                                            {#each pinOptions as option (option.value)}
                                                {@const selection = ensurePinSelection(
                                                    entry.anilist_id,
                                                )}
                                                <label
                                                    class={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] transition ${selection.has(option.value) ? "border-sky-600 bg-sky-900/40 text-sky-100" : "border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-600"}`}
                                                    ><input
                                                        type="checkbox"
                                                        class="h-3 w-3"
                                                        checked={selection.has(
                                                            option.value,
                                                        )}
                                                        onchange={() =>
                                                            dispatch("toggleField", {
                                                                anilistId:
                                                                    entry.anilist_id,
                                                                field: option.value,
                                                            })} />
                                                    {option.label}</label>
                                            {/each}
                                        </div>
                                    {:else}
                                        <div class="text-slate-400">
                                            Pin options unavailable. Try refreshing.
                                        </div>
                                    {/if}
                                    <div class="flex flex-wrap items-center gap-2">
                                        <button
                                            type="button"
                                            class="inline-flex items-center gap-1 rounded-md border border-sky-600/70 bg-sky-700/40 px-2 py-0.5 text-sky-100 hover:bg-sky-600/50 disabled:opacity-50"
                                            disabled={!isPinDirty(entry.anilist_id) ||
                                                isPinSaving(entry.anilist_id)}
                                            onclick={() =>
                                                dispatch("save", {
                                                    anilistId: entry.anilist_id,
                                                })}
                                            >{#if isPinSaving(entry.anilist_id)}
                                                <LoaderCircle
                                                    class="h-3.5 w-3.5 animate-spin" />
                                                Saving…
                                            {:else}
                                                Save
                                            {/if}</button>
                                        <button
                                            type="button"
                                            class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 px-2 py-0.5 text-slate-200 hover:bg-slate-800/60"
                                            onclick={() =>
                                                dispatch("reset", {
                                                    anilistId: entry.anilist_id,
                                                })}>Reset</button>
                                    </div>
                                </div>
                            {/if}
                        </div>
                    {/each}
                </div>
            {/if}
        </div>
    {/if}
</div>
