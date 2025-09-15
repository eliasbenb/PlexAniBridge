<script lang="ts">
    import { onMount } from "svelte";

    import { ArchiveRestore, Folder, LoaderCircle } from "@lucide/svelte";

    import { resolve } from "$app/paths";
    import { apiJson } from "$lib/api";

    interface StatusResponse {
        profiles: Record<string, unknown>;
    }

    let profiles: string[] = $state([]);
    let loading = $state(true);

    async function load() {
        loading = true;
        try {
            const data = await apiJson<StatusResponse>("/api/status");
            profiles = Object.keys(data.profiles || {}).sort();
        } catch (e) {
            console.error(e);
        } finally {
            loading = false;
        }
    }

    onMount(load);
</script>

<div class="space-y-6">
    <div class="space-y-1">
        <div class="flex items-center gap-2">
            <ArchiveRestore class="inline h-4 w-4 text-slate-300" />
            <h2 class="text-lg font-semibold">Backups</h2>
            <span class="hidden text-xs text-slate-500 sm:inline"
                >{Object.keys(profiles).length} profiles
                <div class="ml-auto"></div>
            </span>
        </div>
        <p class="text-xs text-slate-400">Restore from backups for each profile.</p>
    </div>
    {#if loading}
        <div class="flex items-center gap-2 text-sm text-sky-300">
            <LoaderCircle class="inline h-5 w-5 animate-spin" /> Loading…
        </div>
    {:else if !profiles.length}
        <p class="text-sm text-slate-500">No profiles loaded.</p>
    {:else}
        <ul class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {#each profiles as p (p)}
                <li>
                    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
                    <a
                        href={resolve(`/backups/${p}`)}
                        class="group block overflow-hidden rounded-md border border-slate-800 bg-gradient-to-br from-slate-900/70 to-slate-800/40 p-4 shadow-sm backdrop-blur-sm transition hover:border-slate-700 hover:from-slate-800/70 hover:to-slate-700/40 hover:shadow-md"
                    >
                        <div class="flex items-center gap-2">
                            <Folder
                                class="inline h-5 w-5 text-sky-400 transition-colors group-hover:text-sky-300"
                            />
                            <span class="truncate font-medium">{p}</span>
                        </div>
                        <p class="mt-2 text-[11px] text-slate-500">
                            View backups for profile.
                        </p>
                    </a>
                </li>
            {/each}
        </ul>
    {/if}
</div>
