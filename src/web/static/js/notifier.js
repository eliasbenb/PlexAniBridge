/* Toast / error notifier.
 * Listens for custom events dispatched by services and network failures.
 */

(function () {
    const rootId = 'toast-root';
    function ensureRoot() {
        let el = document.getElementById(rootId);
        if (!el) {
            el = document.createElement('div');
            el.id = rootId;
            el.className = 'pointer-events-none fixed top-16 right-4 z-[60] flex w-80 max-w-[90vw] flex-col gap-2';
            document.body.appendChild(el);
        }
        return el;
    }
    const LEVEL_STYLES = {
        info: 'border-slate-600/70 bg-slate-800/80 text-slate-200',
        success: 'border-green-600/70 bg-green-950/70 text-green-200',
        warning: 'border-amber-600/70 bg-amber-950/70 text-amber-100',
        error: 'border-red-600/70 bg-red-950/70 text-red-200'
    };
    const ICONS = {
        info: 'lucide:info',
        success: 'lucide:check-circle',
        warning: 'lucide:alert-triangle',
        error: 'lucide:alert-octagon'
    };

    function toast(msg, level = 'info', opts = {}) {
        const root = ensureRoot();
        const div = document.createElement('div');
        div.role = 'status';
        div.className = `pointer-events-auto group relative overflow-hidden rounded-md border px-3 py-2 shadow backdrop-blur surface animate-fade-in-up ${LEVEL_STYLES[level] || LEVEL_STYLES.info}`;
        div.innerHTML = `\n            <div class="flex items-start gap-3 text-sm">\n              <iconify-icon icon="${ICONS[level] || ICONS.info}" class="mt-0.5 shrink-0" inline></iconify-icon>\n              <div class="flex-1 leading-snug">${msg}</div>\n              <button type="button" aria-label="Dismiss" class="opacity-60 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 rounded p-1" data-dismiss>&times;</button>\n            </div>`;
        const ttl = opts.ttl || (level === 'error' ? 12000 : 6000);
        let timeout = setTimeout(() => dismiss(), ttl);
        function dismiss() {
            if (timeout) { clearTimeout(timeout); timeout = null; }
            div.classList.add('animate-fade-out-down');
            setTimeout(() => div.remove(), 350);
        }
        div.addEventListener('mouseenter', () => { if (timeout) { clearTimeout(timeout); } });
        div.addEventListener('mouseleave', () => { if (!timeout) { timeout = setTimeout(() => dismiss(), ttl); } });
        div.addEventListener('click', e => { if (e.target.closest('[data-dismiss]')) dismiss(); });
        root.appendChild(div);
        return dismiss;
    }

    function formatErr(e) {
        if (!e) return 'Unknown error';
        if (typeof e === 'string') return e;
        if (e instanceof Error) return e.message;
        try { return JSON.stringify(e); } catch { return String(e); }
    }

    document.addEventListener('anilist-error', e => {
        const detail = e.detail || {};
        toast(`AniList: ${formatErr(detail.error || detail.message)}`, 'error');
    });
    document.addEventListener('plex-error', e => {
        const detail = e.detail || {};
        toast(`Plex: ${formatErr(detail.error || detail.message)}`, 'error');
    });
    document.addEventListener('plex-token-refreshed', e => {
        const d = e.detail || {};
        if (d.ok) {
            toast('Plex anonymous token refreshed', 'success', { ttl: 4000 });
        } else if (d.cleared) {
            toast('Plex token cleared', 'warning');
        } else if (d.error) {
            toast(`Plex token refresh failed: ${formatErr(d.error)}`, 'error');
        }
    });

    window.addEventListener('unhandledrejection', ev => {
        const reason = ev.reason;
        toast(`Unhandled error: ${formatErr(reason)}`, 'error');
    });

    window.notify = { toast };
})();
