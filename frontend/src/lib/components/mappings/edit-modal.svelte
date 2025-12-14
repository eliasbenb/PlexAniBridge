<script lang="ts">
    import { CopyPlus, FileJson, RefreshCcw, Trash2 } from "@lucide/svelte";

    import CodeEditor from "$lib/components/code-editor.svelte";
    import type {
        Mapping,
        MappingDetail,
        MappingEdge,
        MappingOverridePayload,
    } from "$lib/types/api";
    import Modal from "$lib/ui/modal.svelte";
    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

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

    type OverrideEdgeInput = {
        target: string;
        source_range: string;
        destination_range: string | null;
    };

    const DESCRIPTOR_RE = /^[^:\s]+:[^:\s]+:[^:\s]+$/;

    let descriptorInput = $state<string>("");
    let targetsJson = $state<string>("{}");
    let overrideEdges = $state<OverrideEdgeInput[]>([
        { target: "", source_range: "", destination_range: null },
    ]);
    let overrideMode = $state<"structured" | "json">("structured");
    let detail = $state<MappingDetail | null>(null);
    let loadingDetail = $state(false);
    let saving = $state(false);
    let error = $state<string | null>(null);
    let showJson = $state(false);

    function getDescriptorError(): string | null {
        if (!descriptorInput.trim()) return "Descriptor is required";
        if (!DESCRIPTOR_RE.test(descriptorInput.trim())) {
            return "Use provider:entry:scope (e.g. anilist:1:movie)";
        }
        return null;
    }

    function getStructuredIssues(): { missing: number; total: number; valid: number } {
        const invalid = overrideEdges.filter(
            (e) => !e.target.trim() || !e.source_range.trim(),
        );
        return {
            missing: invalid.length,
            total: overrideEdges.length,
            valid: overrideEdges.length - invalid.length,
        };
    }

    function totalEdges(): number {
        return overrideEdges.filter(
            (e) => e.target.trim() || e.source_range.trim() || e.destination_range,
        ).length;
    }

    function prefillAvailable(): boolean {
        return Boolean(detail?.override_edges?.length || detail?.edges?.length);
    }

    function addEdgeFromExisting(edge: MappingEdge) {
        if (!edge) return;
        const target = `${edge.target_provider}:${edge.target_entry_id}:${edge.target_scope}`;
        overrideEdges = [
            ...overrideEdges,
            {
                target,
                source_range: edge.source_range,
                destination_range: edge.destination_range ?? null,
            },
        ];
        overrideMode = "structured";
        showJson = false;
        syncJsonFromEdges();
    }

    function cloneStructured(idx: number) {
        const targetEdge = overrideEdges[idx];
        if (!targetEdge) return;
        overrideEdges = [
            ...overrideEdges.slice(0, idx + 1),
            { ...targetEdge },
            ...overrideEdges.slice(idx + 1),
        ];
        syncJsonFromEdges();
    }

    const canSave = $derived(() => {
        if (saving) return false;
        const descriptorError = getDescriptorError();
        if (descriptorError) return false;
        const structuredIssues = getStructuredIssues();
        if (overrideMode === "structured" && structuredIssues.missing > 0) {
            return false;
        }
        return true;
    });

    function prefillFromDetailEdges() {
        const fromOverride = detail?.override_edges?.length
            ? detail.override_edges.map((edge) => ({
                  target: edge.target,
                  source_range: edge.source_range,
                  destination_range: edge.destination_range ?? null,
              }))
            : null;

        const fromUpstream = detail?.edges?.length
            ? detail.edges.map((edge) => ({
                  target: `${edge.target_provider}:${edge.target_entry_id}:${edge.target_scope}`,
                  source_range: edge.source_range,
                  destination_range: edge.destination_range ?? null,
              }))
            : null;

        const candidates = fromOverride ?? fromUpstream ?? [];
        if (!candidates.length) return;
        overrideEdges = candidates;
        syncJsonFromEdges();
        overrideMode = "structured";
    }

    function resetState() {
        descriptorInput = "";
        targetsJson = "{}";
        overrideEdges = [{ target: "", source_range: "", destination_range: null }];
        overrideMode = "structured";
        showJson = false;
        detail = null;
        loadingDetail = false;
        saving = false;
        error = null;
    }

    function edgesFromTargets(
        targets: Record<string, Record<string, string | null>> | null,
    ): OverrideEdgeInput[] {
        if (!targets) return [];
        const edges: OverrideEdgeInput[] = [];
        for (const [target, ranges] of Object.entries(targets)) {
            for (const [src, dst] of Object.entries(ranges || {})) {
                edges.push({
                    target,
                    source_range: src,
                    destination_range: dst ?? null,
                });
            }
        }
        return edges;
    }

    function targetsFromEdges(
        edges: OverrideEdgeInput[],
    ): Record<string, Record<string, string | null>> {
        const out: Record<string, Record<string, string | null>> = {};
        for (const edge of edges) {
            if (!edge.target || !edge.source_range) continue;
            const bucket = (out[edge.target] ||= {});
            bucket[edge.source_range] = edge.destination_range ?? null;
        }
        return out;
    }

    async function loadDetail(descriptor: string) {
        if (!descriptor) return;
        loadingDetail = true;
        error = null;
        try {
            const res = await apiFetch(
                `/api/mappings/${encodeURIComponent(descriptor)}`,
            );
            if (!res.ok) {
                if (res.status !== 404) {
                    toast(`Failed to load mapping (HTTP ${res.status})`, "error");
                }
                detail = null;
                overrideEdges = [
                    { target: "", source_range: "", destination_range: null },
                ];
                return;
            }
            const data = (await res.json()) as MappingDetail;
            detail = data;
            targetsJson = JSON.stringify(data.override ?? {}, null, 2) || "{}";
            overrideEdges = data.override_edges?.length
                ? [...data.override_edges].map((edge) => ({
                      target: edge.target,
                      source_range: edge.source_range,
                      destination_range: edge.destination_range ?? null,
                  }))
                : edgesFromTargets(data.override ?? {}) || [
                      { target: "", source_range: "", destination_range: null },
                  ];
        } catch {
            error = "Failed to load mapping";
            detail = null;
        } finally {
            loadingDetail = false;
        }
    }

    async function handleSave() {
        const descriptor = descriptorInput.trim();
        if (!descriptor) {
            error = "Descriptor is required (e.g. anilist:1:movie)";
            return;
        }

        let parsedTargets: Record<string, Record<string, string | null>> = {};
        let parsedEdges: OverrideEdgeInput[] = [];

        if (overrideMode === "json") {
            try {
                const raw = JSON.parse(targetsJson || "{}");
                parsedTargets = (raw ?? {}) as Record<
                    string,
                    Record<string, string | null>
                >;
                parsedEdges = edgesFromTargets(parsedTargets);
            } catch {
                error = "Targets JSON is invalid";
                return;
            }
        } else {
            const cleaned = overrideEdges
                .map((e) => ({
                    target: e.target.trim(),
                    source_range: e.source_range.trim(),
                    destination_range: e.destination_range?.trim() || null,
                }))
                .filter((e) => e.target || e.source_range || e.destination_range);

            if (cleaned.some((e) => !e.target || !e.source_range)) {
                error = "Each edge needs a target descriptor and source range";
                return;
            }

            parsedEdges = cleaned;
            parsedTargets = targetsFromEdges(cleaned);
            targetsJson = JSON.stringify(parsedTargets, null, 2) || "{}";
        }

        const payload: MappingOverridePayload = {
            descriptor,
            targets: parsedTargets,
            edges: parsedEdges,
        };

        saving = true;
        error = null;
        try {
            const method = mode === "edit" ? "PUT" : "POST";
            const url =
                mode === "edit"
                    ? `/api/mappings/${encodeURIComponent(descriptor)}`
                    : "/api/mappings";
            const res = await apiFetch(
                url,
                {
                    method,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                },
                {
                    successMessage:
                        mode === "edit" ? "Override updated" : "Override created",
                },
            );
            if (!res.ok) {
                error = `Save failed (HTTP ${res.status})`;
                return;
            }
            const data = (await res.json()) as MappingDetail;
            detail = data;
            onSaved?.(data);
            open = false;
        } catch {
            error = "Failed to save override";
        } finally {
            saving = false;
        }
    }

    $effect(() => {
        if (!open) {
            resetState();
            return;
        }

        const nextDescriptor = mode === "edit" ? (mapping?.descriptor ?? "") : "";
        descriptorInput = nextDescriptor;
        targetsJson = "{}";
        overrideEdges = [{ target: "", source_range: "", destination_range: null }];
        overrideMode = "structured";
        showJson = false;
        detail = null;
        if (mode === "edit" && nextDescriptor) {
            loadDetail(nextDescriptor);
        }
    });

    function renderEdgeSummary(edge: {
        target_provider: string;
        target_entry_id: string;
        target_scope: string;
        source_range: string;
        destination_range?: string | null;
    }) {
        return `${edge.target_provider}:${edge.target_entry_id}:${edge.target_scope} (src ${edge.source_range} → dest ${edge.destination_range ?? "all"})`;
    }

    function addEdge() {
        overrideEdges = [
            ...overrideEdges,
            { target: "", source_range: "", destination_range: null },
        ];
    }

    function removeEdge(idx: number) {
        overrideEdges = overrideEdges.filter((_, i) => i !== idx);
        if (!overrideEdges.length) {
            overrideEdges = [{ target: "", source_range: "", destination_range: null }];
        }
    }

    function syncJsonFromEdges() {
        targetsJson = JSON.stringify(targetsFromEdges(overrideEdges), null, 2) || "{}";
    }

    function syncEdgesFromJson() {
        try {
            const raw = JSON.parse(targetsJson || "{}");
            const parsed = (raw ?? {}) as Record<string, Record<string, string | null>>;
            const edges = edgesFromTargets(parsed);
            overrideEdges = edges.length
                ? edges
                : [{ target: "", source_range: "", destination_range: null }];
            error = null;
        } catch {
            error = "Targets JSON is invalid";
        }
    }
