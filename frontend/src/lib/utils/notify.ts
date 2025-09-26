import { writable } from "svelte/store";

export type ToastType = "info" | "success" | "error" | "warn";

export interface ToastOptions {
    timeout?: number;
    id?: string;
}

export interface Toast {
    id: string;
    message: string;
    type: ToastType;
    created: number;
    timeout: number;
}

export interface ToastConfig {
    durations: Record<ToastType, number>;
}

const DEFAULT_CONFIG: ToastConfig = {
    durations: { info: 4000, success: 3000, warn: 6500, error: 9000 },
};

const CONFIG_KEY = "toast.config";

function loadConfig(): ToastConfig {
    if (typeof localStorage === "undefined") return DEFAULT_CONFIG;
    try {
        const raw = localStorage.getItem(CONFIG_KEY);
        if (!raw) return DEFAULT_CONFIG;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return DEFAULT_CONFIG;
        const d = (parsed as ToastConfig).durations || {};
        return { durations: { ...DEFAULT_CONFIG.durations, ...d } };
    } catch {
        return DEFAULT_CONFIG;
    }
}

export const toastConfig = writable<ToastConfig>(loadConfig());
let currentConfig = loadConfig();
toastConfig.subscribe((c) => {
    currentConfig = c;
    try {
        if (typeof localStorage !== "undefined")
            localStorage.setItem(CONFIG_KEY, JSON.stringify(c));
    } catch {}
});

export const toasts = writable<Toast[]>([]);

const DEDUPE_WINDOW = 2500;

let lastShown: { message: string; at: number } | null = null;

export function toast(
    message: string,
    type: ToastType = "info",
    opts: ToastOptions = {},
) {
    if (!message) return;
    const now = Date.now();
    if (
        lastShown &&
        lastShown.message === message &&
        now - lastShown.at < DEDUPE_WINDOW
    ) {
        return; // suppress duplicate
    }
    lastShown = { message, at: now };
    const t: Toast = {
        id: opts.id || Math.random().toString(36).slice(2, 10),
        message,
        type,
        created: now,
        timeout: opts.timeout ?? currentConfig.durations[type],
    };
    toasts.update((list) => [t, ...list]);
    if (t.timeout > 0) {
        setTimeout(() => {
            toasts.update((list) => list.filter((x) => x.id !== t.id));
        }, t.timeout);
    }
}

export function dismiss(id: string) {
    toasts.update((list) => list.filter((t) => t.id !== id));
}

export function updateToastDurations(partial: Partial<Record<ToastType, number>>) {
    toastConfig.update((c) => ({ durations: { ...c.durations, ...partial } }));
}
