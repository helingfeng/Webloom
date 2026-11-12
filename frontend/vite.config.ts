import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
      '/mcp': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 仅代理 MCP 协议请求；浏览器导航（Accept: text/html）走前端路由
        bypass(req) {
          const accept = req.headers.accept || ''
          if (accept.includes('application/json') || accept.includes('text/event-stream')) {
            return undefined
          }
          return req.url
        },
      },
      '/open': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/storage': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
