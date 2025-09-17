const CACHE_NAME = "pab-cache-v1";
const ASSETS = [
    "/pwa-192x192.png",
    "/pwa-512x512.png",
    "/pwa-maskable-192x192.png",
    "/pwa-maskable-512x512.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
                ),
            ),
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request)
                .then((res) => {
                    if (
                        res &&
                        res.status === 200 &&
                        event.request.url.startsWith(self.location.origin)
                    ) {
                        const copy = res.clone();
                        caches
                            .open(CACHE_NAME)
                            .then((cache) => cache.put(event.request, copy));
                    }
                    return res;
                })
                .catch(() => caches.match("/"));
        }),
    );
});
