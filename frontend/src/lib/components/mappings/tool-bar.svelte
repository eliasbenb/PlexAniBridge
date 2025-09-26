<script lang="ts">
    import { Check, Plus } from "@lucide/svelte";
    import { twMerge } from "tailwind-merge";

    import BooruSearch from "$lib/components/mappings/booru-search.svelte";

    interface Props {
        class?: string;
        query?: string;
        customOnly?: boolean;
        page?: number;
        onLoad: () => void;
        onNew: () => void;
    }

    let {
        class: className = "",
        query = $bindable(""),
        customOnly = $bindable(false),
        page = $bindable(1),
        onLoad,
        onNew,
    }: Props = $props();

    function toggleCustom() {
        customOnly = !customOnly;
        page = 1;
        onLoad();
    }
</script>

<!-- Desktop -->
<div class={twMerge("hidden items-center gap-2 text-[11px] sm:flex", className)}>
    <div class="relative w-64 md:w-96">
        <BooruSearch
            bind:value={query}
            size="md"
            onSubmit={() => {
                page = 1;
                onLoad();
            }}
        />
    </div>
    <button
        onclick={toggleCustom}
        class={`inline-flex h-8 items-center gap-1 rounded-md px-3 text-[11px] font-medium ring-1 ${customOnly ? "bg-emerald-600/90 text-white ring-emerald-500/40 hover:bg-emerald-500" : "bg-slate-800 text-slate-300 ring-slate-700/60 hover:bg-slate-700"}`}
    >
        {#if customOnly}
            <Check class="inline h-3.5 w-3.5 text-[14px]" />
        {:else}
            <svg
                class="inline h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                ><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg
            >
        {/if}
        <span>Custom Only</span>
    </button>
    <div class="ml-auto flex items-center gap-2">
        <button
            title="New Override"
            aria-label="New Override"
            class="inline-flex h-8 items-center gap-1 rounded-md bg-emerald-600/90 px-3 text-[11px] font-medium text-emerald-50 hover:bg-emerald-500"
            onclick={onNew}
        >
            <Plus class="inline h-3.5 w-3.5 text-[14px]" />
        </button>
    </div>
</div>

<!-- Mobile -->
<div
    class={twMerge(
        "flex flex-col gap-3 rounded-md border border-slate-800/70 bg-slate-900/60 p-3 text-[11px] sm:hidden",
        className,
    )}
>
    <div class="relative">
        <BooruSearch
            bind:value={query}
            size="md"
            onSubmit={() => {
                page = 1;
                onLoad();
            }}
        />
    </div>
    <div class="flex flex-wrap items-center justify-between">
        <button
            onclick={toggleCustom}
            class={`inline-flex h-8 items-center gap-1 rounded-md px-3 text-[11px] font-medium ring-1 ${customOnly ? "bg-emerald-600/90 text-white ring-emerald-500/40 hover:bg-emerald-500" : "bg-slate-800 text-slate-300 ring-slate-700/60 hover:bg-slate-700"}`}
        >
            {#if customOnly}
                <Check class="inline h-3.5 w-3.5" />
            {:else}
                <svg
                    class="inline h-3.5 w-3.5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    ><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg
                >
            {/if}
            <span>Custom Only</span>
        </button>
        <button
            title="New Override"
            aria-label="New Override"
            class="inline-flex h-8 items-center gap-1 rounded-md bg-emerald-600/90 px-3 text-[11px] font-medium text-emerald-50 hover:bg-emerald-500"
            onclick={onNew}
        >
            <Plus class="inline h-3.5 w-3.5 text-[14px]" />
        </button>
    </div>
</div>
