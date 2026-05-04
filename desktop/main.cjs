const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('node:child_process')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')

const API_HOST = '127.0.0.1'
const API_PORT = Number.parseInt(process.env.PROVIEW_API_PORT || '18765', 10)
const API_BASE_URL = `http://${API_HOST}:${API_PORT}`
const BOOTSTRAP_LOG_PATH = path.join(os.tmpdir(), 'proview-desktop-bootstrap.log')

let backendProcess = null
let mainWindow = null
let splashWindow = null
let isQuitting = false
let splashStatus = {
  message: 'AI 面试官正在启动中...',
  stage: '正在唤醒本地面试引擎',
}

app.setAppUserModelId('com.proview.desktop')

function logBootstrap(message) {
  try {
    fs.appendFileSync(BOOTSTRAP_LOG_PATH, `[${new Date().toISOString()}] ${message}\n`)
  } catch {
    // Ignore bootstrap log failures.
  }
}

function appendBackendLog(chunk) {
  try {
    const logDir = path.join(app.getPath('userData'), 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    fs.appendFileSync(path.join(logDir, 'backend.log'), chunk)
  } catch {
    // Ignore log write failures.
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function getBackendSpawnConfig() {
  if (!app.isPackaged) {
    return {
      command: process.env.PROVIEW_DESKTOP_PYTHON || 'python',
      args: [path.join(__dirname, '..', '..', 'backend', 'app.py')],
      cwd: path.join(__dirname, '..', '..', 'backend'),
    }
  }

  return {
    command: path.join(process.resourcesPath, 'backend', 'proview-backend', 'proview-backend.exe'),
    args: [],
    cwd: path.join(process.resourcesPath, 'backend', 'proview-backend'),
  }
}

function ensureRuntimeEnvFile() {
  const backendDataDir = path.join(app.getPath('userData'), 'backend-data')
  const envFilePath = path.join(backendDataDir, '.env')
  fs.mkdirSync(backendDataDir, { recursive: true })

  if (fs.existsSync(envFilePath)) {
    return envFilePath
  }

  const candidatePaths = app.isPackaged
    ? [
        path.join(process.resourcesPath, 'backend', 'proview-backend', '_internal', '.env'),
        path.join(process.resourcesPath, 'backend', 'proview-backend', '.env'),
      ]
    : [
        path.join(__dirname, '..', '..', 'backend', '.env'),
        path.join(__dirname, '..', 'backend', '.env'),
        path.join(__dirname, '..', '..', 'backend', '.env.example'),
        path.join(__dirname, '..', 'backend', '.env.example'),
      ]

  for (const candidate of candidatePaths) {
    if (!fs.existsSync(candidate)) {
      continue
    }
    fs.copyFileSync(candidate, envFilePath)
    return envFilePath
  }

  fs.writeFileSync(envFilePath, '', 'utf8')
  return envFilePath
}

function buildBackendEnv() {
  const backendDataDir = path.join(app.getPath('userData'), 'backend-data')
  const runtimeEnvFilePath = ensureRuntimeEnvFile()
  return {
    ...process.env,
    PROVIEW_API_HOST: API_HOST,
    PROVIEW_API_PORT: String(API_PORT),
    PROVIEW_DESKTOP_MODE: '1',
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || 'utf-8',
    PYTHONUTF8: process.env.PYTHONUTF8 || '1',
    PROVIEW_PLAYWRIGHT_CHANNEL: process.env.PROVIEW_PLAYWRIGHT_CHANNEL || 'msedge',
    PROVIEW_APP_DATA_DIR: backendDataDir,
    PROVIEW_ENV_FILE: runtimeEnvFilePath,
    PROVIEW_SQLITE_DB_PATH: 'data/interviews.db',
    PROVIEW_CAREER_DB_PATH: 'data/career_planning.sqlite3',
    PROVIEW_SESSION_TOKEN_DB_PATH: 'data/session_tokens.sqlite3',
  }
}

function startBackend() {
  if (backendProcess) {
    return
  }

  const spawnConfig = getBackendSpawnConfig()
  logBootstrap(`Starting backend from ${spawnConfig.command}`)
  backendProcess = spawn(spawnConfig.command, spawnConfig.args, {
    cwd: spawnConfig.cwd,
    env: buildBackendEnv(),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })

  backendProcess.on('error', (error) => {
    logBootstrap(`Backend spawn error: ${error.message}`)
  })
  backendProcess.stdout?.on('data', (chunk) => {
    appendBackendLog(chunk)
    logBootstrap(`backend stdout: ${String(chunk).trim()}`)
  })
  backendProcess.stderr?.on('data', (chunk) => {
    appendBackendLog(chunk)
    logBootstrap(`backend stderr: ${String(chunk).trim()}`)
  })
  backendProcess.on('exit', (code, signal) => {
    logBootstrap(`Backend exited with code=${code} signal=${signal}`)
    backendProcess = null
  })
}

function requestHealth() {
  return new Promise((resolve, reject) => {
    const request = http.get(`${API_BASE_URL}/api/health`, (response) => {
      if (response.statusCode === 200) {
        response.resume()
        resolve()
        return
      }

      response.resume()
      reject(new Error(`HTTP ${response.statusCode}`))
    })

    request.setTimeout(5000, () => {
      request.destroy(new Error('Health check timeout'))
    })
    request.on('error', reject)
  })
}

async function waitForBackend(timeoutMs = 30000, onRetry) {
  const startedAt = Date.now()
  let lastError = null

  while (Date.now() - startedAt < timeoutMs) {
    try {
      await requestHealth()
      logBootstrap('Backend health check passed.')
      return
    } catch (error) {
      lastError = error
      logBootstrap(`Backend health check failed: ${error.message}`)
      onRetry?.({
        elapsedMs: Date.now() - startedAt,
        error,
      })
    }

    if (!backendProcess) {
      throw lastError || new Error('Backend process exited before becoming ready.')
    }

    await delay(1000)
  }

  throw lastError || new Error('Backend did not become ready in time.')
}

function stopBackend() {
  if (!backendProcess) {
    return
  }

  const pid = backendProcess.pid
  backendProcess.removeAllListeners()
  backendProcess = null

  if (!pid) {
    return
  }

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true })
    return
  }

  try {
    process.kill(pid, 'SIGTERM')
  } catch {
    // Ignore missing process errors.
  }
}

