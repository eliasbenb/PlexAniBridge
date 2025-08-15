/**
 * Plex Discover client: obtains anonymous token, caches Plex metadata by GUID via GraphQL.
 */

class PlexService {
    constructor(opts = {}) {
        this.cache = new Map();
        this.CACHE_KEY = 'plex.cache.v1';
        this.CACHE_MAX = opts.cacheMax || 1000;
        this.CACHE_TTL_MS = (typeof window !== 'undefined' && typeof window.PLEX_CACHE_TTL_MS === 'number' && window.PLEX_CACHE_TTL_MS > 0)
            ? window.PLEX_CACHE_TTL_MS
            : (opts.cacheTtlMs || 24 * 60 * 60 * 1000);
        this.TOKEN_KEY = 'plex.token.v1';
        this.CLIENT_ID_KEY = 'plex.clientId.v1';
        this.TOKEN_TTL_MS = opts.tokenTtlMs || 12 * 60 * 60 * 1000;

        this._token = null;
        this._loadCache();
        this._loadToken();
    }

    _isExpired(entry) {
        if (!entry || !entry.t) return true;
        try { return (Date.now() - entry.t) > this.CACHE_TTL_MS; } catch { return true; }
    }

    _hasValid(guid) {
        const v = this.cache.get(guid);
        return !!(v && v.m && !this._isExpired(v));
    }

    _pruneExpired() {
        let removed = 0;
        const now = Date.now();
        for (const [guid, v] of Array.from(this.cache.entries())) {
            if (!v || !v.m || !v.t || (now - v.t) > this.CACHE_TTL_MS) {
                this.cache.delete(guid);
                removed++;
            }
        }
        if (removed) this._dispatch('plex-cache-changed', { size: this.cache.size });
        return removed;
    }

