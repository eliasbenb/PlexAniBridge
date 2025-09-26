<script lang="ts">
    import { onMount } from "svelte";

    import { Activity } from "@lucide/svelte";

    import { apiFetch } from "$lib/utils/api";
    import { toast } from "$lib/utils/notify";

    interface AboutInfo {
        version?: string;
        git_hash?: string;
        python?: string;
        platform?: string;
        started_at?: string | null;
        uptime?: string | null;
        utc_now?: string;
    }

    let info: AboutInfo = $state({});
    let status: unknown = $state(null);
    let loading = $state(true);
    let error: string | null = $state(null);

    async function load() {
        loading = true;
        error = null;
        try {
            const r = await apiFetch("/api/system/about");
            if (!r.ok) throw new Error("HTTP " + r.status);
            const d = await r.json();
            info = d.info || {};
            status = d.status;
        } catch (e: unknown) {
            if (e instanceof Error) error = e.message;
            else error = String(e);
            toast("Failed to load About info", "error");
        } finally {
            loading = false;
        }
    }

    onMount(load);
</script>

<div class="space-y-8">
    <div class="flex items-center gap-2">
        <Activity class="inline h-4 w-4 text-slate-300" />
        <h2 class="text-lg font-semibold">About</h2>
    </div>
    {#if error}<p class="text-sm text-rose-400">Failed: {error}</p>{/if}
    <p class="max-w-prose text-sm text-slate-300">
        PlexAniBridge synchronizes your Plex watch history, ratings, and reviews with
        your AniList profile. Below are runtime diagnostics and scheduler status.
    </p>
    <div class="grid gap-4 md:grid-cols-3">
        <div class="space-y-2 rounded-md border border-slate-800 bg-slate-900/50 p-4">
            <h3 class="text-sm font-medium tracking-wide text-slate-200">Runtime</h3>
            {#if loading}<p class="text-[11px] text-slate-500">Loading…</p>{/if}
            <ul class="space-y-1 text-[11px] text-slate-300" class:hidden={loading}>
                <li><span class="text-slate-500">Version:</span> {info.version}</li>
                <li><span class="text-slate-500">Git Hash:</span> {info.git_hash}</li>
                <li><span class="text-slate-500">Python:</span> {info.python}</li>
                <li class="break-all">
                    <span class="text-slate-500">Platform:</span>
                    {info.platform}
                </li>
                <li><span class="text-slate-500">Started:</span> {info.started_at}</li>
                <li><span class="text-slate-500">Uptime:</span> {info.uptime}</li>
                <li><span class="text-slate-500">UTC Now:</span> {info.utc_now}</li>
            </ul>
        </div>
        <div
            class="space-y-2 rounded-md border border-slate-800 bg-slate-900/50 p-4 md:col-span-2"
        >
            <h3 class="text-sm font-medium tracking-wide text-slate-200">
                Scheduler Status
            </h3>
            {#if loading}<p class="text-[11px] text-slate-500">Loading…</p>{/if}
            <pre
                class="max-h-72 overflow-auto rounded-md border border-slate-800 bg-slate-950/60 p-2 text-[11px]"
                class:hidden={loading}>{JSON.stringify(status, null, 2)}</pre>
        </div>
    </div>
</div>
