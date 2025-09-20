<script lang="ts">
    import { onMount } from "svelte";

    import { ArchiveRestore, Eye, LoaderCircle, RefreshCcw } from "@lucide/svelte";

    import { apiJson } from "$lib/api";
    import { toast } from "$lib/notify";
    import JsonCodeBlock from "$lib/ui/json-code-block.svelte";
    import Modal from "$lib/ui/modal.svelte";

    const { params } = $props<{ params: { profile: string } }>();

    let backups: BackupMeta[] = $state([]);
    let loading = $state(true);
    let restoring = $state<string | null>(null);
    let previewing = $state<string | null>(null);
    interface BackupRawPreview {
        user?: unknown;
        lists?: unknown;
        [k: string]: unknown; // flexible structure
    }
    let previewCache = $state<Record<string, BackupRawPreview>>({});
    let previewLoading = $state(false);

    async function load() {
        loading = true;
        try {
            backups = await listBackups(params.profile);
        } catch (e) {
            console.error(e);
        } finally {
            loading = false;
        }
    }

    interface BackupMeta {
        filename: string;
        created_at: string;
        size_bytes: number;
        entries?: number | null;
        user?: string | null;
        age_seconds: number;
    }

    interface RestoreSummary {
        ok: boolean;
        filename: string;
        total_entries: number;
        processed: number;
        restored: number;
        skipped: number;
        errors: { [k: string]: unknown }[];
        elapsed_seconds: number;
    }

    async function listBackups(profile: string): Promise<BackupMeta[]> {
        const data = await apiJson<{ backups: BackupMeta[] }>(
            `/api/backups/${profile}`,
        );
        return data.backups || [];
    }

    async function restoreBackup(
        profile: string,
        filename: string,
    ): Promise<RestoreSummary> {
        return await apiJson<RestoreSummary>(`/api/backups/${profile}/restore`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename }),
        });
    }

    async function openPreview(filename: string) {
        if (previewing === filename) return;
        if (!previewCache[filename]) {
            previewLoading = true;
            try {
                const data = await apiJson<BackupRawPreview>(
                    `/api/backups/${params.profile}/raw/${filename}`,
                );
                previewCache[filename] = data;
            } catch (e) {
                console.error(e);
                toast("Failed to load preview", "error");
                previewLoading = false;
                return;
            }
            previewLoading = false;
        }
        previewing = filename;
    }

    function getPreviewOpen() {
        return previewing !== null;
    }
    function setPreviewOpen(open: boolean) {
        if (!open) previewing = null;
    }

    function humanBytes(n: number) {
        if (n < 1024) return n + " B";
        const units = ["KB", "MB", "GB"];
        let u = -1;
        let v = n;
        do {
            v /= 1024;
            u++;
        } while (v >= 1024 && u < units.length - 1);
        return v.toFixed(v >= 10 ? 0 : 1) + " " + units[u];
    }

    function ageLabel(sec: number) {
        if (sec < 90) return Math.round(sec) + "s ago";
        if (sec < 3600) return Math.round(sec / 60) + "m ago";
        if (sec < 86400) return Math.round(sec / 3600) + "h ago";
        return Math.round(sec / 86400) + "d ago";
    }

    async function doRestore(filename: string) {
        if (
            !confirm(
                `Restore '${filename}'? This overwrites current AniList list entries.`,
            )
        )
            return;
        restoring = filename;
        try {
            const res = await restoreBackup(params.profile, filename);
            toast(
                `Restore complete: ${res.restored}/${res.total_entries}`,
                res.errors.length ? "warn" : "success",
            );
        } catch (e) {
            console.error(e);
            toast("Restore failed", "error");
        } finally {
            restoring = null;
        }
    }

    onMount(load);
</script>

