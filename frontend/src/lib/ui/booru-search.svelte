<script lang="ts">
    import { onMount } from "svelte";

    import { ArrowRight, Search } from "@lucide/svelte";

    type Props = {
        value?: string;
        placeholder?: string;
        disabled?: boolean;
        autoFocus?: boolean;
        size?: "sm" | "md";
        onSubmit?: () => void;
    };
    let {
        value = $bindable(""),
        placeholder = "Search...",
        disabled = false,
        autoFocus = false,
        size = "sm",
        onSubmit,
    }: Props = $props();

    /**
     * @TODO better type hinting for keys (e.g. imdb doesn't take >, <, etc)
     */
    const KEYS = [
        {
            key: "anilist",
            alias: ["id"],
            desc: "AniList ID (int, supports >, <, ..)",
            type: "int",
        },
        { key: "anidb", desc: "AniDB ID (int)", type: "int" },
        { key: "imdb", desc: "IMDB ID (e.g., tt1234567)", type: "string" },
        { key: "mal", desc: "MyAnimeList ID (int)", type: "int" },
        { key: "tmdb_movie", desc: "TMDb Movie ID (int)", type: "int" },
        { key: "tmdb_show", desc: "TMDb TV ID (int)", type: "int" },
        { key: "tvdb", desc: "TheTVDB ID (int)", type: "int" },
        {
            key: "tvdb_mappings",
            desc: "TVDB mappings (season keys or values)",
            type: "string",
        },
        {
            key: "has",
            desc: "Presence filter: anidb/imdb/mal/tmdb_movie/tmdb_show/tvdb/tvdb_mappings",
            type: "enum",
        },
    ];

    // Internal state
    let inputEl: HTMLInputElement | null = null;
    let open = $state(false);
    let activeIndex = $state<number>(-1);
    let caret = $state(0);
    let suggestions = $derived(getSuggestions(value, caret));

    type Suggestion = {
        label: string;
        detail?: string;
        kind: "key" | "value" | "op" | "helper";
        apply: (ctx: ApplyCtx) => void;
    };

    type ApplyCtx = {
        value: string;
        caret: number;
        // Replace a range [start, end) with text and optionally place caret
        replace: (
            start: number,
            end: number,
            text: string,
            caretDelta?: number,
        ) => void;
        // Insert text at caret
        insert: (text: string) => void;
        // Set new caret
        setCaret: (pos: number) => void;
    };

    function isBoundary(ch: string) {
        return /\s|\||\(|\)/.test(ch);
    }

    function findSegment(value: string, caret: number) {
        const end = caret;
        let start = end;
        while (start > 0 && !isBoundary(value[start - 1])) start--;
        // include leading ~ or - if directly adjacent
        if (start > 0 && (value[start - 1] === "-" || value[start - 1] === "~")) {
            // but only include if there's boundary before that or it's at index 0
            if (start - 1 === 0 || isBoundary(value[start - 2] || " ")) {
                start -= 1;
            }
        }
        const text = value.slice(start, end);
        return { start, end, text };
    }

    function getKeyInfo(name: string | undefined) {
        if (!name) return undefined;
        const lname = name.toLowerCase();
        for (const k of KEYS) {
            if (k.key === lname || (k.alias && k.alias.includes(lname))) return k;
        }
        return undefined;
    }

    function getSuggestions(val: string, caret: number): Suggestion[] {
        const seg = findSegment(val, caret);
        const t = seg.text;

        const out: Suggestion[] = [];

        // If segment looks like key:value (possibly partial value)
        const mKV = t.match(/^([-~]?)([a-zA-Z_][\w]*)?(:)?([^\s]*)$/);
        if (mKV) {
            const prefix = mKV[1] || ""; // ~ or -
            const name = (mKV[2] || "").toLowerCase();
            const hasColon = !!mKV[3];
            const vpart = mKV[4] || "";
            const kinfo = getKeyInfo(name);

            // Key suggestions (when typing name or missing colon)
            if (!hasColon) {
                const needle = name;
                for (const k of KEYS) {
                    if (needle && !k.key.startsWith(needle)) continue;
                    out.push({
                        label: `${prefix}${k.key}:`,
                        detail: k.desc,
                        kind: "key",
                        apply: ({ replace }) => {
                            replace(seg.start, seg.end, `${prefix}${k.key}:`);
                        },
                    });
                }

                if (!needle && prefix === "" && t.trim() === t) {
                    out.push({
                        label: '"title"',
                        detail: "AniList search by title",
                        kind: "helper",
                        apply: ({ replace }) => {
                            replace(seg.start, seg.end, '""');
                        },
                    });
                }
            } else {
                // Value suggestions depending on key type
                if (kinfo?.key === "has") {
                    const opts = [
                        "anidb",
                        "imdb",
                        "mal",
                        "tmdb_movie",
                        "tmdb_show",
                        "tvdb",
                        "tvdb_mappings",
                    ];
                    for (const opt of opts) {
                        if (vpart && !opt.startsWith(vpart.toLowerCase())) continue;
                        out.push({
                            label: `${prefix}${kinfo.key}:${opt}`,
                            detail: "Has field",
                            kind: "value",
                            apply: ({ replace }) => {
                                replace(
                                    seg.start,
                                    seg.end,
                                    `${prefix}${kinfo.key}:${opt}`,
                                );
                            },
                        });
                    }
                } else if (kinfo?.type === "bool") {
                    ["true", "false"].forEach((v) =>
                        out.push({
                            label: `${prefix}${kinfo.key}:${v}`,
                            detail: "Boolean",
                            kind: "value",
                            apply: ({ replace }) => {
                                replace(
                                    seg.start,
                                    seg.end,
                                    `${prefix}${kinfo.key}:${v}`,
                                );
                            },
                        }),
                    );
                } else if (kinfo) {
                    // Numeric/string operators
                    const base = `${prefix}${kinfo.key}:`;
                    const ops: Array<[string, string]> = [
                        [">=", "Greater or equal"],
                        ["<=", "Less or equal"],
                        [">", "Greater than"],
                        ["<", "Less than"],
                        ["..", "Range (lo..hi)"],
                    ];

                    // If the user started typing an operator, filter to those
                    const filteredOps = vpart
                        ? ops.filter(([op]) => op.startsWith(vpart))
                        : ops;
                    for (const [op, detail] of filteredOps) {
                        out.push({
                            label: base + op,
                            detail,
                            kind: "value",
                            apply: ({ replace }) => {
                                const rest = vpart;
                                let next = base + op;

                                if (op === ".." && /\d$/.test(rest)) {
                                    next = base + rest + "..";
                                }
                                replace(seg.start, seg.end, next);
                            },
                        });
                    }
                }
            }
        }

        if (!t || /^\s*$/.test(t)) {
            [
                { sym: "|", desc: "OR between terms" },
                { sym: "~", desc: "Mark term for OR in group" },
                { sym: "-", desc: "NOT (negate next term)" },
                { sym: "(", desc: "Start group" },
                { sym: ")", desc: "End group" },
                { sym: '""', desc: "Bare title search" },
            ].forEach(({ sym, desc }) =>
                out.push({
                    label: sym,
                    detail: desc,
                    kind: "op",
                    apply: ({ insert }) => insert(sym),
                }),
            );
        }

        if (out.length < 6 && val.trim() === "") {
            for (const k of KEYS) {
                if (out.length >= 6) break;
                out.push({
                    label: `${k.key}:`,
                    detail: k.desc,
                    kind: "key",
                    apply: ({ insert }) => insert(`${k.key}:`),
                });
            }
        }

        // De-duplicate by label
        const seen: Record<string, true> = {};
        const uniq: Suggestion[] = [];
        for (const s of out) {
            if (seen[s.label]) continue;
            seen[s.label] = true;
            uniq.push(s);
        }
        return uniq.slice(0, 12);
    }

    function applySuggestion(idx: number) {
        if (idx < 0 || idx >= suggestions.length) return;
        const applyCtx: ApplyCtx = {
            value,
            caret,
            replace(start, end, text, caretDelta = 0) {
                const left = value.slice(0, start);
                const right = value.slice(end);
                value = left + text + right;
                const nextCaret = start + text.length + caretDelta;
                caret = nextCaret;
                queueMicrotask(() => setSelection(nextCaret));
            },
            insert(text) {
                const left = value.slice(0, caret);
                const right = value.slice(caret);
                value = left + text + right;
                const nextCaret = caret + text.length;
                caret = nextCaret;
                queueMicrotask(() => setSelection(nextCaret));
            },
            setCaret(pos) {
                caret = pos;
                queueMicrotask(() => setSelection(pos));
            },
        };
        suggestions[idx].apply(applyCtx);
        open = true;
        activeIndex = -1;
    }

    function setSelection(pos: number) {
        if (!inputEl) return;
        inputEl.selectionStart = inputEl.selectionEnd = pos;
        inputEl.focus();
    }

    function handleKeydown(e: KeyboardEvent) {
        if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
            open = true;
        }
        if (open && suggestions.length) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                activeIndex = (activeIndex + 1) % suggestions.length;
                return;
            }
            if (e.key === "ArrowUp") {
                e.preventDefault();
                activeIndex =
                    (activeIndex - 1 + suggestions.length) % suggestions.length;
                return;
            }
            if (e.key === "Enter" || e.key === "Tab") {
                if (activeIndex >= 0) {
                    e.preventDefault();
                    applySuggestion(activeIndex);
                    return;
                }
            }
            if (e.key === "Escape") {
                open = false;
                activeIndex = -1;
                return;
            }
        }
        if (e.key === "Enter") {
            if (activeIndex < 0) {
                e.preventDefault();
                open = false;
                activeIndex = -1;
                onSubmit?.();
            }
        }
    }

    function onInput(ev: Event) {
        const t = ev.target as HTMLInputElement;
        value = t.value;
        caret = t.selectionStart ?? value.length;
        open = true;
        activeIndex = -1;
    }

    function onFocus() {
        open = true;
        caret = inputEl?.selectionStart ?? 0;
    }

    function onBlur() {
        setTimeout(() => {
            open = false;
            activeIndex = -1;
        }, 120);
    }

    onMount(() => {
        if (autoFocus) inputEl?.focus();
    });
