import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 前端 dev server 走 5173；/api、/images 反代到 FastAPI（8000），
// 避免 CORS 与硬编码后端地址，前端一律用相对路径请求。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/images": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
