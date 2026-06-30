# yesh_mishak frontend

Minimal React + Vite frontend for local backend connectivity testing.

## Setup

```bash
npm install
```

Create or keep `.env`:

```text
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=your-public-anon-key
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

## Google OAuth for web and Capacitor Android

Supabase Auth must have Google enabled and must allow both redirect URLs:

- Web: `https://your-web-origin.example/auth/callback`
- Capacitor Android: `yeshmishak://auth-callback`

In Google Cloud, the authorized redirect URI remains the Supabase callback:

```text
https://<SUPABASE_PROJECT_ID>.supabase.co/auth/v1/callback
```

Do not add the custom Android scheme as a Google Cloud redirect URI. Supabase
receives Google's callback and then returns the PKCE flow to the app.

Run the dev server:

```bash
npm run dev
```

Open the local Vite URL and confirm the page displays:

```text
Backend status: ok
```
