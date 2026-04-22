<div align="center">

# 🎯 ProView AI Interviewer

**用 AI 重新定义面试准备，模拟、分析、提升，一站式搞定**

[![License](https://img.shields.io/badge/License-Non--Commercial%20Reference-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)](backend/requirements.txt)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](frontend/package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](frontend/package.json)
[![Flask](https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white)](backend/requirements.txt)
[![Electron](https://img.shields.io/badge/Electron-37-47848F?logo=electron&logoColor=white)](desktop/package.json)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Storage-336791?logo=postgresql&logoColor=white)](backend/.env.example)

[快速开始](#quick-start) · [功能特性](#features) · [技术架构](#architecture) · [部署指南](#deployment) · [API 配置指南](#api-config) · [界面预览](#preview) · [文档](#docs)

</div>

> 单机桌面测试版已经发布，可直接下载体验：[GitHub Release v0.1.0-alpha.1](https://github.com/gravel-01/proview-desktop/releases/tag/v0.1.0-alpha.1)
>
> 首次使用时，请先在应用内填写你自己的模型、OCR 和语音服务密钥。

---

<a id="project-intro"></a>

## 📖 项目简介

ProView AI Interviewer 是一个面向求职训练场景的 **本地优先 AI 面试平台**。上传简历，选择岗位方向并完成运行时配置后，即可体验 AI 驱动的实时模拟面试、评估报告、简历优化与职业规划能力。

项目由同一套 `Vue 3 + TypeScript` 前端、同一套 `Flask` 后端，以及一个将两者封装为桌面应用的 `Electron` 壳层组成，既适合本地开发联调，也适合直接打包成 Windows 桌面应用。

无需依赖托管式 SaaS 后台，核心流程即可在本地跑通；模型、OCR 和语音能力使用你自己的服务密钥即可接入。

> 💡 **适合谁？** 正在准备校招、社招或岗位转型面试的开发者、产品、运营，以及想把面试训练、简历处理和职业规划放在同一套本地工作流里的使用者。

---

<a id="features"></a>

## ✨ 功能特性

### 🎙️ AI 模拟面试

- **多场景适配**：支持多种岗位方向、面试场景与音色配置
- **实时语音交互**：语音输入可同步转文字并进行纠错，完整保留面试过程
- **评估报告生成**：面试结束后自动输出总结报告与历史记录，方便复盘
- **本地双模式运行**：同一套业务逻辑既可跑 Web，也可封装为桌面应用

### 📄 简历智能处理

- **多格式上传**：支持 PDF、Word、图片等多种简历文件
- **OCR 解析**：可结合 PaddleOCR 对上传简历做识别与结构化处理
- **优化建议**：提供简历优化问卷和针对性优化建议
- **本地管理**：已上传简历可在“我的简历”中统一管理

### 🧱 简历生成与优化工作台

- **多模板生成**：内置多种简历模板，可直接进入工作台编辑
- **在线优化**：支持 AI 优化、模块化编辑与导出
- **集中输出**：把简历生成、优化和输出放在同一工作流内完成

### 🗺️ 职业发展规划

- **成长概览**：支持围绕目标方向整理长期成长建议
- **路线图与任务板**：提供概览、路线图、任务面板与文档面板
- **知识沉淀**：将面试训练与职业规划资料放在同一工作台内
- **持续完善中**：职业规划模块仍在持续迭代

### 💻 本地优先与开发友好

- **统一代码栈**：Web 与桌面版共用同一套业务前后端，避免双份维护
- **运行时配置页**：模型、OCR、语音等密钥可直接在应用内保存
- **多存储兼容**：支持 PostgreSQL、Supabase HTTP 兼容模式，或回退到 SQLite
- **桌面打包链路**：支持 `package-desktop.ps1`、PyInstaller 与 `electron-builder`

---

<a id="quick-start"></a>

## 🚀 快速开始

> ⚡ Web 模式 3 步即可跑通；桌面调试与 Windows 打包见下方部署指南。

### 前置环境

- Python 3
- Node.js + npm
- Windows 开发环境（桌面版）
- Windows / macOS / Linux（仅 Web 开发）

### Step 1：安装依赖

安装后端依赖：

```powershell
cd backend
python -m pip install -r requirements.txt
```

如果你需要 PDF 导出功能，建议额外安装 Playwright 浏览器内核：

```powershell
cd backend
python -m playwright install chromium
```

如果你更想复用系统中的 Edge：

```powershell
$env:PROVIEW_PLAYWRIGHT_CHANNEL = "msedge"
```

安装前端依赖：

```powershell
cd frontend
npm install
```

安装桌面壳依赖（如果你后面要调试或打包桌面版）：

```powershell
cd desktop
npm install
```

### Step 2：准备运行时配置

复制示例配置文件：

```powershell
cd backend
Copy-Item .env.example .env
```

`backend/.env.example` 中已经给出了完整示例。常见配置可以先从下面这组开始：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

ERNIE_API_KEY=
ERNIE_BASE_URL=https://aistudio.baidu.com/llm/lmapi/v3

PADDLEOCR_API_URL=
PADDLE_OCR_TOKEN=

BAIDU_APP_KEY=
BAIDU_SECRET_KEY=

BACKEND_DB_URL=postgresql://postgres:postgres@127.0.0.1:5432/proview_local
# 如果你不使用 PostgreSQL，也可以留空上面这一项，再启用 SQLite 单文件模式：
# PROVIEW_SQLITE_DB_PATH=../database/interviews.db
```

补充说明：

- 后端优先读取 `BACKEND_DB_URL / DATABASE_URL / SUPABASE_DB_URL`
- 如果这些都没有，会自动回退到 SQLite fallback
- 不填写模型、OCR、语音相关配置时，对应功能不可用，但项目仍可启动
- Web 本地开发通常使用 `backend/.env`
- 桌面版运行时会把配置写入 Electron 用户数据目录中的 `backend-data/.env`

### Step 3：启动项目

启动后端：

```powershell
cd backend
python app.py
```

再启动前端开发服务器：

```powershell
cd frontend
npm run dev
```

常用访问地址：

- 落地页：`http://localhost:5173/`
- 业务应用：`http://localhost:5173/app.html`
- 运行时配置页：`http://localhost:5173/app.html#/config`

Web 模式补充说明：

- 业务应用入口不是根路由，而是 `app.html`
- 前端使用 `hash router`，页面地址形如 `app.html#/interview`
- Vite 会把 `/api` 请求代理到 Flask
- 代理目标默认读取 `PROVIEW_API_PORT`，未配置时回退到 `5000`

---

<a id="deployment"></a>

## 🌐 部署指南

### 桌面调试模式

桌面版不会直接连 Vite dev server，而是加载 `frontend/dist/app.html`，所以启动前必须先构建前端资源：

```powershell
cd desktop
npm run build:frontend
```

然后启动 Electron：

```powershell
cd desktop
npx electron .
```

桌面模式会自动：

- 启动本地 `backend/app.py`
- 默认使用 `127.0.0.1:18765`
- 检查 `/api/health`
- 健康检查通过后加载 `frontend/dist/app.html`

如果你想指定 Python 解释器：

```powershell
$env:PROVIEW_DESKTOP_PYTHON = "D:\\path\\to\\python.exe"
```

### Windows 桌面打包

推荐使用仓库根目录脚本：

```powershell
.\package-desktop.ps1
```

如果你只想直接调用 `desktop/` 下的脚本：

```powershell
cd desktop
npm run dist
```

补充说明：

- `package-desktop.ps1` 会额外做环境检查、前后端构建、脱敏 `.env` 校验、日志归档和产物检查
- `npm run dist` 会在 `desktop/release/` 生成 Windows 安装包和 portable 包

---

<a id="preview"></a>

## 🖼️ 界面预览

![面试配置界面](img/fa674dc496310c55a107fa5ab104938.png)

![评估报告界面](img/cc8ee88dbf82050a13d88268752e583.png)

![简历生成工作台](img/83192b99831554bba147f0ede46f79b.png)

---

<a id="api-config"></a>

## 🔑 API 配置指南

### 如何进入配置页

如果你是第一次本地启动项目，可以先按下面方式分别启动后端与前端。

启动后端：

```powershell
cd backend
python app.py
```

出现类似输出时，说明后端已正常启动：

![后端启动成功示例](img/Pasted%20image%2020260415022055.png)

启动前端：

```powershell
cd frontend
npm install
npm run build
npm run dev
```

其中 `npm install` 通常只在首次初始化时需要。

出现类似输出时，说明前端已正常启动：

![前端启动成功示例](img/Pasted%20image%2020260415022840.png)

然后访问 `http://localhost:5173/` 即可进入 Web 页面。

### 在哪里填写密钥

进入页面右上角的应用设置后，即可填写运行所需密钥：

![应用设置入口](img/a34a74a26bdc69786975818666062ea.png)

![应用设置面板](img/92477119f37d0c60e745d545b6f0add.png)

![密钥填写界面](img/3254ba8d88e69408c205b660fca4ab6.png)

### 常用配置项对照

| 配置项 | 用途 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` | DeepSeek 模型调用 | 默认网关为 `https://api.deepseek.com/v1` |
| `ERNIE_API_KEY` / `ERNIE_BASE_URL` | 百度文心模型调用 | 默认网关为 `https://aistudio.baidu.com/llm/lmapi/v3` |
| `PADDLEOCR_API_URL` / `PADDLE_OCR_TOKEN` | OCR 服务 | 上传简历解析时使用 |
| `BAIDU_APP_KEY` / `BAIDU_SECRET_KEY` | 百度语音识别 / 合成 | 语音面试时使用 |
| `BACKEND_DB_URL` | 推荐数据库接入方式 | 本地 PostgreSQL / Supabase Postgres 都可走直连 |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase HTTP 兼容模式 | 作为兼容模式保留 |
| `PROVIEW_SQLITE_DB_PATH` | SQLite fallback | 单文件本地开发可用 |
| `PROVIEW_API_PORT` | Web 开发端口 | 默认值为 `5000` |

补充说明：

- 如果 `PADDLEOCR_API_URL` 指向本机或局域网 OCR 服务，VPN 全局模式可能导致 PaddleOCR 无法连接
- 遇到 OCR 请求失败时，优先检查代理设置和本地网络连通性

### 密钥获取与填写说明

DeepSeek 的 API URL 和 Token 需要到官方平台购买。若你只是先体验项目能力，也可以优先使用百度提供的文心一言、PaddleOCR 和语音服务接口，每日免费额度通常足够完成多次面试练习。

#### 文心一言大模型 API 获取方式

登录 [百度星河社区](https://aistudio.baidu.com/overview) 并完成实名认证：

![百度星河社区首页](img/b35fb4a1d85ddd0c136ff0576648402.png)

![进入模型体验页面](img/e6da98d1e8ba5e54598a5651d16c2ee.png)

![复制文心接口密钥](img/dd5906b528b5a1a3981d4dab872adc3.png)

复制对应密钥后填入系统即可。

#### PaddleOCR API 获取方式

登录 [百度星河社区](https://aistudio.baidu.com/overview) 并完成实名认证：

![进入 OCR 服务页面](img/4834759d1a2534a8e0992130f4e5bbe.png)

![查看 OCR 配置入口](img/7763155a127dba1e1c9ae56555b822d.png)

![复制 OCR 密钥](img/7c5854ad6c8bdbe4e8ddfd16d8877b1.png)

复制对应密钥后填入系统即可。

#### 百度语音 API 获取方式

完成登录和实名认证后，参考 [百度语音接入文档](https://cloud.baidu.com/doc/AI_REFERENCE/s/Im3zhy4w6) 完成配置：

![百度语音配置说明](img/2d1dd3681f5008c54576049f0eb89c8.png)

---

## 🧩 功能详解

### 面试配置

支持多种面试场景和多种音色配置：

![面试配置页面](img/fa674dc496310c55a107fa5ab104938%202.png)

开始面试后，会根据上传的简历格式调用 OCR 进行解析：

![开始面试前的简历解析](img/3ff3dc28d26c009ea2834f1e53740dc.png)

### 面试房间

支持语音实时交互面试，语音输入会同步转为文字并进行实时纠错：

![实时面试房间](img/0a82c5e7499172261340e2c1c226e84.png)

面试可灵活结束，方便随时练习：

![结束面试界面](img/902a0f37fd36e5e4ee891f4293ce96b.png)

### 评估报告

面试结束后会自动生成评估报告，帮助用户直观查看不足：

![评估报告页面](img/cc8ee88dbf82050a13d88268752e583.png)

### 简历优化

既支持直接优化，也支持按目标方向进行定制化优化：

![简历优化入口](img/0c679cfb61e4cdb4cbcf34f121c2488.png)

![简历优化问卷](img/92feec4be55fb5283840585c3a3115d.png)

### 简历生成

内置多种简历模板，集简历生成、AI 优化和输出于一体：

![简历生成工作台](img/83192b99831554bba147f0ede46f79b.png)

### 我的简历

支持对上传的简历进行集中管理：

![我的简历页面](img/6d4a134827b6039980ec97d89ff36ee.png)

### 职业生涯规划指导（完善中）

支持生成可长期跟踪的职业规划建议：

![职业规划页面](img/a585649200fabd2a4aed52d6aba4c8d.png)

---

<a id="architecture"></a>

## 🏗️ 技术架构

```text
Web 模式
浏览器 -> frontend(Vite / app.html) -> backend(Flask)

桌面模式
Electron -> 启动本地 backend(Flask) -> 加载 frontend/dist/app.html
                                     |
                                     +-> LLM: DeepSeek / 文心
                                     +-> OCR: PaddleOCR
                                     +-> 语音: 百度语音
                                     +-> 存储: PostgreSQL / Supabase HTTP / SQLite fallback
                                     +-> RAG: 本地 embedding + 检索
```

| 层级 | 技术选型 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS |
| 后端 | Flask + LangChain + SSE + Playwright + Jinja2 |
| 桌面壳 | Electron + electron-builder + PyInstaller |
| 数据存储 | PostgreSQL / Supabase HTTP / SQLite fallback |
| AI 模型 | DeepSeek / 文心一言 |
| OCR / 语音 | PaddleOCR / 百度语音 |
| 文档与资源 | `doc/`、`README_WEB.md`、`README_DESKTOP.md`、`img/` |

---

## 📁 项目结构

```text
proview-desktop/
├── frontend/            # Vue 3 + Vite 前端，index.html 为落地页，app.html 为业务入口
├── backend/             # Flask API，负责面试、简历、OCR、PDF 导出、历史记录、运行时配置
├── desktop/             # Electron 桌面壳，负责启动本地后端、加载 dist、Windows 打包
├── database/            # 本地数据库目录
├── doc/                 # 开发流程与补充文档
├── img/                 # README 使用的界面截图与说明图片
├── README_WEB.md        # Web 版开发说明
├── README_DESKTOP.md    # 桌面版调试与打包说明
├── package-desktop.ps1  # 推荐的根目录打包入口
└── README.md
```

---

<a id="docs"></a>

## 📚 按需阅读

- [README_WEB.md](README_WEB.md)：适合只关注 Vue 页面、Flask API、前后端联调的开发者
- [README_DESKTOP.md](README_DESKTOP.md)：适合调试 Electron 启动链路、桌面运行时与 Windows 打包
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献方式、提交流程与验证要求
- [SECURITY.md](SECURITY.md)：漏洞报告方式与敏感信息处理说明
- [doc/guidance/DEVELOPMENT_WORKFLOW.md](doc/guidance/DEVELOPMENT_WORKFLOW.md)：开发流程补充说明
- [backend/.env.example](backend/.env.example)：后端运行时配置示例

---

## 📜 许可与使用限制

本仓库采用自定义非商业参考许可，正式文本见：

- [LICENSE](LICENSE)：正式许可协议
- [LICENSE.en.md](LICENSE.en.md)：英文参考版
- [REPOSITORY_USAGE_TERMS.zh-CN.md](REPOSITORY_USAGE_TERMS.zh-CN.md)：中文说明版
- [REPOSITORY_USAGE_TERMS.en.md](REPOSITORY_USAGE_TERMS.en.md)：英文说明版

你可以学习、研究、非商业参考和非商业二次开发，但需要保留来源与许可说明；禁止商用，禁止低改动复用，禁止将本仓库或高相似度衍生版本用于比赛、评审、路演、黑客松或类似活动。

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request。开始协作前，建议先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

---

<div align="center">

**把模拟面试、简历处理和职业规划放回你的本地工作流里**

</div>
