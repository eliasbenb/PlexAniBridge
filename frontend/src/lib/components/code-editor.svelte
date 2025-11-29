<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    import type * as Monaco from "monaco-editor/esm/vs/editor/editor.api";
    import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
    import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
    import { twMerge } from "tailwind-merge";

    import yamlWorker from "./workaround?worker";

    interface Props {
        class?: string;
        content: string;
        language?: string;
        disabled?: boolean;
        schemas?: {
            uri: string;
            fileMatch: string[];
            schema?: { [key: string]: unknown };
        }[];
    }

    let {
        class: className = "",
        content = $bindable(),
        language,
        disabled,
        schemas,
    }: Props = $props();

    let divEl: HTMLDivElement | null = null;
    let editor: Monaco.editor.IStandaloneCodeEditor;

    onMount(async () => {
        self.MonacoEnvironment = {
            getWorker(_: unknown, label: string) {
                if (label === "json") {
                    return new jsonWorker();
                }
                if (label === "yaml") {
                    return new yamlWorker();
                }
                return new editorWorker();
            },
        };

        const [monaco, { configureMonacoYaml }] = await Promise.all([
            import("monaco-editor"),
            import("monaco-yaml"),
        ]);

        monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
            enableSchemaRequest: true,
            schemas: schemas,
            validate: true,
        });

        configureMonacoYaml(monaco, {
            hover: true,
            completion: true,
            enableSchemaRequest: true,
            format: true,
            schemas: schemas,
            validate: true,
        });

        monaco.editor.defineTheme("ab-theme", {
            base: "vs-dark" as const,
            inherit: true,
            colors: {
                "editor.background": "#020617",
                "editor.foreground": "#e2e8f0",
                "editor.inactiveSelectionBackground": "#1e293b",
                "editor.lineHighlightBackground": "#0f172a",
                "editor.selectionBackground": "#334155",
                "editorCursor.foreground": "#6ee7b7",
                "editorError.foreground": "#f87171",
                "editorHoverWidget.background": "#0f172a",
                "editorHoverWidget.border": "#334155",
                "editorIndentGuide.activeBackground": "#334155",
                "editorIndentGuide.background": "#1e293b",
                "editorInfo.foreground": "#38bdf8",
                "editorLineNumber.activeForeground": "#a5f3fc",
                "editorLineNumber.foreground": "#475569",
                "editorSuggestWidget.background": "#0f172a",
                "editorSuggestWidget.border": "#334155",
                "editorSuggestWidget.selectedBackground": "#065f46",
                "editorWarning.foreground": "#fbbf24",
                "editorWidget.background": "#0f172a",
                "editorWidget.border": "#334155",
                "scrollbarSlider.activeBackground": "#475569cc",
                "scrollbarSlider.background": "#1e293bcc",
                "scrollbarSlider.hoverBackground": "#334155cc",
            },
            rules: [],
        });

        editor = monaco.editor.create(divEl!, {
            value: content,
            language: language,
            automaticLayout: true,
            overviewRulerLanes: 0,
            overviewRulerBorder: false,
            wordWrap: "off",
            minimap: { enabled: false },
            fontSize: 12,
            scrollBeyondLastLine: false,
            formatOnPaste: true,
            formatOnType: false,
            theme: "ab-theme",
        });

        // hacky way to trigger suggestions all the time
        // by default, suggestions only trigger after ':' or ' '
        editor.onDidChangeModelContent(() => {
            content = editor.getValue();
            editor.trigger("keyboard", "editor.action.triggerSuggest", {});
        });
    });

    $effect(() => {
        editor?.updateOptions({ readOnly: disabled });
    });

    onDestroy(() => {
        editor?.dispose();
    });
</script>

<div
    class={twMerge(
        "monaco-editor-wrapper relative h-72 rounded border border-slate-800/60 bg-slate-950/70 text-[11px] leading-tight ring-slate-800/60 transition-shadow",
        className,
    )}>
    <div
        bind:this={divEl}
        class="editor-container">
    </div>
</div>

<style>
    .editor-container {
        width: 100%;
        height: 100%;
        font-size: 11px;
        line-height: 1.2;
    }

    :global(.monaco-editor-wrapper .overflow-guard) {
        border-radius: 0.25rem;
    }

    :global(.monaco-editor-wrapper .monaco-editor) {
        border-radius: 0.25rem;
        font-family:
            ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
            "Courier New", monospace;
    }

    :global(.monaco-editor-wrapper .monaco-editor .margin) {
        background: #020617;
    }

    :global(.monaco-editor-wrapper .monaco-editor .view-overlays .current-line) {
        background: #0f172a !important;
    }

    :global(.monaco-editor-wrapper .monaco-editor .line-numbers) {
        color: #475569 !important;
    }

    :global(.monaco-editor-wrapper:focus-within) {
        outline: 0;
    }
</style>
