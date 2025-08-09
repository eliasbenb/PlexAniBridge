/**
 * AniList client to manage caching and fetching AniList media.
 */
class AniListService {
    constructor(opts = {}) {
        this.cache = new Map();
        this.CACHE_KEY = 'anilist.cache.v1';
        this.CACHE_MAX = opts.cacheMax || 1000;
        this.CACHE_TTL_MS = (typeof window !== 'undefined' && typeof window.ANILIST_CACHE_TTL_MS === 'number' && window.ANILIST_CACHE_TTL_MS > 0)
            ? window.ANILIST_CACHE_TTL_MS
            : (opts.cacheTtlMs || 24 * 60 * 60 * 1000);
        this.TITLE_PREF_KEY = 'anilist.title.pref.v1';
        this.TITLE_PREFS = ['romaji', 'english', 'native'];
        this._loadCache();
    }

    _isExpired(entry) {
        if (!entry || !entry.t) return true;
        try { return (Date.now() - entry.t) > this.CACHE_TTL_MS; } catch { return true; }
    }

    _hasValid(id) {
        const v = this.cache.get(id);
        return !!(v && v.m && !this._isExpired(v));
    }

    _pruneExpired() {
        let removed = 0;
        const now = Date.now();
        for (const [id, v] of Array.from(this.cache.entries())) {
            if (!v || !v.m || !v.t || (now - v.t) > this.CACHE_TTL_MS) {
                this.cache.delete(id);
                removed++;
            }
        }
        if (removed) this._dispatch('anilist-cache-changed', { size: this.cache.size });
        return removed;
    }

    _loadCache() {
        try {
            const raw = localStorage.getItem(this.CACHE_KEY);
            if (!raw) return;
            const obj = JSON.parse(raw);
            if (!obj || typeof obj !== 'object' || !obj.data) return;
            const entries = Object.entries(obj.data);
            const now = Date.now();
            for (const [, v] of entries) {
                if (v && v.m && typeof v.m.id === 'number') {
                    const ts = (typeof v.t === 'number' && v.t > 0) ? v.t : now;
                    this.cache.set(v.m.id, { m: v.m, t: ts });
                }
            }
            this._pruneExpired();
        } catch { try { localStorage.removeItem(this.CACHE_KEY); } catch { } }
    }

    _saveCache() {
        try {
            this._pruneExpired();
            const data = {};
            const entries = Array.from(this.cache.entries())
                .sort((a, b) => (a[1]?.t ?? 0) - (b[1]?.t ?? 0)) // oldest first
                .slice(Math.max(0, this.cache.size - this.CACHE_MAX));
            for (const [id, val] of entries) {
                if (val && val.m) data[id] = { m: val.m, t: val.t || Date.now() };
            }
            localStorage.setItem(this.CACHE_KEY, JSON.stringify({ v: 1, data }));
            this._dispatch('anilist-cache-changed', { size: this.cache.size });
        } catch { }
    }

    clearCache(showAlert = true) {
        this.cache.clear();
        try { localStorage.removeItem(this.CACHE_KEY); } catch { }
        this._dispatch('anilist-cache-changed', { size: 0 });
        if (showAlert) { try { alert('AniList cache cleared.'); } catch { } }
    }

    cacheSize() {
        this._pruneExpired();
        return this.cache.size;
    }

    async fetch(ids) {
        if (!Array.isArray(ids) || !ids.length) return {};
        this._pruneExpired();
        const unique = [...new Set(ids.map(i => Number(i)).filter(n => Number.isFinite(n)))];
        const missing = unique.filter(id => !this._hasValid(id));
        if (missing.length) {
            for (let i = 0; i < missing.length; i += 50) {
                const chunk = missing.slice(i, i + 50);
                try {
                    const query = `query ($ids:[Int]) { Page(perPage:50) { media(id_in:$ids, type:ANIME) { id title { romaji english native } coverImage { medium large } format status episodes } } }`;
                    const res = await fetch('https://graphql.anilist.co', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                        body: JSON.stringify({ query, variables: { ids: chunk } })
                    });
                    if (!res.ok) continue;
                    const json = await res.json();
                    const media = json?.data?.Page?.media || [];
                    const now = Date.now();
                    for (const m of media) this.cache.set(m.id, { m, t: now });
                    this._saveCache();
                } catch { }
            }
        }
        const out = {};
        for (const id of unique) {
            const v = this.cache.get(id);
            if (v && v.m) out[id] = v.m;
        }
        return out;
    }

    getLanguage() {
        try {
            const v = localStorage.getItem(this.TITLE_PREF_KEY);
            return this.TITLE_PREFS.includes(v) ? v : 'romaji';
        } catch { return 'romaji'; }
    }

    setLanguage(pref) {
        if (!this.TITLE_PREFS.includes(pref)) return;
        try { localStorage.setItem(this.TITLE_PREF_KEY, pref); } catch { }
        this._dispatch('anilist-pref-changed', { pref });
    }

    getTitle(media, fallback = '') {
        if (!media) return fallback;
        const pref = this.getLanguage();
        const order = [pref, ...this.TITLE_PREFS.filter(p => p !== pref)];
        for (const key of order) {
            const v = media?.title?.[key];
            if (v) return v;
        }
        return fallback;
    }

    _dispatch(name, detail) {
        try { document.dispatchEvent(new CustomEvent(name, { detail })); } catch { }
        try { window.dispatchEvent(new CustomEvent(name, { detail })); } catch { }
    }
}

window.AniList = new AniListService();
