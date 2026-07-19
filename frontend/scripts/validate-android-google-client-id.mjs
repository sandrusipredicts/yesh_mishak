#!/usr/bin/env node

import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnv } from "vite";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GOOGLE_CLIENT_ID_PATTERN = /^[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/;

const env = loadEnv("android", FRONTEND_ROOT, "VITE_");
const clientId = env.VITE_GOOGLE_CLIENT_ID?.trim();

if (!clientId) {
  console.error("Android builds require VITE_GOOGLE_CLIENT_ID.");
  process.exitCode = 1;
} else if (!GOOGLE_CLIENT_ID_PATTERN.test(clientId)) {
  console.error(
    "VITE_GOOGLE_CLIENT_ID must be a Google OAuth client ID ending in .apps.googleusercontent.com.",
  );
  process.exitCode = 1;
} else {
  console.log("Android Google OAuth client ID configuration is present and well-formed.");
}
