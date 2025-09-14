<script lang="ts">
    import { onMount } from "svelte";

    import {
        Activity,
        Github,
        LayoutDashboard,
        List,
        Menu,
        RotateCw,
        Settings,
        Terminal,
        X,
    } from "@lucide/svelte";

    import { resolve } from "$app/paths";
    import { page } from "$app/state";
    import logo from "$lib/assets/favicon.svg";

    import "../app.css";

    let { children } = $props();
    let version = $state("v?");
    let gitHash = $state("");
    let sidebarOpen = $state(false);
    let ws: WebSocket | null = null;
    let isWsOpen = $state(false);

    function active(href: string, rootMatch = false) {
        const path = page.url.pathname;
        if (href === "/" && rootMatch) return path === "/";
        return href !== "/" && path.startsWith(href);
    }

    async function loadMeta() {
        try {
            const r = await fetch("/api/system/meta");
            if (!r.ok) return;
            const d = await r.json();
            if (d.version) version = d.version;
            if (d.git_hash) gitHash = d.git_hash;
        } catch {}
    }

    function openWs() {
        try {
            ws?.close();
        } catch {}
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(proto + "//" + location.host + "/ws/status");
        ws.onopen = () => {
            isWsOpen = true;
        };
        ws.onclose = () => {
            isWsOpen = false;
            setTimeout(openWs, 3000);
        };
    }

    onMount(() => {
        loadMeta();
        openWs();

        if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
            navigator.serviceWorker
                .register("/sw.js")
                .then(() => {
                    // Service worker registered
                })
                .catch(() => {
                    // Registration failed; continue without SW
                });
        }
    });
</script>

<svelte:head>
    <title>PlexAniBridge</title>
</svelte:head>

<div
    class="min-h-dvh bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-950 via-slate-950 to-slate-900 text-slate-100 antialiased selection:bg-blue-600/40 selection:text-white"
