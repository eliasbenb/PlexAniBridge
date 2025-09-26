<script lang="ts">
    import { twMerge } from "tailwind-merge";

    interface Props {
        value?: object | null;
        class?: string;
    }

    let { value = null, class: className = "" }: Props = $props();

    export function highlightJson(obj: object) {
        if (!obj) return '<span class="text-slate-600">—</span>';
        const json = JSON.stringify(obj, null, 2);
        return json
            .replace(/(&|<)/g, (c) => (c === "&" ? "&amp;" : "&lt;"))
            .replace(
                /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g,
                (m) => {
                    if (/^".*":$/.test(m))
                        return `<span class='text-sky-300'>${m}</span>`;
                    if (/^"/.test(m))
                        return `<span class='text-emerald-300'>${m}</span>`;
                    if (/true|false/.test(m))
                        return `<span class='text-indigo-300'>${m}</span>`;
                    if (/null/.test(m))
                        return `<span class='text-pink-300'>${m}</span>`;
                    return `<span class='text-amber-300'>${m}</span>`;
                },
            )
            .trim();
    }
</script>

<div
    class={twMerge(
        "overflow-auto rounded border border-slate-800/60 bg-slate-900/60 p-2 font-mono text-[10px] leading-relaxed",
        className,
    )}
>
    <code class="whitespace-pre">
        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
        {@html highlightJson(value ?? {})}
    </code>
</div>
