import type { PinFieldOption, PinOptionsResponse } from "$lib/types/api";
import { apiFetch } from "$lib/utils/api";

interface PinOptionsState {
    cache: PinFieldOption[] | null;
    inflight: Promise<PinFieldOption[]> | null;
}

const state: PinOptionsState = { cache: null, inflight: null };

export async function loadPinOptions(force = false): Promise<PinFieldOption[]> {
    if (!force && state.cache) return [...state.cache];
    if (!force && state.inflight) return state.inflight;

    state.inflight = (async () => {
        const res = await apiFetch("/api/pins/fields", undefined, { silent: true });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = (await res.json()) as PinOptionsResponse;
        const options = payload.options ?? [];
        state.cache = [...options];
        return [...options];
    })();

    try {
        return await state.inflight;
    } finally {
        state.inflight = null;
    }
}

export function clearPinOptionsCache(): void {
    state.cache = null;
}
