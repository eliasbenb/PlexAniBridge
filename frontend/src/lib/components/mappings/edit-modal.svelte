<script lang="ts">
    import CodeEditor from "$lib/components/code-editor.svelte";
    import type {
        Mapping,
        MappingDetail,
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

    let descriptorInput = $state<string>("");
    let targetsJson = $state<string>("{}");
    let detail = $state<MappingDetail | null>(null);
    let loadingDetail = $state(false);
    let saving = $state(false);
    let error = $state<string | null>(null);

    function resetState() {
        descriptorInput = "";
        targetsJson = "{}";
        detail = null;
        loadingDetail = false;
        saving = false;
        error = null;
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
                return;
            }
            const data = (await res.json()) as MappingDetail;
            detail = data;
            targetsJson = JSON.stringify(data.override ?? {}, null, 2) || "{}";
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

        let parsed: Record<string, Record<string, string | null>>;
        try {
            const raw = JSON.parse(targetsJson || "{}");
            parsed = (raw ?? {}) as Record<string, Record<string, string | null>>;
        } catch {
            error = "Targets JSON is invalid";
            return;
        }

        const payload: MappingOverridePayload = { descriptor, targets: parsed };

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
</script>

<Modal
    bind:open
    contentClass="fixed top-1/2 left-1/2 z-50 w-full max-w-5xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-md border border-slate-800 bg-slate-950/85 shadow-2xl ring-1 ring-slate-800/50 backdrop-blur"
    headerWrapperClass="border-b border-slate-800/80 bg-slate-900/70 px-4 py-3"
    footerClass="flex items-center justify-end gap-2 border-t border-slate-800/70 bg-slate-900/70 px-4 py-3"
    closeButtonClass="rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/70 hover:text-slate-100">
    {#snippet titleChildren()}
        <div class="text-sm font-semibold tracking-wide text-slate-100">
            {mode === "edit" ? "Edit Mapping Override" : "Create Mapping Override"}
        </div>
    {/snippet}

    <div class="grid gap-4 p-4 md:grid-cols-3">
        <div class="space-y-3 md:col-span-2">
            <div
                class="space-y-2 rounded-lg border border-slate-700/50 bg-slate-900/60 p-3 shadow-inner">
                <label class="text-[12px] font-semibold text-slate-100">
                    Descriptor
                    <input
                        class="mt-1 h-9 w-full rounded-lg border border-slate-700/60 bg-slate-950/60 px-3 text-[12px] text-slate-100 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 focus:outline-none"
                        placeholder="provider:entry:scope (e.g. anilist:1:movie)"
                        bind:value={descriptorInput}
                        disabled={mode === "edit"} />
                </label>

                <div class="space-y-1">
                    <div class="flex items-center justify-between">
                        <div class="text-[12px] font-semibold text-slate-100">
                            Targets JSON
                        </div>
                        {#if detail}
                            <button
                                class="text-[11px] text-emerald-300 hover:underline"
                                type="button"
                                onclick={() =>
                                    (targetsJson =
                                        JSON.stringify(
                                            detail?.override ?? {},
                                            null,
                                            2,
                                        ) || "{}")}>Use loaded override</button>
                        {/if}
                    </div>
                    <p class="text-[11px] text-slate-400">
                        Map destination descriptors to range pairs (e.g. tmdb:10:movie ⇒
                        movie:null).
                    </p>
                </div>
                <CodeEditor
                    language="json"
                    class="h-80"
                    bind:content={targetsJson} />
                {#if error}
                    <div
                        class="rounded-md border border-rose-700/60 bg-rose-900/40 px-3 py-2 text-[11px] text-rose-100">
                        {error}
                    </div>
                {/if}
            </div>
        </div>
        <div class="space-y-3">
            <div
                class="rounded-lg border border-slate-700/50 bg-slate-900/70 p-3 text-[11px] text-slate-200">
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
                                <ul class="space-y-1">
                                    {#each detail.edges as edge (renderEdgeSummary(edge))}
                                        <li class="text-slate-300">
                                            {renderEdgeSummary(edge)}
                                        </li>
                                    {/each}
                                </ul>
                            {:else}
                                <div class="text-slate-500">No outgoing edges</div>
                            {/if}
                        </div>
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
                disabled={saving}>
                {saving
                    ? "Saving..."
                    : mode === "edit"
                      ? "Save Changes"
                      : "Create Override"}
            </button>
        </div>
    {/snippet}
</Modal>
