self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
    // Wipe any existing caches created by previous versions
    e.waitUntil(
        (async () => {
            try {
                const keys = await caches.keys();
                await Promise.all(keys.map((k) => caches.delete(k)));
            } catch {}
            await self.clients.claim();
        })(),
    );
});
