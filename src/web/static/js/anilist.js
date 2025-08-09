/**
 * AniList utility functions.
 */

const __aniCache = new Map();
const __ANI_CACHE_KEY = 'anilist.cache.v1';
const __ANI_CACHE_MAX = 1000;
const __ANI_CACHE_TTL_MS = (typeof window !== 'undefined' && typeof window.ANILIST_CACHE_TTL_MS === 'number' && window.ANILIST_CACHE_TTL_MS > 0)
    ? window.ANILIST_CACHE_TTL_MS
    : 24 * 60 * 60 * 1000; // 24 hours

function __aniCache_isExpired(entry) {
    if (!entry || !entry.t) return true;
    try { return (Date.now() - entry.t) > __ANI_CACHE_TTL_MS; } catch { return true; }
}

function __aniCache_hasValid(id) {
    const v = __aniCache.get(id);
    return !!(v && v.m && !__aniCache_isExpired(v));
}

function __aniCache_pruneExpired() {
    let removed = 0;
    const now = Date.now();
    for (const [id, v] of Array.from(__aniCache.entries())) {
        if (!v || !v.m || !v.t || (now - v.t) > __ANI_CACHE_TTL_MS) {
            __aniCache.delete(id);
            removed++;
        }
    }
    if (removed) {
        try { document.dispatchEvent(new CustomEvent('anilist-cache-changed', { detail: { size: __aniCache.size } })); } catch { }
    }
    return removed;
}

function __aniCache_load() {
    try {
        const raw = localStorage.getItem(__ANI_CACHE_KEY);
        if (!raw) return;

        const obj = JSON.parse(raw);
        if (!obj || typeof obj !== 'object' || !obj.data) return;

        const entries = Object.entries(obj.data);
        const now = Date.now();

        for (const [k, v] of entries) {
            if (v && v.m && typeof v.m.id === 'number') {
                const ts = (typeof v.t === 'number' && v.t > 0) ? v.t : now;
                __aniCache.set(v.m.id, { m: v.m, t: ts });
            }
        }

        __aniCache_pruneExpired();
    } catch (_) {
        try { localStorage.removeItem(__ANI_CACHE_KEY); } catch { }
    }
}

function __aniCache_save() {
    try {
        const data = {};
        __aniCache_pruneExpired();

        const entries = Array.from(__aniCache.entries());
        entries.sort((a, b) => (a[1]?.t ?? 0) - (b[1]?.t ?? 0)); // oldest first

        const recent = entries.slice(Math.max(0, entries.length - __ANI_CACHE_MAX));
        for (const [id, val] of recent) {
            if (val && val.m) data[id] = { m: val.m, t: val.t || Date.now() };
        }

        const payload = { v: 1, data };
        localStorage.setItem(__ANI_CACHE_KEY, JSON.stringify(payload));

        try {
            document.dispatchEvent(new CustomEvent('anilist-cache-changed', { detail: { size: __aniCache.size } }));
        } catch { }
    } catch (_) { }
}

function __aniCache_clear(showAlert = true) {
    __aniCache.clear();
    try { localStorage.removeItem(__ANI_CACHE_KEY); } catch { }
    try { document.dispatchEvent(new CustomEvent('anilist-cache-changed', { detail: { size: 0 } })); } catch { }
    if (showAlert) {
        try { alert('AniList cache cleared.'); } catch { }
    }
}

window.clearAniListCache = () => __aniCache_clear(true);
window.getAniListCacheSize = () => { __aniCache_pruneExpired(); return __aniCache.size; };

__aniCache_load();

async function batchFetchAniList(ids) {
    __aniCache_pruneExpired();
    const missing = ids.filter(id => !__aniCache_hasValid(id));
    if (missing.length) {
        const chunks = []; for (let i = 0; i < missing.length; i += 50) chunks.push(missing.slice(i, i + 50));
        for (const chunk of chunks) {
            try {
                const query = `query ($ids:[Int]) { Page(perPage:50) { media(id_in:$ids, type:ANIME) { id title { romaji english native } coverImage { medium large } format status episodes } } }`;
                const res = await fetch('https://graphql.anilist.co', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ query, variables: { ids: chunk } }) });
                if (!res.ok) continue;
                const json = await res.json();
                const media = json?.data?.Page?.media || [];
                const now = Date.now();
                for (const m of media) { __aniCache.set(m.id, { m, t: now }); }
                __aniCache_save();
            } catch (e) { }
        }
    }
    const out = {};
    for (const id of ids) { const v = __aniCache.get(id); if (v && v.m) out[id] = v.m; }
    return out;
}
