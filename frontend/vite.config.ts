import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    svgr({
      svgrOptions: {
        icon: true,
        // This will transform your SVG to a React component
        exportType: "named",
        namedExport: "ReactComponent",
      },
    }),
  ],
server: {
  proxy: {
    "/api": {
      // Override when the backend runs elsewhere, e.g. VITE_API_URL=http://127.0.0.1:8001
      target: process.env.VITE_API_URL || "http://localhost:8000",
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ""), // strip /api prefix
    },
  },
},

});
