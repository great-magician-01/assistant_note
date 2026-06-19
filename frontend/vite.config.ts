import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'

const frontendRoot = fileURLToPath(new URL('./', import.meta.url))
const VDITOR_DIST = path.join(frontendRoot, 'node_modules/vditor/dist')
// Trailing separator so a same-prefix-but-different-dir path can't slip past
// the startsWith guard (e.g. node_modules/vditor/dist-foo).
const VDITOR_DIST_PREFIX = VDITOR_DIST + path.sep

// Vditor fetches its runtime assets (Lute engine, i18n, icons, CSS, fonts,
// emoji, on-demand libs like highlight/mermaid/katex) from `${cdn}/dist/...`
// at runtime — the default CDN is unpkg. For an offline-friendly production
// build we serve those files locally instead: in dev via a middleware that
// streams node_modules/vditor/dist, in build by copying the folder into the
// output dir. Nothing is written to the repo (no public/ pollution, no git
// churn). `cdn` is set to '/vditor', so requests look like
// /vditor/dist/js/lute/lute.min.js → node_modules/vditor/dist/js/lute/...
const MIME: Record<string, string> = {
  js: 'text/javascript; charset=utf-8',
  mjs: 'text/javascript; charset=utf-8',
  css: 'text/css; charset=utf-8',
  json: 'application/json; charset=utf-8',
  svg: 'image/svg+xml',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  woff: 'font/woff',
  woff2: 'font/woff2',
  ttf: 'font/ttf',
  wasm: 'application/wasm',
}

function vditorLocalAssets(): Plugin {
  return {
    name: 'vditor-local-assets',
    configureServer(server) {
      // Serve node_modules/vditor/dist at /vditor/dist in dev.
      server.middlewares.use('/vditor/dist', (req, res, next) => {
        // connect strips the mount prefix, so req.url is like
        // `/js/i18n/zh_CN.js`. Strip the leading slashes before resolving:
        // path.resolve treats a `/`-prefixed segment as drive-root on
        // Windows (→ D:\js\...), escaping VDITOR_DIST and 404-ing.
        const rel = decodeURIComponent((req.url ?? '').split('?')[0]).replace(/^\/+/, '')
        const file = path.resolve(VDITOR_DIST, rel)
        if (
          (file === VDITOR_DIST || file.startsWith(VDITOR_DIST_PREFIX)) &&
          fs.existsSync(file) &&
          fs.statSync(file).isFile()
        ) {
          res.setHeader('Content-Type', MIME[path.extname(file).slice(1).toLowerCase()] ?? 'application/octet-stream')
          // Dev-only: never let the browser cache these. Earlier, a broken
          // version of this middleware served index.html (200, text/html) for
          // .css/.js requests; browsers heuristically cached that bad response
          // and kept using it after the fix. no-store forces a fresh fetch.
          res.setHeader('Cache-Control', 'no-store')
          fs.createReadStream(file).pipe(res)
          return
        }
        next()
      })
    },
    writeBundle(options) {
      // Copy node_modules/vditor/dist → <outDir>/vditor/dist for the build.
      const outDir = options.dir
      if (!outDir) return
      const dest = path.join(outDir, 'vditor/dist')
      fs.cpSync(VDITOR_DIST, dest, { recursive: true })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss(), vditorLocalAssets()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 6580,
    // Fail loud if 6580 is taken instead of silently falling through to the
    // next free port (which is how a stray vite once grabbed 6581 — the
    // backend's IPv4-only port — and intercepted the /api proxy).
    strictPort: true,
    proxy: {
      // Forward API calls to the FastAPI backend during dev to avoid CORS.
      // Use 127.0.0.1 (IPv4) explicitly: the backend binds 0.0.0.0:6581 but
      // not [::1]:6581, and Windows resolves `localhost` to ::1, which would
      // miss the backend.
      '/api': {
        target: 'http://127.0.0.1:6581',
        changeOrigin: true,
      },
      // Uploaded images are served as public static files from the backend.
      '/uploads': {
        target: 'http://127.0.0.1:6581',
        changeOrigin: true,
      },
    },
  },
})
