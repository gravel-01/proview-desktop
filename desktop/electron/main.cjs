const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')
const { spawn } = require('node:child_process')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')

app.disableHardwareAcceleration()
app.commandLine.appendSwitch('disable-gpu')
app.commandLine.appendSwitch('disable-gpu-compositing')

const API_HOST = '127.0.0.1'
const API_PORT = Number.parseInt(process.env.PROVIEW_API_PORT || '18765', 10)
const API_BASE_URL = `http://${API_HOST}:${API_PORT}`
const BOOTSTRAP_LOG_PATH = path.join(os.tmpdir(), 'proview-desktop-bootstrap.log')

let backendProcess = null
let mainWindow = null
let splashWindow = null
let isQuitting = false
let isRecoveringWindow = false
let mainWindowStartupPromise = null
let mainWindowRecoveryPromise = null
let splashStatus = {
  message: 'AI 面试官正在启动中...',
  stage: '正在唤醒本地面试引擎',
}

app.setAppUserModelId('com.proview.desktop')

const hasSingleInstanceLock = app.requestSingleInstanceLock()
if (!hasSingleInstanceLock) {
  app.quit()
}

function logBootstrap(message) {
  try {
    fs.appendFileSync(BOOTSTRAP_LOG_PATH, `[${new Date().toISOString()}] ${message}\n`)
  } catch {
    // Ignore bootstrap log failures.
  }
}

function stringifyError(error) {
  if (!error) {
    return 'Unknown error'
  }
  if (error.stack) {
    return String(error.stack)
  }
  if (error.message) {
    return String(error.message)
  }
  return String(error)
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

function focusWindow(window) {
  if (!window || window.isDestroyed()) {
    return
  }

  if (window.isMinimized()) {
    window.restore()
  }
  if (!window.isVisible()) {
    window.show()
  }
  window.focus()
}

function getBackendSpawnConfig() {
  if (!app.isPackaged) {
    return {
      command: process.env.PROVIEW_DESKTOP_PYTHON || 'python',
      args: [path.join(__dirname, '..', '..', 'backend', 'app.py')],
      cwd: path.join(__dirname, '..', '..', 'backend'),
    }
  }

  const backendDir = path.join(process.resourcesPath, 'backend', 'proview-backend')
  const backendExecutable = process.platform === 'win32' ? 'proview-backend.exe' : 'proview-backend'

  return {
    command: path.join(backendDir, backendExecutable),
    args: [],
    cwd: backendDir,
  }
}

function resolveResumePath(filePath) {
  const normalizedPath = typeof filePath === 'string' ? filePath.trim() : ''
  if (!normalizedPath) {
    throw new Error('未提供可操作的文件路径。')
  }

  const resolvedPath = path.resolve(normalizedPath)
  if (!fs.existsSync(resolvedPath)) {
    throw new Error(`文件不存在：${resolvedPath}`)
  }

  return resolvedPath
}

function registerDesktopFileHandlers() {
  ipcMain.handle('proview:locate-file', async (_event, filePath) => {
    try {
      const resolvedPath = resolveResumePath(filePath)
      shell.showItemInFolder(resolvedPath)
      return { ok: true, path: resolvedPath }
    } catch (error) {
      return {
        ok: false,
        error: String(error && error.message ? error.message : error),
      }
    }
  })

  ipcMain.handle('proview:open-file', async (_event, filePath) => {
    try {
      const resolvedPath = resolveResumePath(filePath)
      const errorMessage = await shell.openPath(resolvedPath)
      if (errorMessage) {
        throw new Error(errorMessage)
      }
      return { ok: true, path: resolvedPath }
    } catch (error) {
      return {
        ok: false,
        error: String(error && error.message ? error.message : error),
      }
    }
  })
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
  const env = {
    ...process.env,
    PROVIEW_API_HOST: API_HOST,
    PROVIEW_API_PORT: String(API_PORT),
    PROVIEW_DESKTOP_MODE: '1',
    PYTHONIOENCODING: process.env.PYTHONIOENCODING || 'utf-8',
    PYTHONUTF8: process.env.PYTHONUTF8 || '1',
    PROVIEW_APP_DATA_DIR: backendDataDir,
    PROVIEW_ENV_FILE: runtimeEnvFilePath,
    PROVIEW_SQLITE_DB_PATH: 'data/interviews.db',
    PROVIEW_CAREER_DB_PATH: 'data/career_planning.sqlite3',
    PROVIEW_SESSION_TOKEN_DB_PATH: 'data/session_tokens.sqlite3',
  }

  if (process.env.PROVIEW_PLAYWRIGHT_CHANNEL) {
    env.PROVIEW_PLAYWRIGHT_CHANNEL = process.env.PROVIEW_PLAYWRIGHT_CHANNEL
  } else if (process.platform === 'win32') {
    env.PROVIEW_PLAYWRIGHT_CHANNEL = 'msedge'
  }

  if (process.env.PLAYWRIGHT_BROWSERS_PATH) {
    env.PLAYWRIGHT_BROWSERS_PATH = process.env.PLAYWRIGHT_BROWSERS_PATH
  } else if (app.isPackaged && process.platform === 'darwin') {
    env.PLAYWRIGHT_BROWSERS_PATH = '0'
  }

  return env
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
    width: 760,
    height: 540,
    minWidth: 760,
    minHeight: 540,
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
    logBootstrap('Splash window closed.')
    if (splashWindow === window) {
      splashWindow = null
    }
  })
  window.webContents.on('render-process-gone', (_event, details) => {
    logBootstrap(`Splash renderer process gone: reason=${details.reason} exitCode=${details.exitCode}`)
  })
  window.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    logBootstrap(`Splash console[level=${level}] ${sourceId}:${line} ${message}`)
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

  window.on('unresponsive', () => {
    logBootstrap('Main window became unresponsive.')
    if (mainWindow === window) {
      void recoverMainWindow('渲染进程无响应')
    }
  })
  window.on('closed', () => {
    logBootstrap('Main window closed.')
  })
  window.webContents.on('preload-error', (_event, preloadPath, error) => {
    logBootstrap(`Preload error at ${preloadPath}: ${stringifyError(error)}`)
  })
  window.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    logBootstrap(`Renderer console[level=${level}] ${sourceId}:${line} ${message}`)
  })
  window.webContents.on('render-process-gone', (_event, details) => {
    logBootstrap(`Renderer process gone: reason=${details.reason} exitCode=${details.exitCode}`)
    if (mainWindow === window) {
      void recoverMainWindow(`渲染进程已退出（${details.reason}）`)
    }
  })
  window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame || errorCode === -3) {
      return
    }
    logBootstrap(`Renderer load failed: code=${errorCode} description=${errorDescription} url=${validatedURL}`)
    if (mainWindow === window) {
      void recoverMainWindow(`主界面加载失败（${errorCode}: ${errorDescription}）`)
    }
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
    focusWindow(mainWindow)
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
    focusWindow(window)
  }

  await closeSplashWindow()
  return window
}

function ensureMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    focusWindow(mainWindow)
    return Promise.resolve(mainWindow)
  }

  if (mainWindowStartupPromise) {
    return mainWindowStartupPromise
  }

  mainWindowStartupPromise = (async () => {
    try {
      return await createMainWindow()
    } finally {
      mainWindowStartupPromise = null
    }
  })()

  return mainWindowStartupPromise
}

function recoverMainWindow(reason) {
  if (isQuitting) {
    return Promise.resolve(null)
  }

  if (mainWindowRecoveryPromise) {
    return mainWindowRecoveryPromise
  }

  logBootstrap(`Recovering main window: ${reason}`)
  mainWindowRecoveryPromise = (async () => {
    try {
      isRecoveringWindow = true
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.destroy()
      }
      mainWindow = null
      mainWindowStartupPromise = null
      return await ensureMainWindow()
    } catch (error) {
      await reportStartupFailure(new Error(`主界面恢复失败：${String(error && error.message ? error.message : error)}`))
      return null
    } finally {
      isRecoveringWindow = false
      mainWindowRecoveryPromise = null
    }
  })()

  return mainWindowRecoveryPromise
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
  logBootstrap('App before-quit.')
  isQuitting = true
  stopBackend()
})

process.on('uncaughtException', (error) => {
  logBootstrap(`Uncaught exception: ${stringifyError(error)}`)
})

process.on('unhandledRejection', (reason) => {
  logBootstrap(`Unhandled rejection: ${stringifyError(reason)}`)
})

app.on('child-process-gone', (_event, details) => {
  logBootstrap(`Child process gone: type=${details.type} reason=${details.reason} exitCode=${details.exitCode} name=${details.name}`)
})

app.on('second-instance', async (_event, commandLine, workingDirectory) => {
  logBootstrap(`Second instance detected. cwd=${workingDirectory} argv=${JSON.stringify(commandLine)}`)
  try {
    await app.whenReady()
    await ensureMainWindow()
  } catch (error) {
    logBootstrap(`Failed to focus existing window for second instance: ${String(error && error.message ? error.message : error)}`)
  }
})

app.whenReady().then(async () => {
  try {
    logBootstrap(`App ready. isPackaged=${app.isPackaged} resourcesPath=${process.resourcesPath}`)
    logBootstrap(`Runtime: electron=${process.versions.electron} chrome=${process.versions.chrome} node=${process.versions.node} platform=${process.platform} arch=${process.arch}`)
    registerDesktopFileHandlers()
    await ensureMainWindow()
  } catch (error) {
    await reportStartupFailure(error, true)
  }
})

app.on('window-all-closed', () => {
  if (isRecoveringWindow) {
    return
  }
  stopBackend()
  if (process.platform !== 'darwin' || isQuitting) {
    app.quit()
  }
})

app.on('activate', async () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    focusWindow(mainWindow)
    return
  }

  try {
    await ensureMainWindow()
  } catch (error) {
    await reportStartupFailure(error)
  }
})