<div class="space-y-6">
    <div class="flex flex-wrap items-center gap-2">
        <ArchiveRestore class="inline h-4 w-4 text-slate-300" />
        <h2 class="text-lg font-semibold">Backups</h2>
        <span class="text-xs text-slate-500">profile: <i>{params.profile}</i></span>
        <div class="ml-auto flex items-center gap-2 text-[11px]">
            <button
                onclick={load}
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-slate-600/60 bg-slate-700/40 px-2 py-1 font-medium text-slate-200 hover:bg-slate-600/50"
            >
                <RefreshCcw class="inline h-4 w-4 text-[14px]" /> Refresh
            </button>
        </div>
    </div>

    {#if loading}
        <div class="flex items-center gap-2 text-sm text-sky-300">
            <LoaderCircle class="inline h-5 w-5 animate-spin" /> Loading backups…
        </div>
    {:else if !backups.length}
        <p class="text-sm text-slate-500">No backups found.</p>
    {:else}
        <div
            class="overflow-x-auto rounded-md border border-slate-800 bg-slate-900/60 shadow-sm backdrop-blur-sm"
        >
            <table class="w-full text-sm">
                <thead
                    class="bg-slate-800/60 text-left text-[11px] tracking-wide text-slate-400 uppercase"
                >
                    <tr>
                        <th class="px-3 py-2 font-medium">Filename</th>
                        <th class="px-3 py-2 font-medium">Created</th>
                        <th class="px-3 py-2 font-medium">Age</th>
                        <th class="px-3 py-2 font-medium">Size</th>
                        <th class="px-3 py-2 font-medium">User</th>
                        <th class="px-3 py-2 text-right font-medium">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                    {#each backups as b (b.filename)}
                        <tr class="transition hover:bg-slate-800/50">
                            <td class="px-3 py-2 font-mono text-[11px] break-all"
                                >{b.filename}</td
                            >
                            <td class="px-3 py-2"
                                >{new Date(b.created_at).toLocaleString()}</td
                            >
                            <td class="px-3 py-2 text-slate-400"
                                >{ageLabel(b.age_seconds)}</td
                            >
                            <td class="px-3 py-2 text-slate-400"
                                >{humanBytes(b.size_bytes)}</td
                            >
                            <td class="px-3 py-2 text-slate-400">{b.user || "—"}</td>
                            <td class="px-3 py-2">
                                <div class="flex justify-end gap-2">
                                    <button
                                        class="inline-flex items-center gap-1 rounded-md border border-sky-600/60 bg-sky-600/30 px-2 py-1 text-[11px] font-medium text-sky-100 hover:bg-sky-600/40 disabled:opacity-50"
                                        disabled={previewLoading &&
                                            !previewCache[b.filename]}
                                        onclick={() => openPreview(b.filename)}
                                        title="Preview raw JSON"
                                    >
                                        {#if previewLoading && !previewCache[b.filename]}
                                            <LoaderCircle
                                                class="inline h-4 w-4 animate-spin"
                                            />
                                        {:else}
                                            <Eye class="inline h-4 w-4" />
                                        {/if}
                                        <span>Preview</span>
                                    </button>
                                    <button
                                        class="inline-flex items-center gap-1 rounded-md border border-emerald-600/60 bg-emerald-600/30 px-2 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-600/40 disabled:opacity-50"
                                        disabled={restoring === b.filename}
                                        onclick={() => doRestore(b.filename)}
                                        title="Restore backup"
                                    >
                                        {#if restoring === b.filename}
                                            <LoaderCircle
                                                class="inline h-4 w-4 animate-spin"
                                            />
                                        {:else}
                                            <ArchiveRestore class="inline h-4 w-4" />
                                        {/if}
                                        <span>Restore</span>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>
    {/if}

    {#if previewing}
        <Modal
            bind:open={getPreviewOpen, setPreviewOpen}
            contentClass="fixed top-1/2 left-1/2 z-50 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-md border border-slate-800 bg-slate-950/80 shadow-xl backdrop-blur-md"
            headerWrapperClass="border-b border-slate-800/80 bg-slate-900/60 px-4 py-2"
            footerClass="flex items-center justify-end gap-2 border-t border-slate-800/70 bg-slate-900/60 px-4 py-2"
            closeButtonClass="rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-800/70 hover:text-slate-200"
            onOpenAutoFocus={(e: Event) => e.preventDefault()}
            onCloseAutoFocus={() => (previewing = null)}
        >
            <svelte:fragment slot="title">
                <div class="text-sm font-semibold tracking-wide text-slate-200">
                    Backup Preview
                    <span class="ml-1 font-mono text-[10px] text-slate-400"
                        >{previewing}</span
                    >
                </div>
            </svelte:fragment>

            <div class="p-4">
                <JsonCodeBlock
                    value={previewCache[previewing] || {}}
                    className="text-[11px] leading-snug"
                    maxHeight="max-h-[70vh]"
                />
            </div>
            <div slot="footer">
                <button
                    class="rounded-md border border-slate-600/60 bg-slate-700/40 px-3 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-600/50"
                    onclick={() => setPreviewOpen(false)}
                >
                    Close
                </button>
            </div>
        </Modal>
    {/if}
</div>