</script>

<div class="relative" data-component="booru-search">
    <input
        bind:this={inputEl}
        {placeholder}
        {disabled}
        {value}
        oninput={onInput}
        onkeydown={handleKeydown}
        onfocus={onFocus}
        onblur={onBlur}
        aria-label="Search mappings"
        class={`${size === "sm" ? "h-8 pr-9 pl-8" : "h-9 pr-10 pl-9"} w-full rounded-md border border-slate-700/70 bg-slate-900/70 text-[11px] shadow-sm placeholder:text-slate-500 focus:border-slate-600 focus:bg-slate-900`}
    />
    <Search
        class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
    />
    <button
        class="absolute top-1/2 right-1 inline-flex items-center justify-center rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700 {size ===
        'sm'
            ? 'h-6 w-6 -translate-y-1/2'
            : 'h-7 w-7 -translate-y-1/2'}"
        aria-label="Run search"
        onclick={() => {
            open = false;
            activeIndex = -1;
            onSubmit?.();
        }}
        {disabled}
    >
        <ArrowRight class={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
    </button>

    {#if open && suggestions.length}
        <div
            class="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-slate-800/70 bg-slate-900/95 shadow-xl backdrop-blur supports-[backdrop-filter]:bg-slate-900/75"
        >
            <ul class="max-h-64 overflow-auto py-1 text-[11px]">
                {#each suggestions as s, i (s.label)}
                    <li>
                        <button
                            class={`group flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-slate-800/70 ${i === activeIndex ? "bg-slate-800/70" : ""}`}
                            onmousedown={(e) => {
                                e.preventDefault();
                                applySuggestion(i);
                            }}
                        >
                            <span class="font-mono text-slate-200">{s.label}</span>
                            {#if s.detail}
                                <span class="ml-2 shrink-0 text-[10px] text-slate-400"
                                    >{s.detail}</span
                                >
                            {/if}
                        </button>
                    </li>
                {/each}
            </ul>
            <div
                class="border-t border-slate-800/70 px-2 py-1 text-[10px] text-slate-400"
            >
                Tips: Use '~' to OR within a group, '|' for OR between groups, '-' to
                negate, quotes for AniList title, and '()' to group terms.
            </div>
        </div>
    {/if}
</div>

<style>
    [data-component="booru-search"] .font-mono {
        font-feature-settings:
            "tnum" 1,
            "ss01" 1;
    }
</style>
