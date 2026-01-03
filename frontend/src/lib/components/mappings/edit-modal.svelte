<script lang="ts">
    import { Info, Plus, RefreshCcw, Save, Trash2 } from "@lucide/svelte";
    import { Tooltip } from "bits-ui";

    import type {
        Mapping,
        MappingDetail,
        MappingOverridePayload,
        MappingTarget,
        TargetPayload,
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

    type RangeMode = "inherited" | "custom";

    type EditableRange = {
        source_range: string;
        upstream_value: string | null;
        custom_value: string | null;
        mode: RangeMode;
        original_source_range: string;
    };

    type EditableEntry = {
        key: string;
        provider: string;
        entry_id: string;
        scope: string;
        provider_placeholder: string;
        entry_id_placeholder: string;
        scope_placeholder: string;
        origin: "upstream" | "custom" | "mixed" | "deleted";
        deleted: boolean;
        original_descriptor: string;
        ranges: EditableRange[];
    };

    const DESCRIPTOR_RE = /^[^:\s]+:[^:\s]+:[^:\s]+$/;

    const fieldInfo = {
        provider:
            "Provider that the override belongs to (e.g. 'anilist', 'tvdb_show', 'tmdb_movie').",
        entryId: "Entry identifier from the provider that the override targets.",
        scope: "Scope to apply the override for (e.g. 'movie', 'sX').",
    } as const;

    const rangeFieldInfo = {
        source: "Source number range to match (e.g. '1', '1-12').",
        destination: "Destination number or range to map to (e.g. '1', '1-12').",
    };

    type DescriptorState = { provider: string; entryId: string; scope: string };

    type DescriptorField = {
        field: keyof DescriptorState;
        placeholder: string;
        aria: string;
        info: string;
    };

    const descriptorInputs: DescriptorField[] = [
        {
            field: "provider",
            placeholder: "Provider",
            aria: "Descriptor provider",
            info: fieldInfo.provider,
        },
        {
            field: "entryId",
            placeholder: "ID",
            aria: "Descriptor entry id",
            info: fieldInfo.entryId,
        },
        {
            field: "scope",
            placeholder: "Scope",
            aria: "Descriptor scope",
            info: fieldInfo.scope,
        },
    ];

    const EMPTY_DESCRIPTOR: DescriptorState = { provider: "", entryId: "", scope: "" };

    type EntryFieldKey = "provider" | "entry_id" | "scope";
    type EntryPlaceholderKey =
        | "provider_placeholder"
        | "entry_id_placeholder"
        | "scope_placeholder";

    type EntryField = {
        key: EntryFieldKey;
        placeholder: EntryPlaceholderKey;
        aria: string;
        info: string;
        defaultLabel: string;
    };

    const entryFields: EntryField[] = [
        {
            key: "provider",
            placeholder: "provider_placeholder",
            aria: "Target provider",
            info: fieldInfo.provider,
            defaultLabel: "Provider",
        },
        {
            key: "entry_id",
            placeholder: "entry_id_placeholder",
            aria: "Target entry ID",
            info: fieldInfo.entryId,
            defaultLabel: "Entry ID",
        },
        {
            key: "scope",
            placeholder: "scope_placeholder",
            aria: "Target scope",
            info: fieldInfo.scope,
            defaultLabel: "Scope",
        },
    ];

    let descriptor = $state<DescriptorState>({ ...EMPTY_DESCRIPTOR });
    let entries = $state<EditableEntry[]>([]);
    let loadingDetail = $state(false);
    let saving = $state(false);
    let error = $state<string | null>(null);

    function descriptorFromState(): string {
        const provider = descriptor.provider.trim();
        const entryId = descriptor.entryId.trim();
        const scope = descriptor.scope.trim();
        if (!provider && !entryId && !scope) {
            return "";
        }
        return `${provider}:${entryId}:${scope}`;
    }

    function setDescriptorFields(provider: string, entryId: string, scope: string) {
        descriptor = { provider, entryId, scope };
    }

    function canLoadDescriptor(): boolean {
        const descriptor = descriptorFromState();
        return !!descriptor && DESCRIPTOR_RE.test(descriptor);
    }

    function toEditableEntries(data: MappingDetail): EditableEntry[] {
        return (data.targets || []).map((entry: MappingTarget) => {
            const isCustomEntry = entry.origin !== "upstream";
            return {
                key: entry.descriptor,
                provider: isCustomEntry ? entry.provider : "",
                entry_id: isCustomEntry ? entry.entry_id : "",
                scope: isCustomEntry ? entry.scope : "",
                provider_placeholder: entry.provider,
                entry_id_placeholder: entry.entry_id,
                scope_placeholder: entry.scope,
                origin: entry.origin,
                deleted: entry.deleted ?? false,
                original_descriptor: entry.descriptor,
                ranges: (entry.ranges || []).map((range) => ({
                    source_range: range.source_range,
                    upstream_value: range.upstream ?? null,
                    custom_value:
                        range.origin === "custom" ? (range.effective ?? null) : null,
                    mode: (range.origin === "custom" || !range.upstream
                        ? "custom"
                        : "inherited") as RangeMode,
                    original_source_range: range.source_range,
                })),
            };
        });
    }

    function hydrateDetail(data: MappingDetail) {
        entries = toEditableEntries(data);
        setDescriptorFields(data.provider, data.entry_id, data.scope);
    }

    function makeKey() {
        return `tmp-${Math.random().toString(36).slice(2)}`;
    }

    function addEntry() {
        entries = [
            ...entries,
            {
                key: makeKey(),
                provider: "",
                entry_id: "",
                scope: "",
                provider_placeholder: "",
                entry_id_placeholder: "",
                scope_placeholder: "",
                origin: "custom",
                deleted: false,
                original_descriptor: "",
                ranges: [
                    {
                        source_range: "",
                        upstream_value: null,
                        custom_value: null,
                        mode: "custom",
                        original_source_range: "",
                    },
                ],
            },
        ];
    }

    function removeEntry(key: string) {
        entries = entries
            .map((entry) => {
                if (entry.key !== key) return entry;
                // If this is a locally-created target, drop it entirely.
                if (entry.origin === "custom") {
                    return null;
                }
                return { ...entry, deleted: true, origin: "deleted" };
            })
            .filter((entry): entry is EditableEntry => entry !== null);
    }

    function updateEntry(
        key: string,
        updater: (entry: EditableEntry) => EditableEntry,
    ) {
        entries = entries.map((entry) => (entry.key === key ? updater(entry) : entry));
    }

    function addRange(key: string) {
        updateEntry(key, (entry) => ({
            ...entry,
            ranges: [
                ...entry.ranges,
                {
                    source_range: "",
                    upstream_value: null,
                    custom_value: null,
                    mode: "custom",
                    original_source_range: "",
                },
            ],
        }));
    }

    function removeRange(key: string, index: number) {
        updateEntry(key, (entry) => {
            const next = entry.ranges.filter((_, i) => i !== index);
            return { ...entry, ranges: next.length ? next : entry.ranges.slice(0, 1) };
        });
    }

    function setSourceRange(key: string, index: number, value: string) {
        updateEntry(key, (entry) => ({
            ...entry,
            ranges: entry.ranges.map((r, i) =>
                i === index ? { ...r, source_range: value, mode: "custom" } : r,
            ),
        }));
    }

    function setRangeValue(key: string, index: number, value: string) {
        updateEntry(key, (entry) => ({
            ...entry,
            ranges: entry.ranges.map((r, i) =>
                i === index
                    ? {
                          ...r,
                          mode: "custom",
                          custom_value: value === "" ? null : value,
                      }
                    : r,
            ),
        }));
    }

    function revertEntry(key: string) {
        updateEntry(key, (entry) => {
            const ranges = entry.ranges.map((r) => ({
                ...r,
                mode: (r.upstream_value ? "inherited" : "custom") as RangeMode,
                custom_value: null,
                original_source_range: r.source_range,
            }));
            return {
                ...entry,
                provider: "",
                entry_id: "",
                scope: "",
                deleted: false,
                origin: entry.origin === "deleted" ? "upstream" : entry.origin,
                original_descriptor: entry.original_descriptor,
                ranges,
            };
        });
    }

    function buildPayload(): MappingOverridePayload | null {
        const descriptor = descriptorFromState();
        if (!descriptor || !DESCRIPTOR_RE.test(descriptor)) {
            error = "Descriptor must be provider:entry:scope";
            return null;
        }

        const payloadTargets: TargetPayload[] = [];

        for (const entry of entries) {
            const provider = (
                entry.provider.trim() || entry.provider_placeholder
            ).trim();
            const entryId = (
                entry.entry_id.trim() || entry.entry_id_placeholder
            ).trim();
            const scope = (entry.scope.trim() || entry.scope_placeholder).trim();
            if (!provider || !entryId || !scope) continue;

            const originalProvider =
                entry.provider_placeholder.trim() || entry.provider.trim();
            const originalEntryId =
                entry.entry_id_placeholder.trim() || entry.entry_id.trim();
            const originalScope = entry.scope_placeholder.trim() || entry.scope.trim();
            const originalDescriptor =
                entry.original_descriptor ||
                (originalProvider && originalEntryId && originalScope
                    ? `${originalProvider}:${originalEntryId}:${originalScope}`
                    : "");
            const newDescriptor = `${provider}:${entryId}:${scope}`;
            const descriptorChanged =
                newDescriptor !== originalDescriptor && !!originalDescriptor;

            const removedSources: Record<string, boolean> = {};
            const ranges = [] as {
                source_range: string;
                destination_range: string | null;
            }[];

            if (entry.deleted) {
                payloadTargets.push({
                    provider: originalProvider || provider,
                    entry_id: originalEntryId || entryId,
                    scope: originalScope || scope,
                    ranges: [],
                    deleted: true,
                });
                continue;
            }

            for (const range of entry.ranges) {
                const source = range.source_range.trim();
                const destFromCustom = range.custom_value;
                const destFromUpstream = range.upstream_value;
                const destination_range =
                    descriptorChanged && destFromCustom == null
                        ? destFromUpstream
                        : destFromCustom;

                if ((descriptorChanged || range.mode !== "inherited") && source) {
                    ranges.push({ source_range: source, destination_range });
                }

                const original = range.original_source_range.trim();
                if (original && original !== source && !removedSources[original]) {
                    ranges.push({ source_range: original, destination_range: null });
                    removedSources[original] = true;
                }
            }

            if (descriptorChanged) {
                payloadTargets.push({
                    provider: originalProvider,
                    entry_id: originalEntryId,
                    scope: originalScope,
                    ranges: [],
                    deleted: true,
                });
            }

            if (ranges.length === 0) continue;
            payloadTargets.push({
                provider,
                entry_id: entryId,
                scope,
                ranges,
                deleted: false,
            });
        }

        return { descriptor, targets: payloadTargets };
    }

    async function loadDetail(explicit?: string) {
        const descriptor = explicit?.trim() || descriptorFromState();
        if (!descriptor) {
            error = "Descriptor is required";
            return;
        }
        loadingDetail = true;
        error = null;
        try {
            const res = await apiFetch(
                `/api/mappings/${encodeURIComponent(descriptor)}`,
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as MappingDetail;
            hydrateDetail(data);
            toast("Mapping loaded", "success");
        } catch (err) {
            console.error(err);
            error = "Failed to load mapping";
            entries = [];
        } finally {
            loadingDetail = false;
        }
    }

    async function handleSave() {
        const payload = buildPayload();
        if (!payload) return;
        saving = true;
        error = null;
        try {
            const method = mode === "edit" ? "PUT" : "POST";
            const url =
                mode === "edit"
                    ? `/api/mappings/${encodeURIComponent(payload.descriptor)}`
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
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as MappingDetail;
            hydrateDetail(data);
            onSaved?.(data);
            open = false;
        } catch (err) {
            console.error(err);
            error = "Failed to save override";
        } finally {
            saving = false;
        }
    }

    $effect(() => {
        if (!open) {
            descriptor = { ...EMPTY_DESCRIPTOR };
            entries = [];
            loadingDetail = false;
            saving = false;
            error = null;
            return;
        }

        const nextDescriptor = mode === "edit" ? (mapping?.descriptor ?? "") : "";
        descriptor =
            mode === "edit"
                ? {
                      provider: mapping?.provider ?? "",
                      entryId: mapping?.entry_id ?? "",
                      scope: mapping?.scope ?? "",
                  }
                : { ...EMPTY_DESCRIPTOR };
        entries = [];
        if (mode === "edit" && nextDescriptor) {
            loadDetail(nextDescriptor);
        }
    });
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

    <div class="space-y-4 p-4">
        <div
            class="rounded-md border border-slate-800/70 bg-slate-900/70 p-4 shadow-inner">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div class="flex-1 space-y-3">
                    <div class="grid gap-3 sm:grid-cols-3">
                        {#each descriptorInputs as field (field.field)}
                            <div class="relative w-full">
                                <input
                                    class="h-9 w-full rounded-md border border-slate-700/60 bg-slate-950 px-3 pr-10 text-[12px] text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
                                    placeholder={field.placeholder}
                                    aria-label={field.aria}
                                    bind:value={descriptor[field.field]}
                                    disabled={mode === "edit"} />
                                <div
                                    class="absolute inset-y-0 right-2 flex items-center">
                                    <Tooltip.Root delayDuration={120}>
                                        <Tooltip.Trigger>
                                            <button
                                                type="button"
                                                class="pointer-events-auto inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/70 text-slate-400 transition-colors hover:text-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500/40 focus-visible:outline-none"
                                                aria-label={`${field.placeholder} info`}>
                                                <Info class="h-3 w-3" />
                                            </button>
                                        </Tooltip.Trigger>
                                        <Tooltip.Portal>
                                            <Tooltip.Content
                                                side="top"
                                                sideOffset={6}
                                                class="z-50 rounded-md border border-slate-800/70 bg-slate-900/95 px-2 py-1.5 text-[11px] text-slate-100 shadow-xl">
                                                {field.info}
                                                <Tooltip.Arrow />
                                            </Tooltip.Content>
                                        </Tooltip.Portal>
                                    </Tooltip.Root>
                                </div>
                            </div>
                        {/each}
                    </div>
                </div>
                <div class="flex flex-wrap items-center gap-2 text-[11px]">
                    <button
                        type="button"
                        class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 bg-slate-800/60 px-3 py-2 text-xs font-semibold text-slate-100 shadow-sm transition-colors hover:border-emerald-500 hover:text-emerald-100 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none"
                        onclick={() => loadDetail()}
                        disabled={loadingDetail || !canLoadDescriptor()}>
                        <RefreshCcw class="inline h-3.5 w-3.5" />
                        Load existing
                    </button>
                    <button
                        type="button"
                        class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 bg-slate-800/60 px-3 py-2 text-xs font-semibold text-slate-100 shadow-sm transition-colors hover:border-emerald-500 hover:text-emerald-100 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none"
                        onclick={addEntry}
                        disabled={saving}>
                        <Plus class="inline h-3.5 w-3.5" />
                        Add Mapping
                    </button>
                </div>
            </div>
        </div>

        {#if entries.length === 0}
            <div
                class="rounded-md border border-dashed border-slate-800 bg-slate-950/70 p-6 text-center text-sm text-slate-400">
                Load an existing mapping or add a mapping to start.
            </div>
        {:else}
            <div class="space-y-4">
                {#each entries as entry (entry.key)}
                    <div
                        class={`rounded-md border p-4 shadow-md ${
                            entry.deleted && entry.origin !== "custom"
                                ? "border-rose-900/60 bg-slate-950/50 opacity-70"
                                : "border-slate-800 bg-slate-950/80"
                        }`}>
                        <div class="flex flex-wrap items-center gap-1.5">
                            <span
                                class={`font-mono text-xs ${
                                    entry.deleted && entry.origin !== "custom"
                                        ? "text-slate-500 line-through"
                                        : "text-slate-300"
                                }`}>
                                {entry.provider ||
                                    entry.provider_placeholder ||
                                    "?"}:{entry.entry_id ||
                                    entry.entry_id_placeholder ||
                                    "?"}:{entry.scope || entry.scope_placeholder || "?"}
                            </span>
                            <span
                                class={`rounded border px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${
                                    entry.origin === "custom"
                                        ? "border-emerald-800/60 bg-emerald-900/40 text-emerald-100"
                                        : entry.origin === "mixed"
                                          ? "border-amber-800/60 bg-amber-900/40 text-amber-100"
                                          : "border-slate-700/70 bg-slate-800/60 text-slate-100"
                                }`}>
                                {entry.origin === "custom"
                                    ? "Custom"
                                    : entry.origin === "mixed"
                                      ? "Mixed"
                                      : "Upstream"}
                            </span>
                            {#if entry.deleted && entry.origin !== "custom"}
                                <span
                                    class="rounded border border-rose-800/60 bg-rose-900/40 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-rose-100 uppercase">
                                    Disabled override
                                </span>
                            {/if}
                            <span class="flex-1"></span>
                            {#if entry.origin !== "custom"}
                                <button
                                    type="button"
                                    class="inline-flex items-center gap-1 rounded-md border border-slate-700/60 bg-slate-900/60 px-3 py-1 text-[12px] font-semibold text-slate-200 transition-colors hover:border-slate-500 focus:outline-none"
                                    onclick={() => revertEntry(entry.key)}>
                                    Revert to upstream
                                </button>
                            {/if}
                            <button
                                type="button"
                                class="inline-flex items-center rounded-md border border-slate-700/60 bg-slate-900/60 p-1 text-[12px] font-semibold text-emerald-200 shadow-sm transition-colors hover:border-emerald-400 hover:text-emerald-100 focus:outline-none"
                                title="Add range"
                                onclick={() => addRange(entry.key)}
                                disabled={entry.deleted}>
                                <Plus class="inline h-4 w-4" />
                            </button>
                            <button
                                type="button"
                                class="inline-flex items-center rounded-md border border-slate-700/60 bg-slate-900/60 p-1 text-[12px] font-semibold text-rose-200 transition-colors hover:border-rose-500 focus:outline-none"
                                title="Remove target mapping"
                                onclick={() => removeEntry(entry.key)}>
                                <Trash2 class="inline h-4 w-4" />
                            </button>
                        </div>

                        <div class="mt-3 grid gap-3 sm:grid-cols-3">
                            {#each entryFields as field (field.key)}
                                <div class="relative w-full">
                                    <input
                                        class="h-9 w-full rounded-md border border-slate-800/70 bg-slate-900 px-3 pr-10 text-[13px] text-slate-100 placeholder:text-slate-500 placeholder:opacity-70 focus:border-emerald-500 focus:outline-none"
                                        placeholder={entry[field.placeholder] ||
                                            field.defaultLabel}
                                        aria-label={field.aria}
                                        bind:value={entry[field.key]}
                                        disabled={entry.deleted} />
                                    <div
                                        class="absolute inset-y-0 right-2 flex items-center">
                                        <Tooltip.Root delayDuration={120}>
                                            <Tooltip.Trigger>
                                                <button
                                                    type="button"
                                                    class="pointer-events-auto inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/70 text-slate-400 transition-colors hover:text-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500/40 focus-visible:outline-none"
                                                    aria-label={`${field.defaultLabel} info`}>
                                                    <Info class="h-3 w-3" />
                                                </button>
                                            </Tooltip.Trigger>
                                            <Tooltip.Portal>
                                                <Tooltip.Content
                                                    side="top"
                                                    sideOffset={6}
                                                    class="z-50 rounded-md border border-slate-800/70 bg-slate-900/95 px-2 py-1.5 text-[11px] text-slate-100 shadow-xl">
                                                    {field.info}
                                                    <Tooltip.Arrow />
                                                </Tooltip.Content>
                                            </Tooltip.Portal>
                                        </Tooltip.Root>
                                    </div>
                                </div>
                            {/each}
                        </div>

                        <div class="mt-3 space-y-2 border-l border-slate-800/60 pl-4">
                            {#each entry.ranges as range, idx (idx)}
                                <div class="flex flex-wrap items-center gap-2">
                                    <div class="relative w-full min-w-44 flex-1">
                                        <input
                                            class="w-full min-w-0 rounded-md border border-slate-800/70 bg-slate-900 px-3 py-1 pr-10 text-[11px] text-slate-100 placeholder:text-slate-500 placeholder:opacity-80 focus:border-emerald-500 focus:outline-none"
                                            value={range.mode === "custom"
                                                ? range.source_range
                                                : ""}
                                            oninput={(ev) =>
                                                setSourceRange(
                                                    entry.key,
                                                    idx,
                                                    ev.currentTarget.value,
                                                )}
                                            placeholder={range.source_range ||
                                                "Source range"}
                                            aria-label="Range source"
                                            disabled={entry.deleted} />
                                        <div
                                            class="absolute inset-y-0 right-2 flex items-center">
                                            <Tooltip.Root delayDuration={120}>
                                                <Tooltip.Trigger>
                                                    <button
                                                        type="button"
                                                        class="pointer-events-auto inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/70 text-slate-400 transition-colors hover:text-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500/40 focus-visible:outline-none"
                                                        aria-label="Range source info">
                                                        <Info class="h-3 w-3" />
                                                    </button>
                                                </Tooltip.Trigger>
                                                <Tooltip.Portal>
                                                    <Tooltip.Content
                                                        side="top"
                                                        sideOffset={6}
                                                        class="z-50 rounded-md border border-slate-800/70 bg-slate-900/95 px-2 py-1 text-[11px] text-slate-100 shadow-xl">
                                                        {rangeFieldInfo.source}
                                                        <Tooltip.Arrow />
                                                    </Tooltip.Content>
                                                </Tooltip.Portal>
                                            </Tooltip.Root>
                                        </div>
                                    </div>
                                    <div class="relative w-full min-w-44 flex-1">
                                        <input
                                            class="w-full min-w-0 rounded-md border border-slate-800/70 bg-slate-900 px-3 py-1 pr-10 text-[11px] text-slate-100 placeholder:text-slate-500 placeholder:opacity-80 focus:border-emerald-500 focus:outline-none"
                                            value={range.mode === "custom"
                                                ? (range.custom_value ?? "")
                                                : ""}
                                            oninput={(ev) =>
                                                setRangeValue(
                                                    entry.key,
                                                    idx,
                                                    ev.currentTarget.value,
                                                )}
                                            placeholder={range.upstream_value ||
                                                "Destination range"}
                                            aria-label="Range destination"
                                            disabled={entry.deleted} />
                                        <div
                                            class="absolute inset-y-0 right-2 flex items-center">
                                            <Tooltip.Root delayDuration={120}>
                                                <Tooltip.Trigger>
                                                    <button
                                                        type="button"
                                                        class="pointer-events-auto inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/70 text-slate-400 transition-colors hover:text-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-500/40 focus-visible:outline-none"
                                                        aria-label="Range destination info">
                                                        <Info class="h-3 w-3" />
                                                    </button>
                                                </Tooltip.Trigger>
                                                <Tooltip.Portal>
                                                    <Tooltip.Content
                                                        side="top"
                                                        sideOffset={6}
                                                        class="z-50 rounded-md border border-slate-800/70 bg-slate-900/95 px-2 py-1.5 text-[11px] text-slate-100 shadow-xl">
                                                        {rangeFieldInfo.destination}
                                                        <Tooltip.Arrow />
                                                    </Tooltip.Content>
                                                </Tooltip.Portal>
                                            </Tooltip.Root>
                                        </div>
                                    </div>
                                    <div class="flex items-center gap-1.5">
                                        <button
                                            type="button"
                                            class="inline-flex items-center rounded-md border border-slate-700/60 bg-slate-900/60 p-1 text-[12px] font-semibold text-rose-200 transition-colors hover:border-rose-500 focus:outline-none"
                                            title="Remove range"
                                            onclick={() => removeRange(entry.key, idx)}
                                            disabled={entry.deleted}>
                                            <Trash2 class="inline h-4 w-4" />
                                        </button>
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>
                {/each}
            </div>
        {/if}

        {#if error}
            <div
                class="rounded-md border border-rose-800 bg-rose-900/40 p-3 text-[12px] text-rose-100">
                {error}
            </div>
        {/if}
        <div class="flex flex-wrap items-center gap-2">
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-3 py-2 text-[12px] font-semibold text-emerald-100 shadow-sm transition-colors hover:bg-emerald-600/40 focus:ring-2 focus:ring-emerald-500/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                onclick={handleSave}
                disabled={saving}>
                {#if saving}
                    <Save class="h-4 w-4 animate-spin" />
                {:else}
                    <Save class="h-4 w-4" />
                {/if}
                Save
            </button>
            <button
                type="button"
                class="inline-flex items-center gap-2 rounded-md border border-slate-700/60 bg-slate-800/60 px-3 py-2 text-[12px] font-semibold text-slate-100 shadow-sm transition-colors hover:border-slate-500 focus:ring-2 focus:ring-slate-500/40 focus:outline-none"
                onclick={() => loadDetail()}
                disabled={loadingDetail || !canLoadDescriptor()}>
                <RefreshCcw class="h-4 w-4" />
                Reload
            </button>
        </div>
    </div>
</Modal>