</script>

<Modal
    bind:open
    contentClass="fixed top-1/2 left-1/2 z-50 w-full max-w-6xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/90 shadow-2xl ring-1 ring-slate-800/60 backdrop-blur"
    headerWrapperClass="border-b border-slate-800/80 bg-slate-900/70 px-4 py-3"
    footerClass="flex items-center justify-end gap-3 border-t border-slate-800/70 bg-slate-900/70 px-4 py-3"
    closeButtonClass="rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/70 hover:text-slate-100">
    {#snippet titleChildren()}
        <div class="text-sm font-semibold tracking-wide text-slate-100">
            {mode === "edit" ? "Edit Mapping Override" : "Create Mapping Override"}
        </div>
    {/snippet}

    <div class="grid gap-4 p-4 xl:grid-cols-[1.6fr,1fr]">
        <div class="space-y-4">
            <div
                class="rounded-xl border border-slate-800 bg-slate-900/70 p-4 shadow-inner">
                <div class="flex flex-wrap items-center gap-2">
                    <div class="min-w-60 flex-1">
                        <label class="text-[12px] font-semibold text-slate-100">
                            Descriptor
                            <input
                                class="mt-1 h-10 w-full rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 text-[12px] text-slate-100 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
                                placeholder="provider:entry:scope (e.g. anilist:1:movie)"
                                bind:value={descriptorInput}
                                disabled={mode === "edit"} />
                        </label>
                        {#if getDescriptorError()}
                            <p class="mt-1 text-[11px] text-rose-300">
                                {getDescriptorError()}
                            </p>
                        {:else}
                            <p class="mt-1 text-[11px] text-slate-400">
                                Scope can be <span class="font-semibold text-slate-200"
                                    >movie</span>
                                or
                                <span class="font-semibold text-slate-200">s1/s2</span> for
                                seasons.
                            </p>
                        {/if}
                    </div>
                    <div class="flex flex-wrap items-center gap-2 text-[11px]">
                        <button
                            class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 font-semibold text-slate-100 hover:border-emerald-500 hover:text-emerald-100"
                            type="button"
                            onclick={prefillFromDetailEdges}
                            disabled={!prefillAvailable()}>
                            <CopyPlus class="h-3.5 w-3.5" />
                            Prefill from current
                        </button>
                        <button
                            class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 font-semibold text-slate-100 hover:border-emerald-500 hover:text-emerald-100"
                            type="button"
                            onclick={() => loadDetail(descriptorInput.trim())}
                            disabled={loadingDetail ||
                                !descriptorInput.trim() ||
                                Boolean(getDescriptorError())}>
                            <RefreshCcw class="h-3.5 w-3.5" />
                            Load existing
                        </button>
                        <button
                            class={`inline-flex items-center gap-1 rounded-md border px-3 py-2 font-semibold ${overrideMode === "structured" ? "border-emerald-500/60 bg-emerald-900/30 text-emerald-100" : "border-slate-700 bg-slate-800 text-slate-100"}`}
                            type="button"
                            onclick={() => {
                                overrideMode = "structured";
                                showJson = false;
                                syncEdgesFromJson();
                            }}>
                            Structured
                        </button>
                        <button
                            class={`inline-flex items-center gap-1 rounded-md border px-3 py-2 font-semibold ${showJson ? "border-emerald-500/60 bg-emerald-900/30 text-emerald-100" : "border-slate-700 bg-slate-800 text-slate-100"}`}
                            type="button"
                            onclick={() => {
                                showJson = !showJson;
                                overrideMode = showJson ? "json" : "structured";
                                if (showJson) {
                                    syncJsonFromEdges();
                                } else {
                                    syncEdgesFromJson();
                                }
                            }}>
                            <FileJson class="h-3.5 w-3.5" /> JSON
                        </button>
                    </div>
                </div>
            </div>

            <div
                class="rounded-xl border border-slate-800 bg-slate-900/70 p-4 shadow-inner">
                <div
                    class="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-slate-100">
                    <span class="rounded bg-slate-800/70 px-2 py-1"
                        >{totalEdges()} edge{totalEdges() === 1 ? "" : "s"}</span>
                    {#if overrideMode === "structured"}
                        {@const issues = getStructuredIssues()}
                        <span
                            class={`rounded px-2 py-1 ring-1 ${issues.missing > 0 ? "bg-amber-900/40 text-amber-100 ring-amber-800/50" : "bg-emerald-900/40 text-emerald-100 ring-emerald-800/40"}`}>
                            {issues.missing > 0
                                ? `${issues.missing} missing field${issues.missing === 1 ? "" : "s"}`
                                : "Ready"}
                        </span>
                    {/if}
                    <div class="flex-1"></div>
                    <button
                        class="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-[11px] font-semibold text-slate-100 hover:border-emerald-500 hover:text-emerald-100"
                        type="button"
                        onclick={addEdge}>
                        Add edge
                    </button>
                </div>

                {#if overrideMode === "structured"}
                    <div class="mt-3 space-y-2">
                        <div
                            class="grid gap-2 text-[11px] text-slate-400 md:grid-cols-[2fr,1fr,1fr,auto]">
                            <span>Target descriptor</span>
                            <span>Source range</span>
                            <span>Destination range</span>
                            <span class="text-right">Actions</span>
                        </div>
                        <div
                            class="divide-y divide-slate-800/60 rounded-md border border-slate-800 bg-slate-950/40">
                            {#each overrideEdges as edge, idx (idx)}
                                {@const targetId = `edge-target-${idx}`}
                                {@const sourceId = `edge-source-${idx}`}
                                {@const destId = `edge-dest-${idx}`}
                                <div
                                    class="grid gap-2 px-3 py-3 md:grid-cols-[2fr,1fr,1fr,auto] md:items-center">
                                    <input
                                        id={targetId}
                                        class="h-10 w-full rounded-md border border-slate-700/60 bg-slate-950/70 px-2 text-[12px] text-slate-100 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
                                        placeholder="provider:entry:scope"
                                        bind:value={edge.target} />
                                    <input
                                        id={sourceId}
                                        class="h-10 w-full rounded-md border border-slate-700/60 bg-slate-950/70 px-2 text-[12px] text-slate-100 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
                                        placeholder="1-12"
                                        bind:value={edge.source_range} />
                                    <input
                                        id={destId}
                                        class="h-10 w-full rounded-md border border-slate-700/60 bg-slate-950/70 px-2 text-[12px] text-slate-100 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
                                        placeholder="all / 1-12"
                                        bind:value={edge.destination_range} />
                                    <div class="flex items-center justify-end gap-2">
                                        <button
                                            class="rounded-md border border-slate-800 px-2 py-2 text-slate-400 hover:border-emerald-600 hover:bg-emerald-900/40 hover:text-emerald-100"
                                            type="button"
                                            title="Duplicate"
                                            onclick={() => cloneStructured(idx)}>
                                            <CopyPlus class="h-4 w-4" />
                                        </button>
                                        <button
                                            class="rounded-md border border-slate-800 px-2 py-2 text-slate-400 hover:border-rose-700 hover:bg-rose-900/40 hover:text-rose-100"
                                            type="button"
                                            title="Remove edge"
                                            onclick={() => removeEdge(idx)}>
                                            <Trash2 class="h-4 w-4" />
                                        </button>
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>
                {/if}

                {#if showJson}
                    <div class="mt-4 space-y-2">
                        <div
                            class="flex items-center justify-between text-[11px] text-slate-300">
                            <span>Advanced JSON editor</span>
                            <button
                                class="text-emerald-300 hover:underline"
                                type="button"
                                onclick={syncEdgesFromJson}>
                                Sync to structured
                            </button>
                        </div>
                        <CodeEditor
                            language="json"
                            class="h-72"
                            bind:content={targetsJson} />
                    </div>
                {/if}

                {#if error}
                    <div
                        class="mt-3 rounded-md border border-rose-700/60 bg-rose-900/40 px-3 py-2 text-[11px] text-rose-100">
                        {error}
                    </div>
                {/if}
            </div>
        </div>

        <div class="space-y-3">
            <div
                class="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-[11px] text-slate-200 shadow-inner">
                <div class="mb-2 flex items-center justify-between">
                    <span class="text-[12px] font-semibold text-slate-100"
                        >Preview</span>
                    {#if mode === "edit" && mapping?.descriptor}
                        <button
                            class="text-emerald-300 hover:underline"
                            type="button"
                            onclick={() => loadDetail(mapping.descriptor)}
                            disabled={loadingDetail}>
                            Refresh
                        </button>
                    {/if}
                </div>
                {#if loadingDetail}
                    <div class="text-slate-400">Loading…</div>
                {:else if detail}
                    <div class="space-y-2">
                        <div class="text-[12px] font-semibold text-slate-100">
                            {detail.descriptor}
                        </div>
                        <div
                            class="rounded border border-slate-700/60 bg-slate-900/60 p-2">
                            {#if detail.edges?.length}
                                <ul class="space-y-2">
                                    {#each detail.edges as edge (renderEdgeSummary(edge))}
                                        <li
                                            class="flex items-start justify-between gap-2 text-slate-300">
                                            <span class="leading-tight"
                                                >{renderEdgeSummary(edge)}</span>
                                            <button
                                                class="rounded-md border border-slate-700 px-2 py-1 text-[11px] font-semibold text-slate-100 hover:border-emerald-500 hover:text-emerald-100"
                                                type="button"
                                                title="Add override for this edge"
                                                onclick={() =>
                                                    addEdgeFromExisting(edge)}>
                                                Override
                                            </button>
                                        </li>
                                    {/each}
                                </ul>
                                <p class="mt-2 text-[10px] text-slate-500">
                                    Unchanged edges remain inherited; add overrides to
                                    modify them.
                                </p>
                            {:else}
                                <div class="text-slate-500">No outgoing edges</div>
                            {/if}
                        </div>
                        {#if detail.override_edges?.length}
                            <div class="space-y-1 text-[11px] text-slate-300">
                                <div class="text-[12px] font-semibold text-slate-100">
                                    Override edges
                                </div>
                                <ul class="space-y-1">
                                    {#each detail.override_edges as edge, i (i)}
                                        <li class="text-slate-300">
                                            {edge.target}: {edge.source_range} → {edge.destination_range ??
                                                "all"}
                                        </li>
                                    {/each}
                                </ul>
                            </div>
                        {/if}
                        {#if detail.sources?.length}
                            <div class="text-slate-400">
                                Sources: {detail.sources.join(", ")}
                            </div>
                        {/if}
                    </div>
                {:else}
                    <div class="text-slate-500">No detail loaded.</div>
                {/if}
            </div>
        </div>
    </div>

    {#snippet footerChildren()}
        <div class="flex w-full justify-end gap-2">
            <button
                class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-[12px] font-semibold text-slate-200 hover:bg-slate-800"
                type="button"
                onclick={() => (open = false)}>
                Cancel
            </button>
            <button
                class="rounded-lg bg-emerald-600 px-3 py-2 text-[12px] font-semibold text-emerald-50 shadow hover:bg-emerald-500 disabled:opacity-60"
                type="button"
                onclick={handleSave}
                disabled={!canSave}
                aria-disabled={!canSave}>
                {saving
                    ? "Saving..."
                    : mode === "edit"
                      ? "Save Changes"
                      : "Create Override"}
            </button>
        </div>
    {/snippet}
</Modal>
