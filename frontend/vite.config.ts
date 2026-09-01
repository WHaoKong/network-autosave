import { readFileSync } from 'fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const packageJson = JSON.parse(
  readFileSync(resolve(__dirname, 'package.json'), 'utf-8'),
) as { version: string }
const appVersion = `v${packageJson.version}`
const buildTime = new Date().toISOString()
const backendTarget = process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:5000'
const forwardedProto = (() => {
  try {
    return new URL(backendTarget).protocol.replace(':', '') || 'http'
  } catch {
    return 'http'
  }
})()

const createProxyConfig = (withBypass = false) => ({
  target: backendTarget,
  changeOrigin: false,
  secure: false,
  xfwd: true,
  cookieDomainRewrite: false,
  cookiePathRewrite: false,
  configure: (proxy) => {
    proxy.on('proxyReq', (proxyReq, req) => {
      // Forward the current Host so local IP access works correctly.
      const host = req.headers.host || 'localhost:3001'
      proxyReq.setHeader('X-Forwarded-Host', host)
      proxyReq.setHeader('X-Forwarded-Proto', forwardedProto)
    })
  },
  ...(withBypass
    ? {
        bypass: (req) => {
          // Proxy form submissions only; let the frontend handle page routes.
          if (req.method !== 'POST') {
            return '/index.html'
          }
        },
      }
    : {}),
})

export default defineConfig({
  base: './',
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __BUILD_TIME__: JSON.stringify(buildTime),
  },
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ['vue', 'vue-router', 'pinia'],
      dts: true,
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0', // Allow access from the local network, including mobile devices.
    port: 3001,
    open: false,
    proxy: {
      '/api': {
        ...createProxyConfig(),
        ws: true,
      },
      '/login': createProxyConfig(true),
      '/logout': createProxyConfig(true),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus'],
        },
      },
    },
  },
})
