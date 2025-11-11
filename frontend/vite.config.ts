import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { SvelteKitPWA } from "@vite-pwa/sveltekit";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [
        tailwindcss(),
        sveltekit(),
        SvelteKitPWA({
            registerType: "autoUpdate",
            includeAssets: [
                "favicon.ico",
                "apple-touch-icon.png",
                "pwa-192x192.png",
                "pwa-512x512.png",
                "pwa-maskable-192x192.png",
                "pwa-maskable-512x512.png",
            ],
            devOptions: { enabled: false },
            workbox: { maximumFileSizeToCacheInBytes: 8000000 },
            manifest: {
                name: "AniBridge",
                short_name: "AniBridge",
                icons: [
                    {
                        src: "/pwa-192x192.png",
                        sizes: "192x192",
                        type: "image/png",
                        purpose: "any",
                    },
                    {
                        src: "/pwa-512x512.png",
                        sizes: "512x512",
                        type: "image/png",
                        purpose: "any",
                    },
                    {
                        src: "/pwa-maskable-192x192.png",
                        sizes: "192x192",
                        type: "image/png",
                        purpose: "maskable",
                    },
                    {
                        src: "/pwa-maskable-512x512.png",
                        sizes: "512x512",
                        type: "image/png",
                        purpose: "maskable",
                    },
                ],
                start_url: "/",
                display: "standalone",
                background_color: "#05070d",
                theme_color: "#020618",
                description:
                    "The smart way to keep your AniList profile perfectly synchronized with your Plex library.",
            },
        }),
    ],
    server: {
        proxy: {
            "/api": { target: "http://localhost:4848", changeOrigin: true },
            "/ws": { target: "http://localhost:4848", changeOrigin: true, ws: true },
        },
    },
});
