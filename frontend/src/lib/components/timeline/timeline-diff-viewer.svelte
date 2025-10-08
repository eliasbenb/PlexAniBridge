<script lang="ts">
    import { ArrowRight, Copy, Search } from "@lucide/svelte";

    import JsonCodeBlock from "$lib/components/json-code-block.svelte";
    import type { DiffEntry, ItemDiffUi } from "$lib/components/timeline/types";
    import {
        buildDiff,
        sizeLabel,
        truncateValue,
    } from "$lib/components/timeline/utils";
    import type { HistoryItem } from "$lib/types/api";

    interface Props {
        item: HistoryItem;
        ui: ItemDiffUi;
    }

    let { item, ui }: Props = $props();

    const diffs = $derived<DiffEntry[]>(buildDiff(item));

    function copyJson(obj: unknown) {
        try {
            navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
        } catch {}
    }

    const filtered = $derived(
        diffs.filter((diff) => {
            if (!ui.showUnchanged && diff.status === "unchanged") return false;
            if (ui.filter && !diff.path.toLowerCase().includes(ui.filter.toLowerCase()))
                return false;
            return true;
        }),
    );
</script>

<div
    class="mt-2 overflow-hidden rounded-md border border-slate-800 bg-slate-950/80 will-change-transform">
    <div class="flex flex-wrap items-center gap-3 border-b border-slate-800 px-3 py-2">
        <div
            class="flex items-center overflow-hidden rounded-md border border-slate-700/70 bg-slate-900/60 text-[11px]">
            <button
                class={`px-2 py-1 font-medium ${ui.tab === "changes" ? "bg-slate-700/70 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}
                onclick={() => (ui.tab = "changes")}>
                Changes
            </button>
            <button
                class={`hidden px-2 py-1 font-medium md:inline-flex ${ui.tab === "compare" ? "bg-slate-700/70 text-slate-100" : "text-slate-400 hover:text-slate-200"}`}
                onclick={() => (ui.tab = "compare")}>
                Compare
            </button>
        </div>
        {#if ui.tab === "changes"}
            <div class="flex min-w-[12rem] grow items-center gap-2 text-[11px]">
                <div class="relative flex-1">
                    <Search
                        class="absolute top-1/2 left-1.5 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                    <input
                        bind:value={ui.filter}
                        placeholder="Filter path…"
                        class="w-full rounded-md border border-slate-700/70 bg-slate-900/60 py-1 pr-2 pl-6 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none" />
                </div>
                <label
                    class="inline-flex cursor-pointer items-center gap-1 select-none">
                    <input
                        type="checkbox"
                        checked={ui.showUnchanged}
                        onchange={(event: Event) => {
                            const target = event.target as HTMLInputElement;
                            ui.showUnchanged = target.checked;
                        }}
                        class="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-0" />
                    <span class="text-slate-400">Unchanged</span>
                </label>
            </div>
        {/if}
        <div class="ml-auto flex items-center gap-1">
            <button
                onclick={() => copyJson(item.before_state)}
                class="flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                title="Copy Before JSON">
                <Copy class="inline h-3.5 w-3.5" /> <span>Before</span>
            </button>
            <button
                onclick={() => copyJson(item.after_state)}
                class="flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                title="Copy After JSON">
                <Copy class="inline h-3.5 w-3.5" /> <span>After</span>
            </button>
        </div>
    </div>
    <div class="space-y-3 p-3">
        {#if ui.tab === "changes"}
            {#if filtered.length}
                <ul class="divide-y divide-slate-800/60 text-[11px]">
                    {#each filtered as diff (diff.path)}
                        <li class="group px-1 py-1.5">
                            <div class="flex flex-wrap items-start gap-2">
                                <span
                                    class="max-w-full rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] break-all text-slate-300 group-hover:bg-slate-700/80">
                                    {diff.path}
                                </span>
                                <div
                                    class="flex min-w-[10rem] flex-1 items-start gap-1.5">
                                    <span
                                        class={`min-w-0 break-all ${diff.status === "removed" ? "text-red-400" : diff.status === "changed" ? "text-red-300" : "text-slate-500"}`}
                                        >{truncateValue(diff.before)}</span>
                                    <ArrowRight
                                        class="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600" />
                                    <span
                                        class={`min-w-0 break-all ${diff.status === "added" ? "text-emerald-400" : diff.status === "changed" ? "text-emerald-300" : "text-slate-500"}`}
                                        >{truncateValue(diff.after)}</span>
                                </div>
                            </div>
                        </li>
                    {/each}
                </ul>
            {:else}
                <p class="text-[11px] text-slate-500 italic">No differences.</p>
            {/if}
        {:else}
            <div class="grid items-stretch gap-2 md:grid-cols-2 md:gap-3">
                <div class="flex h-full flex-col gap-1.5">
                    <h5
                        class="flex items-center gap-1 text-xs font-semibold tracking-wider text-slate-400 uppercase">
                        Before
                        <span class="text-[10px] font-normal text-slate-600">
                            {sizeLabel(item.before_state)}
                        </span>
                    </h5>
                    <div class="min-h-0 flex-1">
                        <JsonCodeBlock
                            value={item.before_state ?? {}}
                            class="h-full leading-tight" />
                    </div>
                </div>
                <div class="flex h-full flex-col gap-1.5">
                    <h5
                        class="flex items-center gap-1 text-xs font-semibold tracking-wider text-slate-400 uppercase">
                        After
                        <span class="text-[10px] font-normal text-slate-600">
                            {sizeLabel(item.after_state)}
                        </span>
                    </h5>
                    <div class="min-h-0 flex-1">
                        <JsonCodeBlock
                            value={item.after_state ?? {}}
                            class="h-full leading-tight" />
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
