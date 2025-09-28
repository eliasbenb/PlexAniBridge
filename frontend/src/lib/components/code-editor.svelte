<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    import loader from "@monaco-editor/loader";
    import type * as Monaco from "monaco-editor/esm/vs/editor/editor.api";
    import { twMerge } from "tailwind-merge";

    let editor: Monaco.editor.IStandaloneCodeEditor;
    let monaco: typeof Monaco;
    let editorContainer: HTMLElement;

    interface Props {
        class?: string;
        value: string;
        language?: string;
        theme?: string;
        modelUri?: string;
        jsonSchema?: Record<string, unknown>;
        performanceMode?: boolean;
    }

    let {
        class: className,
        value = $bindable(),
        language = "json",
        theme = "pab-dark",
        modelUri = "inmemory://model/untitled-" + crypto.randomUUID() + ".json",
        jsonSchema = undefined,
        performanceMode = true,
    }: Props = $props();

    function applyJsonSchema(schema: Record<string, unknown>) {
        if (!monaco || !schema) return;

        const schemaId =
            typeof (schema as { $id?: string }).$id === "string"
                ? (schema as { $id: string }).$id
                : "inmemory://schema/mapping-" + btoa(modelUri) + ".json";

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const jsonLang: any = (monaco as unknown as { languages: unknown }).languages;
        const jsonDefaults = jsonLang?.json?.jsonDefaults;
        if (!jsonDefaults) return;

        const existingOpts = jsonDefaults.diagnosticsOptions || {};
        const prevSchemas: { uri: string }[] = existingOpts.schemas || [];
        const filtered = prevSchemas.filter((s) => s.uri !== schemaId);

        jsonDefaults.setDiagnosticsOptions({
            ...existingOpts,
            validate: true,
            enableSchemaRequest: true,
            schemas: [...filtered, { uri: schemaId, fileMatch: [modelUri], schema }],
        });
    }

    let themeDefined = false;
    function defineTheme() {
        if (!monaco || themeDefined) return;

        monaco.editor.defineTheme("pab-dark", {
            base: "vs-dark",
            inherit: true,
            rules: [
                { token: "comment", foreground: "64748b" }, // slate-500
                { token: "json-key", foreground: "7dd3fc" }, // sky-300
                { token: "string", foreground: "6ee7b7" }, // emerald-300
                { token: "number", foreground: "fbbf24" }, // amber-400
                { token: "boolean", foreground: "a5b4fc" }, // indigo-300
                { token: "null", foreground: "f9a8d4" }, // pink-300
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
        });
        themeDefined = true;
    }

    onMount(() => {
        (async () => {
            const monacoEditor = await import("monaco-editor");
            loader.config({ monaco: monacoEditor.default });

            monaco = await loader.init();

            defineTheme();

            // Create or reuse a model so schema association works reliably
            let model = monaco.editor.getModel(monaco.Uri.parse(modelUri));
            if (!model) {
                model = monaco.editor.createModel(
                    value,
                    language,
                    monaco.Uri.parse(modelUri),
                );
            } else {
                model.setValue(value);
            }

            if (language === "json" && jsonSchema) {
                applyJsonSchema(jsonSchema);
            }

            const baseOptions: Monaco.editor.IStandaloneEditorConstructionOptions = {
                model,
                language,
                theme: theme === "pab-dark" ? "pab-dark" : theme,
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
            };

            const perfOptions: Partial<Monaco.editor.IStandaloneEditorConstructionOptions> =
                performanceMode
                    ? {
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
                      }
                    : {};

            editor = monaco.editor.create(editorContainer, {
                ...baseOptions,
                ...perfOptions,
            });

            editor.onDidChangeModelContent((e) => {
                if (e.isFlush) {
                } else {
                    const updatedValue = editor?.getValue() ?? " ";
                    value = updatedValue;
                }
            });
        })();
    });

    $effect(() => {
        if (value) {
            if (editor) {
                if (editor.hasWidgetFocus()) {
                } else {
                    if (editor?.getValue() ?? " " !== value) {
                        editor?.setValue(value);
                    }
                }
            }
        }
        if (value === "") {
            editor?.setValue(" ");
        }
        if (language === "json" && jsonSchema) {
            applyJsonSchema(jsonSchema);
        }
    });

    onDestroy(() => {
        monaco?.editor.getModels().forEach((model) => model.dispose());
        editor?.dispose();
    });
</script>

<div
    class={twMerge(
        "pab-code-editor-wrapper relative h-72 rounded border border-slate-800/60 bg-slate-950/70 text-[11px] leading-tight ring-slate-800/60 transition-shadow",
        className,
    )}>
    <div
        class="container"
        bind:this={editorContainer}>
    </div>
</div>

<style>
    .container {
        width: 100%;
        height: 100%;
        padding: 0;
        font-size: 11px;
        line-height: 1.2;
    }

    :global(.pab-code-editor-wrapper .overflow-guard) {
        border-radius: 0.25rem; /* rounded */
    }

    :global(.pab-code-editor-wrapper .monaco-editor) {
        border-radius: 0.25rem; /* rounded */
        font-family:
            ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
            "Courier New", monospace;
    }
    :global(.pab-code-editor-wrapper .monaco-editor .margin) {
        background: #020617; /* keep subtle */
    }
    :global(.pab-code-editor-wrapper .monaco-editor .view-overlays .current-line) {
        background: #0f172a !important;
    }
    :global(.pab-code-editor-wrapper .monaco-editor .line-numbers) {
        color: #475569 !important;
    }
    :global(.pab-code-editor-wrapper:focus-within) {
        outline: 0;
    }
</style>
