<script lang="ts">
    import { onMount } from "svelte";

    import { ArrowRight, Search } from "@lucide/svelte";
    import { Popover } from "bits-ui";

    import { apiJson } from "$lib/utils/api";

    interface Props {
        value?: string;
        autoFocus?: boolean;
        disabled?: boolean;
        placeholder?: string;
        size?: "sm" | "md";
        onSubmit?: () => void;
    }

    let {
        value = $bindable(""),
        autoFocus = false,
        disabled = false,
        placeholder = "Search...",
        size = "sm",
        onSubmit,
    }: Props = $props();

    type FieldCapability = {
        key: string;
        aliases?: string[];
        type: "int" | "string" | "enum" | string;
        operators: string[]; // "=", ">", ">=", "<", "<=", "*", "?", "range"
        values?: string[] | null;
        desc?: string | null;
    };

    type CapabilitiesResponse = { fields: FieldCapability[] };

    let capabilities = $state<FieldCapability[] | null>(null);
    let KEYS: FieldCapability[] = $derived(capabilities ?? []);

    let inputEl = $state<HTMLInputElement | null>(null);
    let containerEl = $state<HTMLDivElement | null>(null);
    let open = $state(false);
    let activeIndex = $state<number>(-1);
    let caret = $state(0);
    let suggestions = $derived(getSuggestions(value, caret));
    let focused = $state(false);
    const isActive = $derived(focused || open || value.trim().length > 0);
    let pointerInPopover = $state(false);
    const listId = `booru-suggestions-${Math.random().toString(36).slice(2, 8)}`;

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
            const aliases = k.aliases ?? [];
            if (k.key === lname || (Array.isArray(aliases) && aliases.includes(lname)))
                return k;
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

                for (const k of KEYS) {
                    if (needle && !k.key.startsWith(needle)) continue;
                    out.push({
                        label: `${prefix}${k.key}:`,
                        detail: k.desc ?? undefined,
                        kind: "key",
                        apply: ({ replace }) => {
                            replace(seg.start, seg.end, `${prefix}${k.key}:`);
                        },
                    });
                }
            } else {
                // Value suggestions depending on key type
                if (kinfo?.key === "has") {
                    const opts = kinfo.values || [];
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
                    // Operators based on backend capabilities
                    const base = `${prefix}${kinfo.key}:`;
                    const capOps: string[] = Array.isArray(kinfo.operators)
                        ? kinfo.operators
                        : [];
                    const opMap: Record<string, string> = {
                        "=": "Equals",
                        ">": "Greater than",
                        ">=": "Greater or equal",
                        "<": "Less than",
                        "<=": "Less or equal",
                        "*": "Wildcard (*)",
                        "?": "Wildcard (?)",
                        range: "Range (lo..hi)",
                    };

                    // Transform to UI suffixes
                    const allOps: Array<[string, string]> = capOps.map((op) => [
                        op === "=" ? "" : op === "range" ? ".." : op,
                        op === "wildcard" ? "*" : opMap[op] || "",
                    ]);

                    const filteredOps = vpart
                        ? allOps.filter(([op]) => op.startsWith(vpart))
                        : allOps;
                    for (const [op, detail] of filteredOps) {
                        out.push({
                            label: base + op,
                            detail: detail || undefined,
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

        if (out.length < 6 && val.trim() === "") {
            for (const k of KEYS) {
                if (out.length >= 6) break;
                out.push({
                    label: `${k.key}:`,
                    detail: k.desc ?? undefined,
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
        focused = true;
        open = true;
        caret = inputEl?.selectionStart ?? 0;
    }

    function onBlur() {
        setTimeout(() => {
            focused = false;
            if (!pointerInPopover) {
                open = false;
                activeIndex = -1;
            }
        }, 50);
    }

    onMount(async () => {
        if (autoFocus) inputEl?.focus();
        try {
            const res = await apiJson<CapabilitiesResponse>(
                "/api/mappings/query-capabilities",
            );
            if (res && Array.isArray(res.fields) && res.fields.length) {
                capabilities = res.fields as FieldCapability[];
            }
        } catch {}
    });

    function closePopover() {
        open = false;
        activeIndex = -1;
    }

    $effect(() => {
        if (!open) return;
        if (activeIndex < 0) return;
        const el = document.querySelector(
            `[data-booru-suggestion="${activeIndex}"]`,
        ) as HTMLElement | null;
        el?.scrollIntoView({ block: "nearest" });
    });
</script>

<div class="relative w-full" data-component="booru-search">
    <div bind:this={containerEl} class="relative flex items-center">
        <div
            class={`relative ml-auto transition-all duration-300 ease-in-out ${
                isActive ? "w-full" : "w-full sm:w-64 md:w-48"
            }`}
        >
            <input
                bind:this={inputEl}
                {placeholder}
                {disabled}
                {value}
                oninput={onInput}
                onkeydown={handleKeydown}
                onfocus={onFocus}
                onblur={onBlur}
                role="combobox"
                aria-expanded={open}
                aria-controls={listId}
                aria-label="Search mappings"
                class={`
                    w-full
                    ${size === "sm" ? "h-8 pr-9 pl-8" : "h-9 pr-10 pl-9"}
                    rounded-md 
                    border border-slate-700/70 
                    bg-slate-900/70 
                    text-[11px] 
                    shadow-sm 
                    placeholder:text-slate-500 
                    focus:border-slate-600 
                    focus:bg-slate-900
                    focus:outline-none
                `}
            />
            <Search
                class={`
                    pointer-events-none 
                    absolute 
                    top-1/2 
                    left-2.5 
                    -translate-y-1/2 
                    text-slate-500
                    ${size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"}
                `}
            />
            <button
                class={`
                    absolute 
                    top-1/2 
                    right-1 
                    inline-flex
                    -translate-y-1/2 
                    items-center 
                    justify-center 
                    rounded-md 
                    bg-slate-800 
                    text-slate-300 
                    transition-colors
                    hover:bg-slate-700
                    ${size === "sm" ? "h-6 w-6" : "h-7 w-7"}
                `}
                aria-label="Run search"
                onclick={() => {
                    closePopover();
                    onSubmit?.();
                }}
                {disabled}
            >
                <ArrowRight class={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
            </button>
        </div>
    </div>

    <Popover.Root
        bind:open
        onOpenChangeComplete={(o: boolean) => {
            if (!o) {
                activeIndex = -1;
                pointerInPopover = false;
            }
        }}
    >
        <Popover.Portal>
            <Popover.Content
                customAnchor={inputEl}
                side="bottom"
                align="end"
                sideOffset={6}
                trapFocus={false}
                onOpenAutoFocus={(e) => e.preventDefault()}
                updatePositionStrategy="always"
                class="focus-override data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 z-50 mt-1 w-[var(--bits-popover-anchor-width)] max-w-[90vw] overflow-hidden rounded-md border border-slate-800/70 bg-slate-900/95 shadow-xl outline-hidden backdrop-blur supports-[backdrop-filter]:bg-slate-900/75"
                onmouseenter={() => (pointerInPopover = true)}
                onmouseleave={() => {
                    pointerInPopover = false;
                    if (!focused) closePopover();
                }}
            >
                <ul
                    id={listId}
                    role="listbox"
                    class={"max-h-64 overflow-auto py-1 text-[11px]" +
                        (suggestions.length === 0 ? " hidden" : "")}
                >
                    {#each suggestions as s, i (s.label)}
                        <li>
                            <button
                                data-booru-suggestion={i}
                                role="option"
                                aria-selected={i === activeIndex}
                                class={`group flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-slate-800/70 ${i === activeIndex ? "bg-slate-800/70" : ""}`}
                                onmousedown={(e) => {
                                    e.preventDefault();
                                    applySuggestion(i);
                                }}
                            >
                                <span class="font-mono text-slate-200">{s.label}</span>
                                {#if s.detail}
                                    <span
                                        class="ml-2 shrink-0 text-[10px] text-slate-400"
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
                    Tips: Use '()' to group terms, '|' to OR between groups, '~' to OR
                    within a group, '-' to negate, '..' for ranges, '*' or '?' as
                    wildcards, and quotes for AniList title search.
                </div>
            </Popover.Content>
        </Popover.Portal>
    </Popover.Root>
</div>
