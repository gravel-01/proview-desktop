import { existsSync, readFileSync } from 'fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

function readBackendEnvValue(key: string): string | undefined {
  const envPath = resolve(__dirname, '../backend/.env')
  if (!existsSync(envPath)) {
    return undefined
  }

  const lines = readFileSync(envPath, 'utf8').split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }
    const separatorIndex = trimmed.indexOf('=')
    if (separatorIndex === -1) {
      continue
    }
    const currentKey = trimmed.slice(0, separatorIndex).trim()
    if (currentKey !== key) {
      continue
    }
    const rawValue = trimmed.slice(separatorIndex + 1).trim()
    return rawValue.replace(/^['"]|['"]$/g, '')
  }

  return undefined
}

const backendPort = process.env.PROVIEW_API_PORT || readBackendEnvValue('PROVIEW_API_PORT') || '5000'
const backendTarget = process.env.VITE_DEV_API_TARGET || `http://localhost:${backendPort}`
const isDesktopBuild = process.env.PROVIEW_DESKTOP_BUILD === '1'

export default defineConfig(({ command }) => ({
  // serve: 使用绝对根路径，保证开发环境 HMR 与资源解析稳定。
  // build: 默认使用相对路径，避免桌面端 file:// 打开时 /assets 失效导致白屏。
  base: command === 'serve' ? '/' : './',
  plugins: [vue(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        landing: resolve(__dirname, 'index.html'),
        app: resolve(__dirname, 'app.html')
      }
    }
  },
  server: {
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true
      }
    }
  },
  define: {
    __PROVIEW_DESKTOP_BUILD__: JSON.stringify(isDesktopBuild)
  }
}))