    _loadCache() {
        try {
            const raw = localStorage.getItem(this.CACHE_KEY);
            if (!raw) return;
            const obj = JSON.parse(raw);
            if (!obj || typeof obj !== 'object' || !obj.data) return;
            const now = Date.now();
            for (const [, v] of Object.entries(obj.data)) {
                if (v && v.m && typeof v.m.guid === 'string') {
                    const ts = (typeof v.t === 'number' && v.t > 0) ? v.t : now;
                    this.cache.set(v.m.guid, { m: v.m, t: ts });
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
            for (const [guid, val] of entries) {
                if (val && val.m) data[guid] = { m: val.m, t: val.t || Date.now() };
            }
            localStorage.setItem(this.CACHE_KEY, JSON.stringify({ v: 1, data }));
            this._dispatch('plex-cache-changed', { size: this.cache.size });
        } catch { }
    }

    clearCache(showAlert = true) {
        this.cache.clear();
        try { localStorage.removeItem(this.CACHE_KEY); } catch { }
        this._dispatch('plex-cache-changed', { size: 0 });
        if (showAlert) { try { alert('Plex cache cleared.'); } catch { } }
    }

    cacheSize() {
        this._pruneExpired();
        return this.cache.size;
    }

    _loadToken() {
        try {
            const raw = localStorage.getItem(this.TOKEN_KEY);
            if (!raw) return;
            const obj = JSON.parse(raw);
            if (obj && typeof obj.token === 'string') {
                this._token = obj;
            }
        } catch { try { localStorage.removeItem(this.TOKEN_KEY); } catch { } }
    }

    _saveToken() {
        try { localStorage.setItem(this.TOKEN_KEY, JSON.stringify(this._token)); } catch { }
    }

    async _getToken() {
        const now = Date.now();
        if (this._token && this._token.token && (now - (this._token.t || 0)) < this.TOKEN_TTL_MS) {
            return this._token.token;
        }
        return await this._fetchAnonymousToken();
    }

    _genClientId() {
        try {
            let cid = localStorage.getItem(this.CLIENT_ID_KEY);
            if (cid) return cid;
            // Basic UUID (RFC4122-ish) generator
            const tpl = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
            cid = tpl.replace(/[xy]/g, c => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
            localStorage.setItem(this.CLIENT_ID_KEY, cid);
            return cid;
        } catch { return 'PlexAniBridgeWeb'; }
    }

    async _fetchAnonymousToken() {
        const clientId = this._genClientId();
        const headers = {
            'Accept': 'application/json',
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '4.148.0',
            'X-Plex-Client-Identifier': clientId,
            'X-Plex-Platform': (typeof navigator !== 'undefined'
                ? (navigator.userAgentData?.platform || 'Web')
                : 'Web'),
            'X-Plex-Device': 'Web',
            'X-Plex-Device-Name': 'PlexAniBridge'
        };
        try {
            const res = await fetch('https://plex.tv/api/v2/users/anonymous', { method: 'POST', headers });
            if (!res.ok) throw new Error('anon token http ' + res.status);
            const json = await res.json();
            const token = json?.authToken;
            if (!token) throw new Error('no token');
            this._token = { token, t: Date.now() };
            this._saveToken();
            return token;
        } catch (e) {
            this._dispatch('plex-token-refreshed', { ok: false, error: String(e) });
            this._dispatch('plex-error', { error: 'Token fetch failed: ' + String(e) });
            return null;
        }
    }

    clearToken(showAlert = true) {
        this._token = null;
        try { localStorage.removeItem(this.TOKEN_KEY); } catch { }
        if (showAlert) { try { alert('Plex anonymous token cleared.'); } catch { } }
        this._dispatch('plex-token-refreshed', { ok: false, cleared: true });
    }

    async refreshToken(force = false) {
        if (!force) {
            const token = await this._getToken();
            return token;
        }
        return await this._fetchAnonymousToken();
    }

    async fetch(guids) {
        if (!Array.isArray(guids) || !guids.length) return {};
        this._pruneExpired();
        const unique = [...new Set(guids.map(g => (g == null ? '' : String(g))).filter(Boolean))];
        const missing = unique.filter(g => !this._hasValid(g));
        if (missing.length) {
            const token = await this._getToken();
            if (!token) return this._collect(unique);

            // Chunk metadata requests into batches of 50
            for (let i = 0; i < missing.length; i += 50) {
                const chunk = missing.slice(i, i + 50);
                await this._fetchChunkMetadata(chunk, token);
            }
            this._saveCache();
        }
        return this._collect(unique);
    }

    _collect(keys) {
        const out = {};
        for (const k of keys) {
            const v = this.cache.get(k);
            if (v && v.m) out[k] = v.m;
        }
        return out;
    }

    async _fetchChunkMetadata(chunk, token) {
        if (!chunk.length) return;
        const shortGuids = chunk.map(g => (g.split('/').pop() || '').trim()).filter(Boolean);
        if (!shortGuids.length) return;

        const base = (typeof window !== 'undefined' && window.PLEX_METADATA_BASE) || 'https://metadata.provider.plex.tv';
        const url = `${base}/library/metadata/${encodeURIComponent(shortGuids.join(','))}?includeUserState=1`;
        const headers = {
            'Accept': 'application/xml, text/xml, application/json',
            'X-Plex-Token': token,
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '4.148.0',
            'X-Plex-Client-Identifier': this._genClientId(),
            'X-Plex-Platform': (typeof navigator !== 'undefined' ? (navigator.platform || 'Web') : 'Web'),
            'X-Plex-Device': 'Web',
            'X-Plex-Device-Name': 'PlexAniBridge'
        };
        try {
            const res = await fetch(url, { method: 'GET', headers });
            if (res.status === 401 || res.status === 403) {
                const newToken = await this._fetchAnonymousToken();
                if (!newToken) return;
                return await this._fetchChunkMetadata(chunk, newToken);
            }
            if (!res.ok) { this._dispatch('plex-error', { status: res.status, message: 'Metadata request failed', chunk }); return; }
            const ct = res.headers.get('Content-Type') || '';
            let items = [];
            if (ct.includes('json')) {
                const json = await res.json();
                const arr = json?.MediaContainer?.Metadata || json?.Metadata || [];
                items = Array.isArray(arr) ? arr : [];
            } else {
                const text = await res.text();
                items = this._parseMetadataXml(text);
            }
            const now = Date.now();
            // Map short guid back to full guid if necessary by matching endings
            for (const it of items) {
                if (!it.guid) continue;
                const full = chunk.find(g => it.guid.endsWith(g.split('/').pop()));
                const key = full || it.guid; // prefer full original
                this.cache.set(key, { m: it, t: now });
            }
        } catch (e) { this._dispatch('plex-error', { error: String(e), chunk }); }
    }

    _parseMetadataXml(xmlText) {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(xmlText, 'application/xml');
            if (doc.querySelector('parsererror')) return [];
            const metas = Array.from(doc.querySelectorAll('MediaContainer > *'));
            return metas.map(el => {
                const obj = {};
                // Copy attributes
                for (const attr of el.attributes) obj[attr.name] = attr.value;
                // Normalized fields
                obj.guid = obj.guid || null;
                obj.title = obj.title || obj.originalTitle || null;
                // Build thumb/art absolute if relative (prefix base)
                const base = (typeof window !== 'undefined' && window.PLEX_METADATA_BASE) || 'https://metadata.provider.plex.tv';
                if (obj.thumb && obj.thumb.startsWith('/')) obj.thumb = base + obj.thumb;
                if (obj.art && obj.art.startsWith('/')) obj.art = base + obj.art;
                return obj;
            });
        } catch { return []; }
    }

    getTitle(media, fallback = '') {
        if (!media) return fallback;
        return media.title || fallback;
    }

    _dispatch(name, detail) {
        try { document.dispatchEvent(new CustomEvent(name, { detail })); } catch { }
        try { window.dispatchEvent(new CustomEvent(name, { detail })); } catch { }
    }
}

window.Plex = new PlexService();
