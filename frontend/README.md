# yesh_mishak frontend

Minimal React + Vite frontend for local backend connectivity testing.

## Setup

```bash
npm install
```

Create or keep `.env`:

```text
VITE_API_URL=http://localhost:8000
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_FIREBASE_VAPID_KEY=
```

Firebase values here are public web app config values. Do not put Firebase service
account JSON or private keys in the frontend.

Run the dev server:

```bash
npm run dev
```

Open the local Vite URL and confirm the page displays:

```text
Backend status: ok
```