>
    <!-- Toast mount point -->
    <div
        id="toast-root"
        class="pointer-events-none fixed top-16 right-4 z-[60] flex w-80 max-w-[90vw] flex-col gap-2"
    ></div>
    <a
        href="#main"
        class="sr-only bg-blue-600 px-3 py-2 text-sm font-medium text-white shadow-lg focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md"
        >Skip to content</a
    >
    <!-- Mobile backdrop -->
    {#if sidebarOpen}
        <div
            class="fixed inset-0 z-30 bg-slate-900/70 backdrop-blur-sm lg:hidden"
            role="button"
            aria-label="Close sidebar"
            tabindex="0"
            onclick={() => (sidebarOpen = false)}
            onkeydown={(e) =>
                (e.key === "Escape" || e.key === "Enter" || e.key === " ") &&
                (e.preventDefault(), (sidebarOpen = false))}
        ></div>
    {/if}
    <!-- Sidebar -->
    <aside
        class="fixed inset-y-0 left-0 z-40 flex w-64 -translate-x-full flex-col border-r border-slate-800 bg-slate-950/95 px-3 pt-4 pb-6 shadow-xl shadow-slate-950/50 backdrop-blur transition-transform duration-300 ease-out lg:translate-x-0"
        class:translate-x-0={sidebarOpen}
    >
        <div class="mb-4 flex items-center gap-3 px-2">
            <img src={logo} alt="Logo" class="h-8 w-8" loading="lazy" />
            <a href={resolve("/")} class="group">
                <h1 class="text-base font-semibold tracking-tight text-white">
                    PlexAniBridge
                </h1>
                <p class="text-[11px] tracking-wide text-slate-500 uppercase">
                    Sync Dashboard
                </p>
            </a>
        </div>
        <nav class="flex flex-1 flex-col gap-1 text-sm font-medium">
            <a
                href={resolve("/")}
                class="nav-link {active('/', true) ? 'nav-link-active' : ''}"
                aria-current={active("/", true) ? "page" : undefined}
                ><LayoutDashboard class="inline h-4 w-4" /><span>Dashboard</span></a
            >
            <a
                href={resolve("/mappings")}
                class="nav-link {active('/mappings') ? 'nav-link-active' : ''}"
                aria-current={active("/mappings") ? "page" : undefined}
                ><List class="inline h-4 w-4" /><span>Mappings</span></a
            >
            <a
                href={resolve("/logs")}
                class="nav-link {active('/logs') ? 'nav-link-active' : ''}"
                aria-current={active("/logs") ? "page" : undefined}
                ><Terminal class="inline h-4 w-4" /><span>Logs</span></a
            >
            <div
                class="mt-4 px-3 text-[10px] font-semibold tracking-wider text-slate-500 uppercase"
            >
                System
            </div>
            <a
                href={resolve("/settings")}
                class="nav-link {active('/settings') ? 'nav-link-active' : ''}"
                aria-current={active("/settings") ? "page" : undefined}
                ><Settings class="inline h-4 w-4" /><span>Settings</span></a
            >
            <a
                href={resolve("/about")}
                class="nav-link {active('/about') ? 'nav-link-active' : ''}"
                aria-current={active("/about") ? "page" : undefined}
                ><Activity class="inline h-4 w-4" /><span>About</span></a
            >
            <div class="mt-auto border-t border-slate-800/60 pt-4">
                <p class="px-3 text-[11px] text-slate-500">
                    © {new Date().getFullYear()}
                    <a
                        href="https://plexanibridge.elias.eu.org"
                        target="_blank"
                        rel="noopener"
                        class="transition-colors hover:text-slate-200">PlexAniBridge</a
                    >
                </p>
            </div>
        </nav>
    </aside>
    <!-- Main content wrapper -->
    <div class="flex min-h-dvh w-full flex-col lg:pl-64">
        <!-- Top bar -->
        <header
            class="sticky top-0 z-20 flex h-14 w-full items-center gap-3 border-b border-slate-800/80 bg-slate-950/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-slate-950/65"
        >
            <button
                type="button"
                class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-700/70 bg-slate-800/70 text-slate-300 hover:bg-slate-700/70 hover:text-white focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none lg:hidden"
                aria-label="Toggle navigation"
                onclick={() => (sidebarOpen = !sidebarOpen)}
            >
                {#if sidebarOpen}
                    <X class="inline h-4 w-4" />
                {:else}
                    <Menu class="inline h-4 w-4" />
                {/if}
            </button>
            <div class="flex flex-1 items-center gap-3">
                <div
                    class="hidden items-center gap-2 rounded-md border border-slate-700/60 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-400 sm:flex"
                    aria-live="polite"
                >
                    <span class="relative flex h-2 w-2">
                        <span
                            class={`absolute inline-flex h-full w-full rounded-md ${isWsOpen ? "animate-ping bg-blue-500/60" : "bg-amber-500/40"}`}
                        ></span>
                        <span
                            class={`relative inline-flex h-2 w-2 rounded-md ${isWsOpen ? "bg-blue-500" : "bg-amber-500"}`}
                        ></span>
                    </span>
                    <span class="font-medium">{isWsOpen ? "Live" : "Offline"}</span>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <button
                    type="button"
                    class="btn-base border border-slate-700/70 bg-slate-800/70 text-slate-300 hover:bg-slate-700/70 hover:text-white focus-visible:ring-blue-500"
                    onclick={() => location.reload()}
                >
                    <RotateCw class="inline h-4 w-4" />
                    <span class="hidden sm:inline">Refresh</span>
                </button>
            </div>
        </header>
        <!-- Page content area -->
        <main id="main" class="flex-1 p-4 sm:p-6">
            <div class="fade-in space-y-8">{@render children?.()}</div>
        </main>
        <!-- Footer -->
        <footer
            class="mt-auto border-t border-slate-800/80 bg-slate-950/70 px-4 py-4 text-[11px] text-slate-500 backdrop-blur"
        >
            <div
                class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
            >
                <div class="flex flex-wrap items-center gap-3">
                    <a
                        href="https://github.com/eliasbenb/PlexAniBridge"
                        target="_blank"
                        rel="noopener"
                        class="inline-flex items-center gap-1 text-slate-400 transition-colors hover:text-slate-200"
                    >
                        <Github class="inline h-4 w-4" /><span>GitHub</span>
                    </a>
                    <div>
                        <a
                            href={`https://github.com/eliasbenb/PlexAniBridge/releases/tag/v${version}`}
                            target="_blank"
                            rel="noopener"
                            class="text-slate-600 transition-colors hover:text-slate-200"
                            >v{version}</a
                        >
                        {#if gitHash}
                            <a
                                href={`https://github.com/eliasbenb/PlexAniBridge/tree/${gitHash}`}
                                target="_blank"
                                rel="noopener"
                                class="ml-1 text-slate-600 transition-colors hover:text-slate-200"
                                >({gitHash.slice(0, 7)})</a
                            >
                        {/if}
                    </div>
                </div>
                <div class="text-slate-600">
                    Made by <a
                        href="https://github.com/eliasbenb"
                        target="_blank"
                        rel="noopener"
                        class="transition-colors hover:text-slate-200">@eliasbenb</a
                    >
                </div>
            </div>
        </footer>
    </div>
</div>
