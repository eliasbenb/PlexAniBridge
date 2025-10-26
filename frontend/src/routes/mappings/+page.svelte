<script lang="ts">
    import { onMount } from "svelte";

    import { Check, Eye, List, RefreshCcw } from "@lucide/svelte";
    import { Checkbox, Popover } from "bits-ui";
    import { SvelteURLSearchParams } from "svelte/reactivity";

    import {
        defaultColumns,
        type ColumnConfig,
    } from "$lib/components/mappings/columns";
    import MappingsTable from "$lib/components/mappings/mappings-table.svelte";
    import SearchBar from "$lib/components/mappings/tool-bar.svelte";
    import Pagination from "$lib/components/pagination.svelte";
    import type { Mapping } from "$lib/types/api";
    import { apiFetch, isAbortError } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

    let items: Mapping[] = $state([]);
    let total = $state(0);
    let page = $state(1);
    let pages = $state(1);
    let perPage = $state(25);
    let query = $state("");
    let customOnly = $state(false);
    let loading = $state(false);

    let currentAbort: AbortController | null = null;

    async function load() {
        const controller = new AbortController();
        if (currentAbort) {
            currentAbort.abort();
        }
        currentAbort = controller;
        loading = true;
        try {
            const p = new SvelteURLSearchParams({
                page: String(page),
                per_page: String(perPage),
            });
            if (query) p.set("q", query);
            if (customOnly) p.set("custom_only", "true");
            const titleVisible = columns.some(
                (column) => column.id === "title" && column.visible,
            );
            if (titleVisible) p.set("with_anilist", "true");
            const r = await apiFetch("/api/mappings?" + p.toString(), {
                signal: controller.signal,
            });
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            items = d.items || [];
            total = d.total || 0;
            pages = d.pages || 1;
            page = d.page || page;
        } catch (e) {
            if (isAbortError(e)) return;
            console.error("load mappings failed", e);
            toast("Failed to load mappings", "error");
        } finally {
            if (currentAbort === controller) {
                currentAbort = null;
                loading = false;
            }
        }
    }

    function cancelLoad() {
        if (!currentAbort) return;
        currentAbort.abort();
        currentAbort = null;
        loading = false;
    }

    let columns = $state<ColumnConfig[]>(restoreColumns());
    let previousTitleVisible: boolean | null = $state(null); // when title visible changes, refetch with toggled `with_anilist`

    function restoreColumns(): ColumnConfig[] {
        try {
            const raw = localStorage.getItem("mappings.columns.v1");
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    const map = new Map(parsed.map((c: ColumnConfig) => [c.id, c]));
                    return defaultColumns.map((d) => ({
                        ...d,
                        ...(map.get(d.id) || {}),
                    }));
                }
            }
        } catch {}
        return [...defaultColumns];
    }

    function hideAllColumns() {
        columns = columns.map((c) => ({ ...c, visible: false }));
    }

    function showAllColumns() {
        columns = columns.map((c) => ({ ...c, visible: true }));
    }

    function resetColumns() {
        columns = [...defaultColumns];
    }

    $effect(() => {
        try {
            localStorage.setItem("mappings.columns.v1", JSON.stringify(columns));
        } catch {}
    });

    $effect(() => {
        const current = columns.some(
            (column) => column.id === "title" && column.visible,
        );
        if (previousTitleVisible === null) {
            previousTitleVisible = current;
            return;
        }
        if (current !== previousTitleVisible) {
            previousTitleVisible = current;
            load();
        }
    });

    onMount(load);
</script>

<div class="space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="space-y-1 sm:flex-1">
            <div class="flex items-center gap-2">
                <List class="inline h-4 w-4 text-slate-300" />
                <h2 class="text-lg font-semibold">Mappings</h2>
            </div>
            <p class="text-xs text-slate-400">
                Browse and override external ID mappings
            </p>
        </div>
        <SearchBar
            bind:query
            bind:customOnly
            bind:page
            {loading}
            onLoad={load}
            onCancel={cancelLoad} />
    </div>
    <div
        class="relative flex h-[70vh] flex-col overflow-hidden rounded-md border border-slate-800/70 bg-slate-900/40 backdrop-blur-sm">
        <div
            class="flex items-center gap-4 border-b border-slate-800/60 bg-slate-950/50 px-3 py-2 text-[11px]">
            <span class="text-slate-400"
                >Showing <span class="font-medium text-slate-200">{items.length}</span
                >/<span class="text-slate-500">{total}</span></span>
            {#if pages > 1}<span class="text-slate-500">Page {page} / {pages}</span
                >{/if}
            {#if customOnly}<span class="text-emerald-400">Custom overrides only</span
                >{/if}
            <span class="flex-1"></span>
            <button
                onclick={load}
                class="-mr-2 inline-flex h-6 w-6 items-center justify-center rounded bg-slate-800/50 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                title="Refresh"
                aria-label="Refresh">
                <RefreshCcw class="h-4 w-4" />
            </button>
            <!-- Column settings popover -->
            <Popover.Root>
                <Popover.Trigger
                    class="inline-flex h-6 w-6 items-center justify-center rounded bg-slate-800/50 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                    title="Column settings"
                    aria-label="Column settings">
                    <Eye class="h-4 w-4" />
                </Popover.Trigger>
                <Popover.Content
                    class="z-50 w-64 rounded-md border border-slate-700 bg-slate-900 p-3 shadow-lg"
                    side="bottom"
                    align="end"
                    sideOffset={4}>
                    <div class="flex items-center justify-between">
                        <h3 class="text-sm font-medium text-slate-200">
                            Column Visibility
                        </h3>
                        {#if columns.some((c) => !c.visible)}<button
                                onclick={showAllColumns}
                                class="text-xs text-slate-400 hover:text-slate-200"
                                >Show All</button>
                        {:else}
                            <button
                                onclick={hideAllColumns}
                                class="text-xs text-slate-400 hover:text-slate-200"
                                >Hide All</button>
                        {/if}
                    </div>
                    <div>
                        <button
                            onclick={resetColumns}
                            class="muted mb-3 text-xs text-slate-400 italic hover:text-slate-200">
                            (reset)
                        </button>
                    </div>
                    <div class="space-y-2">
                        {#each columns as column (column.id)}
                            <div class="flex items-center gap-2">
                                <label
                                    class="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
                                    <Checkbox.Root
                                        bind:checked={column.visible}
                                        class="flex h-4 w-4 items-center justify-center rounded border border-slate-600 bg-slate-800 data-[state=checked]:border-emerald-600 data-[state=checked]:bg-emerald-600">
                                        {#snippet children({ checked, indeterminate })}
                                            {#if indeterminate}
                                                <div
                                                    class="h-2 w-2 rounded-sm bg-white">
                                                </div>
                                            {:else if checked}
                                                <Check class="h-3 w-3 text-white" />
                                            {/if}
                                        {/snippet}
                                    </Checkbox.Root>
                                    <span class="truncate select-none"
                                        >{column.title}</span>
                                </label>
                            </div>
                        {/each}
                    </div>
                </Popover.Content>
            </Popover.Root>
        </div>
        <MappingsTable
            {items}
            bind:columns />
    </div>
    <Pagination
        class="mt-3"
        bind:page
        bind:perPage
        bind:pages
        onChange={load} />
</div>
