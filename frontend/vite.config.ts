import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [tailwindcss(), sveltekit()],
    server: {
        proxy: {
            "/api": { target: "http://localhost:4848", changeOrigin: true },
            "/ws": { target: "http://localhost:4848", changeOrigin: true, ws: true },
        },
    },
});
