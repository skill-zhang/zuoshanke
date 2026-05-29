import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/wb-api': {
        target: 'http://localhost:8001',
        rewrite: (path) => path.replace(/^\/wb-api/, '/api'),
      },
      '/wb': {
        target: 'http://localhost:5174',
        rewrite: (path) => path.replace(/^\/wb/, ''),
      },
    },
    allowedHosts: true, // 允许 Cloudflare Tunnel 等任意域名访问
  },
})
