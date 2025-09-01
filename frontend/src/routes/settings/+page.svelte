<script lang="ts">
    import { onMount } from "svelte";

    import { Languages, Settings, User } from "@lucide/svelte";

    interface SettingsResp {
        global_config: Record<string, any>;
        profiles: { name: string; settings: Record<string, any> }[];
    }

    let data: SettingsResp = $state({ global_config: {}, profiles: [] });
    let loading = $state(true);
    let error: string | null = $state(null);
    let titleLang = $state("romaji");

    function loadPref() {
        try {
            titleLang = localStorage.getItem("anilist.lang") || "romaji";
        } catch {}
    }

    function setLang(v: string) {
        titleLang = v;
        try {
            localStorage.setItem("anilist.lang", v);
            dispatchEvent(
                new CustomEvent("anilist-lang-changed", { detail: { lang: v } }),
            );
        } catch {}
    }

    async function load() {
        loading = true;
        error = null;
        try {
            const r = await fetch("/api/system/settings");
            if (!r.ok) throw new Error("HTTP " + r.status);
            data = await r.json();
        } catch (e: any) {
            error = e?.message || String(e);
        } finally {
            loading = false;
        }
    }

    onMount(() => {
        loadPref();
        load();
    });
</script>

<div class="space-y-8">
    <div class="flex items-center gap-2">
        <Settings class="inline h-4 w-4 text-slate-300" />
        <h2 class="text-lg font-semibold">Settings</h2>
    </div>
    <p class="max-w-prose text-xs text-slate-400">
        Read-only view of the currently loaded configuration. To change settings, edit
        your environment variables or configuration file and restart the application.
    </p>
    {#if error}<p class="text-sm text-rose-400">Failed: {error}</p>{/if}
    <div class="grid gap-6 md:grid-cols-3">
        <div class="space-y-8 md:col-span-1">
            <div class="space-y-2">
                <h4 class="text-sm font-medium tracking-wide text-slate-200">Global</h4>
                {#if loading}<p class="text-[11px] text-slate-500">Loading…</p>{/if}
                <ul
                    class="space-y-1 rounded-md border border-slate-800 bg-slate-900/50 p-4 text-[11px]"
                    class:hidden={loading}
                >
                    {#each Object.entries(data.global_config) as [k, v] (k)}
                        <li class="flex gap-2">
                            <span class="min-w-40 break-all text-slate-500">{k}</span>
                            <span class="break-all text-slate-300">
                                {#if v == null}
                                    <span class="italic text-slate-600">(unset)</span>
                                {:else if typeof v === "string"}
                                    {v}
                                {:else}
                                    {JSON.stringify(v)}
                                {/if}
                            </span>
                        </li>
                    {/each}
                    {#if !Object.keys(data.global_config).length && !loading}<li
                            class="text-slate-500"
                        >
                            Empty
                        </li>{/if}
                </ul>
            </div>
            <div class="space-y-2">
                <h4
                    class="flex items-center gap-2 text-sm font-medium tracking-wide text-slate-200"
                >
                    <Languages class="inline h-4 w-4 text-slate-400" /><span
                        >AniList Title Language</span
                    >
                </h4>
                <p class="text-[11px] leading-relaxed text-slate-500">
                    Choose which title language to prefer (Romaji, English, or Native).
                    Stored only in this browser.
                </p>
                <div class="flex gap-2">
                    {#each ["romaji", "english", "native"] as opt (opt)}
                        <button
                            type="button"
                            onclick={() => setLang(opt)}
                            class={`rounded-md border px-3 py-1.5 text-[11px] font-medium ${titleLang === opt ? "border-blue-500 bg-blue-600 text-white" : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-700/60"}`}
                            >{opt[0].toUpperCase() + opt.slice(1)}</button
                        >
                    {/each}
                </div>
                <p class="text-[10px] text-slate-500">
                    Current preference: <span class="font-medium text-slate-300"
                        >{titleLang}</span
                    >
                </p>
            </div>
        </div>
        <div class="space-y-4 md:col-span-2">
            <div class="flex items-center gap-2">
                <h3 class="text-sm font-medium tracking-wide text-slate-200">
                    Profiles
                </h3>
                <span class="text-[11px] text-slate-500">({data.profiles.length})</span>
            </div>
            {#if loading}<p class="text-[11px] text-slate-500">Loading…</p>{/if}
            <div class="space-y-6" class:hidden={loading}>
                {#each data.profiles as p (p.name)}
                    <div class="rounded-md border border-slate-800 bg-slate-900/50">
                        <div
                            class="flex items-center gap-2 border-b border-slate-800 px-4 py-2"
                        >
                            <User class="inline h-4 w-4 text-slate-400" />
                            <span class="font-medium text-slate-200">{p.name}</span>
                        </div>
                        <div class="p-4">
                            <ul class="space-y-1 text-[11px]">
                                {#each Object.entries(p.settings) as [k, v] (`${p.name}-${k}`)}
                                    <li class="flex gap-2">
                                        <span class="min-w-40 break-all text-slate-500"
                                            >{k}</span
                                        >
                                        <span class="break-all text-slate-300">
                                            {#if v == null}
                                                <span class="italic text-slate-600"
                                                    >(unset)</span
                                                >
                                            {:else if typeof v === "string"}
                                                {v}
                                            {:else}
                                                {JSON.stringify(v)}
                                            {/if}
                                        </span>
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    </div>
                {/each}
                {#if !data.profiles.length && !loading}<p
                        class="text-xs text-slate-500"
                    >
                        No profiles loaded.
                    </p>{/if}
            </div>
        </div>
    </div>
</div>
