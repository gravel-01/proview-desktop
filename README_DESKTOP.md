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

## 本地运行时数据、备份与升级

桌面版的用户数据不放在安装目录里，而是放在 Electron 的用户数据目录下：

```text
<Electron userData>\backend-data
```

Windows 常见位置类似：

```text
%APPDATA%\ProView AI Interviewer\backend-data
```

实际路径以运行时配置页显示的 `.env` 和 `models.json` 路径为准。Electron 会把这个目录注入给后端：

- `PROVIEW_APP_DATA_DIR=<Electron userData>\backend-data`
- `PROVIEW_ENV_FILE=<Electron userData>\backend-data\.env`
- `PROVIEW_SQLITE_DB_PATH=data/interviews.db`
- `PROVIEW_CAREER_DB_PATH=data/career_planning.sqlite3`
- `PROVIEW_SESSION_TOKEN_DB_PATH=data/session_tokens.sqlite3`

建议备份整个 `backend-data` 目录。最小备份边界如下：

- `backend-data/.env`：固定运行时配置，例如 OCR、语音、端口和数据库路径。这里可能包含 OCR Token、百度语音密钥等敏感信息。
- `backend-data/models.json`：模型中心主存储，包含模型名称、Base URL、默认模型、旧配置导入摘要和模型 API Key。
- `backend-data/data/interviews.db`：面试历史、会话数据和主要本地业务数据。
- `backend-data/data/career_planning.sqlite3`：职业规划、任务和进度数据。当前桌面脚本会把它作为独立 SQLite 文件注入。
- `backend-data/data/session_tokens.sqlite3`：本机会话 token。备份它可以保留部分本地认证映射；如果你想让升级后重新建立会话，可以不恢复这个文件。

恢复或迁移到新机器时：

1. 先完全退出 ProView 桌面版。
2. 安装或解压新版本。
3. 将旧 `backend-data` 内容复制到新机器对应的 `<Electron userData>\backend-data`。
4. 启动应用，在运行时配置页确认 `.env`、`models.json` 和模型列表路径正常。

升级注意事项：

- 安装包升级不应该覆盖 `backend-data`，但升级前仍建议备份整个目录。
- 首次启动新版本时，SQLite schema 可能会自动迁移；迁移前保留一份冷备份更稳。
- 不承诺恢复正在进行中的 active session。升级或替换文件前，先结束当前面试、简历分析或职业规划操作。
- `models.json` 和 `.env` 当前仍是本机明文存储。不要提交、截图、发送或共享这些文件；生产使用时建议依赖系统账户权限、磁盘加密和后续密钥链 / 加密存储专项。

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
