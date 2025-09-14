<script lang="ts">
    import { onDestroy } from "svelte";

    import { X } from "@lucide/svelte";

    import { dismiss, toasts, type Toast } from "$lib/notify";

    let list: Toast[] = $state([]);
    const unsub = toasts.subscribe((v) => (list = v));

    onDestroy(() => unsub());

    const COLORS: Record<string, string> = {
        info: "border-sky-600/60 bg-sky-900/70 text-sky-100",
        success: "border-emerald-600/60 bg-emerald-900/70 text-emerald-100",
        error: "border-red-600/60 bg-red-900/70 text-red-100",
        warn: "border-amber-600/60 bg-amber-900/70 text-amber-100",
    };
</script>

<div
    class="pointer-events-none fixed top-16 right-4 z-[60] flex w-80 max-w-[90vw] flex-col gap-2"
    aria-live="assertive"
    aria-relevant="additions removals"
>
    {#each list as t (t.id)}
        <div
            class={`group relative flex overflow-hidden rounded-md border p-3 pr-8 text-sm shadow-lg shadow-slate-950/50 backdrop-blur ${COLORS[t.type]}`}
            role="alert"
        >
            <span class="block leading-snug">{t.message}</span>
            <button
                type="button"
                title="Dismiss"
                class="pointer-events-auto absolute top-1.5 right-1.5 inline-flex h-6 w-6 items-center justify-center rounded-md bg-slate-950/30 text-[11px] text-slate-400 hover:bg-slate-950/50 hover:text-slate-200"
                onclick={() => dismiss(t.id)}
            >
                <X class="inline h-3.5 w-3.5" />
            </button>
            <div
                class="pointer-events-none absolute bottom-0 left-0 h-0.5 w-full bg-slate-950/20"
            >
                <div
                    class="h-full bg-white/30"
                    style={`animation: shrink ${t.timeout}ms linear forwards`}
                ></div>
            </div>
        </div>
    {/each}
</div>

<style>
    @keyframes shrink {
        from {
            width: 100%;
        }
        to {
            width: 0%;
        }
    }
</style>
