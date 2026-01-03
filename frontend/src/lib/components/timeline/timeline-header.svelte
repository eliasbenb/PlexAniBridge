<script lang="ts">
    import { CloudDownload, History, RefreshCcw, RotateCw } from "@lucide/svelte";
    import { Meter } from "bits-ui";

    import type { CurrentSync } from "$lib/types/api";

    interface Props {
        profile: string;
        currentSync?: CurrentSync | null;
        isProfileRunning?: boolean;
        onFullSync: () => void;
        onPollSync: () => void;
        onRefresh: () => void;
    }

    let {
        profile,
        currentSync = null,
        isProfileRunning = false,
        onFullSync,
        onPollSync,
        onRefresh,
    }: Props = $props();

    function progressPercent(sync: CurrentSync | null): number | null {
        if (!sync || sync.state !== "running") return null;
        const secIdx = Math.max(0, (sync.section_index || 1) - 1);
        const secCount = Math.max(1, sync.section_count || 1);
        const total = Math.max(1, sync.section_items_total || 1);
        const done = Math.min(total, sync.section_items_processed || 0);
        const sectionFrac = total > 0 ? done / total : 0;
        const overall = (secIdx + sectionFrac) / secCount;
        return Math.max(0, Math.min(1, overall));
    }

    const hasRunningSync = () => currentSync?.state === "running";
    const percent = () => progressPercent(currentSync) ?? 0;
</script>

<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
    <div class="flex items-center gap-2">
        <History class="inline h-4 w-4 text-slate-300" />
        <h2 class="text-lg font-semibold">Sync Timeline</h2>
        <span class="text-xs text-slate-500">profile: <i>{profile}</i></span>
    </div>
    <div class="flex items-center gap-2 text-[11px]">
        <button
            onclick={onFullSync}
            type="button"
            class="inline-flex items-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-2 py-1 font-medium text-emerald-200 hover:bg-emerald-600/40 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isProfileRunning}
            ><RefreshCcw class="inline h-4 w-4 text-[14px]" /> Full Scan</button>
        <button
            onclick={onPollSync}
            type="button"
            class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-600/30 px-2 py-1 font-medium text-sky-200 hover:bg-sky-600/40 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isProfileRunning}
            ><CloudDownload class="inline h-4 w-4 text-[14px]" /> Poll Scan</button>
        <button
            onclick={onRefresh}
            type="button"
            class="inline-flex items-center gap-1 rounded-md border border-slate-600/60 bg-slate-700/40 px-2 py-1 font-medium text-slate-200 hover:bg-slate-600/50"
            ><RotateCw class="inline h-4 w-4 text-[14px]" /> Refresh</button>
    </div>
</div>
{#if hasRunningSync()}
    <div class="mt-2 space-y-2">
        <div class="flex items-center justify-between text-[11px] text-slate-400">
            <div class="truncate">
                {#if currentSync?.section_title}
                    <span class="text-slate-300">{currentSync.section_title}</span>
                    <span class="mx-1">•</span>
                {/if}
                <span class="tracking-wide uppercase"
                    >{currentSync?.stage || "processing"}</span>
            </div>
            <div>
                {currentSync?.section_items_processed || 0}/
                {currentSync?.section_items_total || 0}
            </div>
        </div>
        {#key currentSync?.section_index}
            <Meter.Root
                value={percent()}
                min={0}
                max={1}
                class="h-2 w-full overflow-hidden rounded bg-slate-800/80">
                <div
                    class="h-full bg-linear-to-r from-indigo-500 via-sky-500 to-cyan-400 transition-all duration-300 ease-out"
                    style="transform: translateX(-{100 - 100 * percent()}%)">
                </div>
            </Meter.Root>
        {/key}
    </div>
{/if}
