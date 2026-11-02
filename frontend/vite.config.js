import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'

function apiProxy() {
  return {
    target: apiTarget,
    changeOrigin: true,
    proxyTimeout: 360000,
    configure(proxy) {
      proxy.on('error', (_error, _request, response) => {
        if (response && typeof response.writeHead === 'function' && !response.headersSent && !response.writableEnded) {
          response.writeHead(503, {'Content-Type': 'application/json; charset=utf-8'})
          response.end(JSON.stringify({detail:'Не удалось связаться с сервисом. Повторите загрузку через несколько секунд.'}))
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': apiProxy() },
  },
  preview: {
    proxy: { '/api': apiProxy() },
  },
})
