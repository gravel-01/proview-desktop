# README Desktop

这份文档面向只想开发桌面版的人。

如果你的目标是：

- 调试 Electron 壳
- 验证桌面端启动本地后端
- 验证桌面端文件操作能力
- 调试桌面专用运行时配置
- 打 Windows 安装包或 portable 包

就看这份文档。

## 你会运行什么

```text
Electron
  -> 启动本地 backend/app.py
  -> 检查 /api/health
  -> 加载 frontend/dist/app.html
```

重点：

- 桌面开发不是连 Vite dev server
- Electron 在未打包模式下会直接启动仓库里的 `backend/app.py`
- Electron 加载的是 `frontend/dist/app.html`

这意味着桌面开发前，必须先构建前端静态文件。

## 前置环境

- Python 3
- Node.js + npm
- Windows 开发环境

先安装依赖：

```powershell
cd backend
python -m pip install -r requirements.txt

cd ..\desktop
npm install
```

桌面前端构建脚本会在需要时自动安装 `frontend` 依赖，所以你不一定要先手动进 `frontend/` 执行 `npm install`。

## 桌面运行时配置

未打包开发模式下：

- Electron 会优先读取 `backend/.env`
- 首次运行时会把配置复制到桌面运行目录的 `backend-data/.env`

桌面模式会额外注入这些运行时变量：

- `PROVIEW_DESKTOP_MODE=1`
- `PROVIEW_API_HOST=127.0.0.1`
- `PROVIEW_API_PORT=18765`（默认）
- `PROVIEW_APP_DATA_DIR=<Electron 用户目录下的 backend-data>`

如果你想指定 Python 解释器：

```powershell
$env:PROVIEW_DESKTOP_PYTHON = "D:\path\to\python.exe"
```

如果你想改桌面后端端口：

```powershell
$env:PROVIEW_API_PORT = "18765"
```

## 启动步骤

### 1. 构建桌面要用的前端资源

```powershell
cd desktop
npm run build:frontend
```

这个脚本会：

- 自动检查并安装 `frontend` 依赖
- 设置 `PROVIEW_DESKTOP_BUILD=1`
- 默认把桌面 API 地址指向 `http://127.0.0.1:18765`
- 执行 `frontend` 的生产构建

### 2. 启动 Electron

```powershell
cd desktop
npx electron .
```

启动后 Electron 会：

1. 显示启动页
2. 拉起本地 `backend/app.py`
3. 轮询 `http://127.0.0.1:18765/api/health`
4. 健康检查通过后加载 `frontend/dist/app.html`

## 桌面开发循环

### 改了前端页面

桌面版不会热更新 Vite 页面。改完前端后要重新构建：

```powershell
cd desktop
npm run build:frontend
```

然后重启 Electron。

### 改了后端 Python 代码

直接重启 Electron 即可，它会重新启动本地 `backend/app.py`。

### 改了 Electron 主进程代码

直接重启 Electron。

## 常见目录

开发时你最常接触的是：

- `desktop/electron/main.cjs`：桌面启动入口
- `desktop/electron/preload.cjs`：预加载桥接
- `desktop/scripts/build-frontend.ps1`：桌面前端构建
- `desktop/scripts/build-backend.ps1`：桌面后端打包
- `frontend/dist/`：桌面实际加载的前端产物

## 打包桌面版

### 快速打包

```powershell
cd desktop
npm run dist
```

这会：

- 构建桌面前端
- 打包 Python 后端
- 生成 Windows 安装包和 portable 包

输出目录：

- `desktop/release/`

### 只生成目录包

```powershell
cd desktop
npm run pack
```

### 推荐的仓库根目录入口

如果你要做更完整的本地打包流程，优先用：

```powershell
.\package-desktop.ps1
```

这个脚本比 `desktop/package.json` 里的命令多做了这些事：

- 环境检查
- Conda 环境切换
- 前后端构建顺序控制
- 脱敏 `.env` 校验
- 打包日志归档
- 产物检查

### macOS Apple Silicon 打包

Mac 版必须在 macOS 上构建，尤其是后端 PyInstaller 产物不能从 Windows 交叉生成。M 系列芯片请在原生 arm64 终端运行，不要通过 Rosetta 启动终端。

在 M 系列 Mac 上准备依赖后运行：

```bash
python3 -m pip install -r backend/requirements.txt
npm install --prefix desktop
bash ./package-desktop-mac.sh
```

这个脚本会：

- 构建桌面前端
- 打包 macOS arm64 后端
- 下载并打包 Playwright Chromium，避免 Mac 版默认依赖 Windows Edge
- 生成 macOS `.dmg` 和 `.zip`

输出目录：

- `desktop/release/`

Mac 产物命名格式：

```text
ProView AI Interviewer-Mac-1.0.0-arm64.dmg
ProView AI Interviewer-Mac-1.0.0-arm64.zip
```

如果没有 Apple Developer 签名和公证，macOS 首次打开时可能需要在系统设置里允许运行，或右键选择打开。

## 桌面开发常见问题

### 启动后白屏或提示找不到资源

先确认你已经执行过：

```powershell
cd desktop
npm run build:frontend
```

### Electron 起不来后端

优先检查：

- 当前终端的 `python` 是否能运行 `backend/app.py`
- 是否需要设置 `PROVIEW_DESKTOP_PYTHON`
- `backend` 依赖是否装全

### OCR / PDF / 语音在桌面端不可用

这通常不是 Electron 问题，而是运行时配置没有填：

- `PADDLEOCR_API_URL`
- `PADDLE_OCR_TOKEN`
- 模型 API key
- 百度语音配置

## 什么时候不要用这份文档

如果你只是想开发 Vue 页面、Flask API、前后端联调，而不关心 Electron 和打包，请看 [README_WEB.md](README_WEB.md)。