function updateSplashStatus(message, stage) {
  splashStatus = {
    message: message || splashStatus.message,
    stage: stage || splashStatus.stage,
  }

  if (!splashWindow || splashWindow.isDestroyed()) {
    return
  }

  const script = `
    window.__PROVIEW_SPLASH_UPDATE?.({
      message: ${JSON.stringify(splashStatus.message)},
      stage: ${JSON.stringify(splashStatus.stage)},
      freeze: true
    })
  `

  splashWindow.webContents.executeJavaScript(script).catch(() => {
    // Ignore splash update failures.
  })
}

async function createSplashWindow() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    return splashWindow
  }

  const window = new BrowserWindow({
    width: 680,
    height: 460,
    minWidth: 680,
    minHeight: 460,
    show: false,
    frame: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    autoHideMenuBar: true,
    backgroundColor: '#05050A',
    skipTaskbar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  })

  splashWindow = window
  window.on('closed', () => {
    if (splashWindow === window) {
      splashWindow = null
    }
  })
  window.once('ready-to-show', () => {
    if (!window.isDestroyed()) {
      window.show()
    }
  })
  window.webContents.on('did-finish-load', () => {
    updateSplashStatus(splashStatus.message, splashStatus.stage)
  })

  const splashHtmlPath = path.join(__dirname, 'splash.html')
  logBootstrap(`Loading splash from ${splashHtmlPath}`)
  if (!fs.existsSync(splashHtmlPath)) {
    throw new Error(`Splash screen not found: ${splashHtmlPath}`)
  }

  await window.loadFile(splashHtmlPath)
  return window
}

async function closeSplashWindow() {
  if (!splashWindow || splashWindow.isDestroyed()) {
    return
  }

  const window = splashWindow
  splashWindow = null

  if (!window.isDestroyed()) {
    window.close()
    await delay(60)
  }
}

function getAppHtmlPath() {
  return app.isPackaged
    ? path.join(__dirname, '..', 'frontend', 'dist', 'app.html')
    : path.join(__dirname, '..', '..', 'frontend', 'dist', 'app.html')
}

async function createAppWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1200,
    minHeight: 760,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  const appHtmlPath = getAppHtmlPath()
  logBootstrap(`Loading renderer from ${appHtmlPath}`)
  if (!fs.existsSync(appHtmlPath)) {
    throw new Error(`Frontend bundle not found: ${appHtmlPath}`)
  }

  const readyToShow = new Promise((resolve) => {
    window.once('ready-to-show', resolve)
  })

  await window.loadFile(appHtmlPath)
  await readyToShow
  return window
}

async function createMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return mainWindow
  }

  await createSplashWindow()
  updateSplashStatus('AI 面试官正在启动中...', '正在唤醒本地面试引擎')

  startBackend()
  await waitForBackend(30000, ({ elapsedMs }) => {
    const elapsedSeconds = Math.max(1, Math.ceil(elapsedMs / 1000))
    updateSplashStatus('AI 面试官正在启动中...', `正在连接本地服务... ${elapsedSeconds}s`)
  })

  updateSplashStatus('AI 面试官即将就绪...', '正在装载主界面')
  const window = await createAppWindow()
  mainWindow = window

  window.on('closed', () => {
    if (mainWindow === window) {
      mainWindow = null
    }
  })

  if (!window.isDestroyed()) {
    window.show()
    window.focus()
  }

  await closeSplashWindow()
  return window
}

async function reportStartupFailure(error, shouldQuit = false) {
  const message = String(error && error.message ? error.message : error)
  logBootstrap(`App startup failed: ${message}`)
  await closeSplashWindow()
  dialog.showErrorBox('ProView AI Interviewer 启动失败', message)

  if (shouldQuit) {
    app.quit()
  }
}

app.on('before-quit', () => {
  isQuitting = true
  stopBackend()
})

app.whenReady().then(async () => {
  try {
    logBootstrap(`App ready. isPackaged=${app.isPackaged} resourcesPath=${process.resourcesPath}`)
    await createMainWindow()
  } catch (error) {
    await reportStartupFailure(error, true)
  }
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin' || isQuitting) {
    app.quit()
  }
})

app.on('activate', async () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return
  }

  try {
    await createMainWindow()
  } catch (error) {
    await reportStartupFailure(error)
  }
})
