# ProView Desktop Development Workflow

## Goal

This repository is best developed in two modes:

1. Web-style development for fast iteration
2. Desktop verification for Electron-specific behavior

Do not package the desktop app after every small change.
Most daily work should happen in `backend/` and `frontend/`.

## Recommended Daily Workflow

### Mode A: Fast daily development

Use this mode for:

- UI changes
- page logic
- API integration
- store changes
- most backend feature work

Start the backend:

```powershell
cd .\backend
python app.py
```

Start the frontend dev server:

```powershell
cd .\frontend
npm run dev
```

Open in the browser:

```text
http://localhost:5173/app.html
```

Why this is the default:

- Vite hot reload is much faster than rebuilding Electron assets
- frontend changes are visible immediately
- backend can be debugged directly from the terminal
- most feature work does not require a packaged desktop build

## How The Current Repo Works

### Frontend

- source code lives in `frontend/`
- production output is generated into `frontend/dist/`
- browser development uses Vite

### Backend

- source code lives in `backend/`
- browser development usually runs `backend/app.py` directly
- desktop mode starts the backend through Electron automatically

### Desktop shell

- Electron source lives in `desktop/`
- Electron loads `frontend/dist/app.html`
- packaged desktop builds bundle the frontend and a PyInstaller backend

## Port Rules

There are two normal runtime shapes in this repo.

### Browser development

- backend usually runs on `PROVIEW_API_PORT=5000`
- Vite proxies `/api` requests to the backend
- frontend can keep using relative `/api/...` calls

### Desktop runtime

- Electron uses port `18765` by default
- `desktop/scripts/build-frontend.ps1` injects:
  - `PROVIEW_API_PORT=18765`
  - `VITE_API_BASE_URL=http://127.0.0.1:18765`
- Electron starts the backend itself

This means:

- browser dev and desktop verification do not need to share the same port
- this is expected

## Recommended Work Split

### Frontend changes

Use browser development first:

```powershell
cd .\frontend
npm run dev
```

Examples:

- Vue views
- components
- Pinia stores
- CSS and layout
- API request formatting

When a change is stable, verify it in Electron.

### Backend changes

Run the backend directly:

```powershell
cd .\backend
python app.py
```

Examples:

- Flask routes
- OCR flow
- resume export
- auth/session logic
- database behavior

After backend changes that affect Electron startup or packaged paths, do one desktop verification pass.

## Desktop Verification Workflow

When you want to verify real desktop behavior, do this:

### 1. Build the frontend bundle

```powershell
cd .\desktop
npm run build:frontend
```

### 2. Start Electron

```powershell
cd .\desktop
npx electron .
```

What this verifies:

- Electron boot flow
- splash screen
- backend auto-start
- `frontend/dist` loading
- local desktop runtime environment
- packaged-path assumptions that may differ from browser dev

## Release Build Workflow

Only do this when you actually want an installer or portable package.

### Build the installer

```powershell
cd .\desktop
npm run dist
```

This will:

1. build the frontend
2. package the backend with PyInstaller
3. build the Electron installer and portable package

## Practical Recommendation

Use this as your normal rhythm:

1. Develop in `frontend/` and `backend/`
2. Test quickly in the browser
3. When a feature is mostly done, run one Electron verification
4. Only run `npm run dist` for release validation

This gives the fastest iteration speed with the least packaging overhead.

## Commands Cheat Sheet

### Install frontend deps

```powershell
cd .\frontend
npm install
```

### Install desktop deps

```powershell
cd .\desktop
npm install
```

### Install backend deps

```powershell
cd .\backend
pip install -r requirements.txt
python -m playwright install chromium
```

### Run backend only

```powershell
cd .\backend
python app.py
```

### Run frontend dev only

```powershell
cd .\frontend
npm run dev
```

### Build frontend for desktop

```powershell
cd .\desktop
npm run build:frontend
```

### Package backend for desktop

```powershell
cd .\desktop
npm run build:backend
```

### Build full desktop release

```powershell
cd .\desktop
npm run dist
```

## Common Problems

### Problem: Electron says frontend bundle is missing

Cause:

- `frontend/dist/` has not been built yet

Fix:

```powershell
cd .\desktop
npm run build:frontend
```

### Problem: Browser dev cannot call backend

Check:

- backend is running
- backend port matches `backend/.env`
- Vite proxy target is correct

Relevant file:

- `frontend/vite.config.ts`

### Problem: Desktop starts but backend health check fails

Check:

- Python environment is usable
- `backend/.env` is valid
- required local dependencies are installed
- the target port is not occupied

Relevant file:

- `desktop/electron/main.cjs`

### Problem: Packaged build fails

Check:

- `python -m playwright install chromium`
- PyInstaller is available
- backend native dependencies are installed

Run again:

```powershell
cd .\desktop
npm run build:backend
```

## Best Practice For This Repo

The best strategy right now is:

- treat `frontend/` as your main UI workspace
- treat `backend/` as your main feature/service workspace
- treat `desktop/` as the packaging and runtime integration layer

So the short answer is:

- yes, usually develop the web side first
- then build it into `frontend/dist`
- then use `desktop/` to verify and package
