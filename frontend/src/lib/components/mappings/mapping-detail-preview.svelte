<script lang="ts">
    import { createEventDispatcher } from "svelte";

    import { Globe, Loader2 } from "@lucide/svelte";

    import type { MappingDetail } from "$lib/types/api";
    import { preferredTitle } from "$lib/utils/anilist";

    interface Props {
        detail: MappingDetail | null;
        mode: "create" | "edit";
        loadingDetail: boolean;
        pendingPrefillId: number | null;
        loadedDetailId: number | null;
    }

    const dispatch = createEventDispatcher<{ prefill: void }>();

    let { detail, mode, loadingDetail, pendingPrefillId, loadedDetailId }: Props =
        $props();

    function handlePrefillClick() {
        if (loadingDetail) return;
        dispatch("prefill");
    }

    function resolveCoverImage(detailValue: MappingDetail | null) {
        if (!detailValue?.anilist?.coverImage) return null;
        const { coverImage } = detailValue.anilist;
        return (
            coverImage?.medium ?? coverImage?.large ?? coverImage?.extraLarge ?? null
        );
    }
</script>

<div
    class="h-full rounded-lg border border-slate-600/40 bg-slate-900/55 p-4 shadow-inner">
    {#if loadingDetail}
        <div class="flex min-w-0 animate-pulse items-start gap-3">
            <div class="block w-12 shrink-0">
                <div class="h-16 w-full rounded-md bg-slate-800/40"></div>
            </div>
            <div class="min-w-0 flex-1 space-y-3">
                <div class="h-4 w-3/4 rounded bg-slate-800/40"></div>
                <div class="h-3 w-1/2 rounded bg-slate-800/40"></div>
                <div class="flex flex-wrap gap-1 pt-1">
                    <div class="h-3 w-16 rounded bg-slate-800/40"></div>
                    <div class="h-3 w-14 rounded bg-slate-800/40"></div>
                    <div class="h-3 w-12 rounded bg-slate-800/40"></div>
                    <div class="h-3 w-10 rounded bg-slate-800/40"></div>
                </div>
            </div>
        </div>
    {:else if detail?.anilist}
        {@const coverImage = resolveCoverImage(detail)}
        <div class="flex min-w-0 items-start gap-3">
            <a
                href={`https://anilist.co/anime/${detail.anilist.id}`}
                rel="noopener noreferrer"
                target="_blank"
                class="group block w-12 shrink-0">
                {#if coverImage}
                    <div
                        class="relative h-16 w-full overflow-hidden rounded-md ring-1 ring-slate-500/40">
                        {#if mode === "create" && pendingPrefillId && pendingPrefillId !== loadedDetailId}
                            <div
                                class="mt-4 rounded-lg border border-emerald-900/40 bg-emerald-950/20 p-3 text-[10px] text-emerald-200">
                                <div
                                    class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                    <div class="text-left font-medium">
                                        AniList ID changed. Load details for {pendingPrefillId}?
                                    </div>
                                    <button
                                        class="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-800/60 bg-emerald-900/40 px-3 text-[10px] font-semibold text-emerald-100 transition hover:border-emerald-600/70 hover:bg-emerald-900/60 disabled:opacity-60"
                                        type="button"
                                        disabled={loadingDetail}
                                        onclick={handlePrefillClick}>
                                        {#if loadingDetail}
                                            <Loader2 class="h-3 w-3 animate-spin" />
                                        {:else}
                                            <Globe class="h-3 w-3" />
                                        {/if}
                                        Prefill new ID
                                    </button>
                                </div>
                            </div>
                        {/if}
                        <img
                            alt={(preferredTitle(detail.anilist.title) || "Cover") +
                                " cover"}
                            loading="lazy"
                            src={coverImage}
                            class="h-full w-full object-cover transition-[filter,transform] duration-150 ease-out group-hover:scale-105"
                            class:blur-sm={detail.anilist?.isAdult} />
                    </div>
                {:else}
                    <div
                        class="flex h-20 w-14 items-center justify-center rounded-md border border-dashed border-slate-600 bg-slate-800/30 text-[9px] text-slate-500 select-none">
                        No Art
                    </div>
                {/if}
            </a>
            <div class="min-w-0 flex-1 space-y-1">
                <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0 space-y-2">
                        <div
                            class="truncate font-semibold text-slate-100"
                            title={preferredTitle(detail.anilist.title) ||
                                `AniList ${detail.anilist.id}`}>
                            {#if detail?.anilist?.title}
                                {preferredTitle(detail.anilist.title)}
                            {:else}
                                AniList {detail.anilist.id}
                            {/if}
                        </div>
                        <div
                            class="mt-1 flex flex-wrap gap-1 text-[9px] text-slate-300">
                            {#if detail.anilist.format}
                                <span
                                    class="truncate rounded bg-slate-800/60 px-1.5 py-0.5 tracking-wide uppercase"
                                    title={detail.anilist.format}>
                                    {detail.anilist.format}
                                </span>
                            {/if}
                            {#if detail.anilist.status}
                                <span
                                    class="truncate rounded bg-slate-800/60 px-1.5 py-0.5 tracking-wide uppercase"
                                    title={detail.anilist.status}>
                                    {detail.anilist.status}
                                </span>
                            {/if}
                            {#if detail.anilist.season && detail.anilist.seasonYear}
                                <span
                                    class="truncate rounded bg-slate-800/60 px-1.5 py-0.5 tracking-wide uppercase"
                                    title={`${detail.anilist.season} ${detail.anilist.seasonYear}`}>
                                    {detail.anilist.season}
                                    {detail.anilist.seasonYear}
                                </span>
                            {/if}
                            {#if detail.anilist.episodes}
                                <span
                                    class="truncate rounded bg-slate-800/60 px-1.5 py-0.5"
                                    title={`${detail.anilist.episodes} episodes`}>
                                    EP {detail.anilist.episodes}
                                </span>
                            {/if}
                            {#if detail.anilist?.isAdult}
                                <span
                                    class="rounded bg-rose-800 px-1.5 py-0.5 text-rose-100"
                                    title="ADULT content">
                                    ADULT
                                </span>
                            {/if}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    {:else if mode === "create"}
        <div
            class="flex h-full flex-col items-center justify-center gap-3 text-center text-[11px] text-slate-200">
            <button
                class="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-500/40 bg-slate-900/55 px-3 text-[11px] font-semibold text-slate-100 transition hover:border-emerald-400/60 hover:bg-slate-900/70"
                type="button"
                onclick={handlePrefillClick}>
                {#if loadingDetail}
                    <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                    <Globe class="h-3.5 w-3.5" />
                {/if}
                Prefill from AniList
            </button>
            <p class="text-[10px] text-slate-500">
                Fetch the current mapping details before creating overrides.
            </p>
        </div>
    {:else}
        <div class="flex h-full items-center justify-center text-[11px] text-slate-500">
            No AniList details available.
        </div>
    {/if}
</div>
