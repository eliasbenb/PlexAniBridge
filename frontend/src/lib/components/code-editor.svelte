<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    import loader from "@monaco-editor/loader";
    import type * as Monaco from "monaco-editor/esm/vs/editor/editor.api";
    import { twMerge } from "tailwind-merge";

    interface Props {
        class?: string;
        value: string;
        language?: string;
        theme?: string;
        modelUri?: string;
        jsonSchema?: Monaco.languages.json.JSONSchema;
        performanceMode?: boolean;
    }

    let {
        class: className,
        value = $bindable(),
        language = "json",
        theme = "anibridge-dark",
        modelUri = `inmemory://model/untitled-${crypto.randomUUID()}.json`,
        jsonSchema,
        performanceMode = true,
    }: Props = $props();

    let editor: Monaco.editor.IStandaloneCodeEditor;
    let monaco: typeof Monaco;
    let editorContainer: HTMLElement;
    let isInitialized = false;

    const THEME_CONFIG = {
        base: "vs-dark" as const,
        inherit: true,
        rules: [
            { token: "comment", foreground: "64748b" },
            { token: "json-key", foreground: "7dd3fc" },
            { token: "string", foreground: "6ee7b7" },
            { token: "number", foreground: "fbbf24" },
            { token: "boolean", foreground: "a5b4fc" },
            { token: "null", foreground: "f9a8d4" },
            { token: "delimiter", foreground: "94a3b8" },
            { token: "delimiter.bracket", foreground: "94a3b8" },
        ],
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
    };

    const getBaseOptions = (): Monaco.editor.IStandaloneEditorConstructionOptions => ({
        language,
        theme: theme === "anibridge-dark" ? "anibridge-dark" : theme,
        automaticLayout: true,
        overviewRulerLanes: 0,
        overviewRulerBorder: false,
        wordWrap: "on",
        minimap: { enabled: false },
        fontSize: 12,
        scrollBeyondLastLine: false,
        formatOnPaste: true,
        formatOnType: false,
        extraEditorClassName: className,
    });

    const getPerformanceOptions =
        (): Partial<Monaco.editor.IStandaloneEditorConstructionOptions> => ({
            glyphMargin: false,
            folding: false,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 3,
            links: false,
            contextmenu: false,
            occurrencesHighlight: "off",
            selectionHighlight: false,
            renderLineHighlight: "line",
            renderWhitespace: "none",
            renderControlCharacters: false,
            smoothScrolling: false,
            dragAndDrop: false,
            codeLens: false,
            stickyScroll: { enabled: false },
            inlineSuggest: { enabled: false },
            suggest: { showIcons: false, showSnippets: false },
            hover: { delay: 600 },
            quickSuggestions: false,
            bracketPairColorization: { enabled: false },
            guides: { bracketPairs: false },
        });

    function applyJsonSchema(schema: Monaco.languages.json.JSONSchema) {
        if (!monaco || !schema || language !== "json") return;

        const schemaId =
            (schema as { $id?: string }).$id ||
            `inmemory://schema/mapping-${btoa(modelUri)}.json`;

        const jsonDefaults = monaco.languages?.json?.jsonDefaults;
        if (!jsonDefaults) return;

        const existingOptions = jsonDefaults.diagnosticsOptions || {};
        const existingSchemas: { uri: string }[] = existingOptions.schemas || [];
        const filteredSchemas = existingSchemas.filter((s) => s.uri !== schemaId);

        jsonDefaults.setDiagnosticsOptions({
            ...existingOptions,
            validate: true,
            enableSchemaRequest: true,
            schemas: [
                ...filteredSchemas,
                { uri: schemaId, fileMatch: [modelUri], schema },
            ],
        });
    }

    async function initializeEditor() {
        try {
            const monacoEditor = await import("monaco-editor");
            loader.config({ monaco: monacoEditor.default });
            monaco = await loader.init();

            monaco.editor.defineTheme("anibridge-dark", THEME_CONFIG);

            const uri = monaco.Uri.parse(modelUri);
            let model = monaco.editor.getModel(uri);

            if (!model) {
                model = monaco.editor.createModel(value, language, uri);
            } else {
                model.setValue(value);
            }

            if (jsonSchema) {
                applyJsonSchema(jsonSchema);
            }

            const options = {
                ...getBaseOptions(),
                ...(performanceMode ? getPerformanceOptions() : {}),
                model,
            };

            editor = monaco.editor.create(editorContainer, options);

            editor.onDidChangeModelContent((e) => {
                if (!e.isFlush) {
                    value = editor.getValue();
                }
            });

            isInitialized = true;
        } catch (error) {
            console.error("Failed to initialize Monaco Editor:", error);
        }
    }

    function updateEditorValue(newValue: string) {
        if (!editor || !isInitialized) return;

        const currentValue = editor.getValue();
        if (currentValue !== newValue && !editor.hasWidgetFocus()) {
            editor.setValue(newValue || "");
        }
    }

    onMount(initializeEditor);

    onDestroy(() => {
        monaco?.editor.getModels().forEach((model) => model.dispose());
        editor?.dispose();
    });

    $effect(() => {
        updateEditorValue(value);
    });

    $effect(() => {
        if (jsonSchema && isInitialized) {
            applyJsonSchema(jsonSchema);
        }
    });
</script>

<div
    class={twMerge(
        "monaco-editor-wrapper relative h-72 rounded border border-slate-800/60 bg-slate-950/70 text-[11px] leading-tight ring-slate-800/60 transition-shadow",
        className,
    )}>
    <div
        class="editor-container"
        bind:this={editorContainer}>
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
