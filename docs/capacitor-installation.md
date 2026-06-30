# Capacitor Installation and Validation

## Purpose

This guide documents how to reproduce the existing Capacitor setup for the React/Vite frontend before creating native Android or iOS projects. It covers dependency installation, the shared Capacitor configuration, the web build, and configuration validation only.

Native platform creation belongs to dedicated platform issues and is intentionally excluded from this setup phase.

## Prerequisites

- Install Node.js and npm.
- Clone the project locally.
- Ensure the frontend dependencies can be installed from `frontend/package.json` and `frontend/package-lock.json`.
- Run all npm and Capacitor commands in the `frontend/` directory.

## Current Capacitor Configuration

The shared configuration is stored in `frontend/capacitor.config.ts`:

```ts
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.yeshmishak.app',
  appName: 'Yesh Mishak',
  webDir: 'dist',
};

export default config;
```

| Setting | Value |
| :--- | :--- |
| `appId` | `com.yeshmishak.app` |
| `appName` | `Yesh Mishak` |
| `webDir` | `dist` |

The `webDir` value matches Vite's build output directory.

## Installation Steps Already Performed

The project setup used the Capacitor 8.4.1 versions approved by ISSUE-190:

```powershell
cd frontend
npm install @capacitor/core@8.4.1
npm install -D @capacitor/cli@8.4.1
```

`@capacitor/core` is a runtime dependency. `@capacitor/cli` is a development dependency.

The project configuration was then created at `frontend/capacitor.config.ts` with the values shown above. Android and iOS platforms are intentionally not created as part of this phase.

## Reproduce the Setup

From a fresh local clone:

```powershell
cd frontend
npm install
npm run build
```

Verify that the build produced the expected entry point:

```powershell
Test-Path -LiteralPath .\dist\index.html
```

Expected result:

```text
True
```

Verify that generated JavaScript and CSS assets exist:

```powershell
Get-ChildItem -LiteralPath .\dist\assets -File -Filter *.js
Get-ChildItem -LiteralPath .\dist\assets -File -Filter *.css
```

Finally, ask Capacitor to load and display the project configuration:

```powershell
npx cap config
```

## Expected Validation Output

A successful setup has all of the following results:

- `npm run build` exits successfully.
- `frontend/dist/` exists.
- `frontend/dist/index.html` exists.
- `frontend/dist/assets/` contains generated JavaScript and CSS files.
- `npx cap config` exits successfully.
- Capacitor resolves:
  - `appId: 'com.yeshmishak.app'`
  - `appName: 'Yesh Mishak'`
  - `webDir: 'dist'`
  - an absolute web directory ending in `frontend\dist` on Windows or `frontend/dist` on macOS and Linux

These checks confirm that Capacitor can find the built web application through the configured `webDir`.

## What Not to Do Yet

Do not create or modify native projects during this setup phase:

```text
npx cap add android
npx cap add ios
```

Do not run either command until its dedicated native-platform issue authorizes platform creation. Native folders, platform configuration, signing, Firebase native configuration, and platform builds are outside the scope of this guide.

## Troubleshooting

### `dist/index.html` is missing

Run the frontend build from `frontend/`:

```powershell
npm run build
```

If the build fails, resolve the web build error before running further Capacitor or native commands.

### Capacitor resolves the wrong `webDir`

Open `frontend/capacitor.config.ts` and confirm that `webDir` is set to `dist`. Also confirm that Vite has not been configured with a different `build.outDir`.

### `npx cap config` fails

- Confirm that the current directory is `frontend/`.
- Run `npm install` to restore dependencies from the lockfile.
- Confirm that `@capacitor/core` and `@capacitor/cli` are present in `frontend/package.json`.
- Confirm that `frontend/capacitor.config.ts` exists and contains valid TypeScript.

### The frontend build fails

Fix the web build before touching Capacitor platform or native code. A native project cannot package a missing or broken web build.

## Related Issues

- ISSUE-191: Capacitor dependencies installed and verified.
- ISSUE-192: Initial Capacitor configuration created.
- ISSUE-193: Web build compatibility with the Capacitor configuration validated.
