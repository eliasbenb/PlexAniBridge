import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { SvelteKitPWA } from "@vite-pwa/sveltekit";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [tailwindcss(), sveltekit(), SvelteKitPWA()],
    server: {
        proxy: {
            "/api": { target: "http://localhost:4848", changeOrigin: true },
            "/ws": { target: "http://localhost:4848", changeOrigin: true, ws: true },
        },
    },
});
