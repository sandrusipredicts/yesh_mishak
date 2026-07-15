#!/usr/bin/env node

import { Buffer } from "node:buffer";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const DEFAULT_ENV_VAR = "ANDROID_GOOGLE_SERVICES_JSON_BASE64";
const EXPECTED_PACKAGE = "com.yeshmishak.app";
const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_OUTPUT = path.join(FRONTEND_ROOT, "android", "app", "google-services.json");

function usage() {
  return [
    "Usage:",
    "  node scripts/materialize-google-services.mjs [--env NAME] [--output PATH]",
    "  node scripts/materialize-google-services.mjs --validate-file PATH",
  ].join("\n");
}

function parseArgs(argv) {
  const options = {
    envName: DEFAULT_ENV_VAR,
    output: DEFAULT_OUTPUT,
    validateFile: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];

    if (arg === "--env" && next) {
      options.envName = next;
      index += 1;
    } else if (arg === "--output" && next) {
      options.output = path.resolve(next);
      index += 1;
    } else if (arg === "--validate-file" && next) {
      options.validateFile = path.resolve(next);
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown or incomplete argument: ${arg}\n${usage()}`);
    }
  }

  return options;
}

function decodeBase64(value, envName) {
  if (!value || !value.trim()) {
    throw new Error(`Missing required environment variable ${envName}.`);
  }

  const compactValue = value.replace(/\s/g, "");
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(compactValue) || compactValue.length % 4 === 1) {
    throw new Error(`${envName} is not valid Base64.`);
  }

  const decoded = Buffer.from(compactValue, "base64");
  const normalizedInput = compactValue.replace(/=+$/, "");
  const normalizedRoundTrip = decoded.toString("base64").replace(/=+$/, "");

  if (!decoded.length || normalizedInput !== normalizedRoundTrip) {
    throw new Error(`${envName} is not valid Base64.`);
  }

  return decoded.toString("utf8");
}

function parseJson(content) {
  if (!content.trim()) {
    throw new Error("google-services.json is empty.");
  }

  try {
    return JSON.parse(content);
  } catch {
    throw new Error("google-services.json content is not valid JSON.");
  }
}

function androidPackageNames(config) {
  if (!Array.isArray(config.client)) {
    return [];
  }

  return config.client
    .map((client) => client?.client_info?.android_client_info?.package_name)
    .filter((packageName) => typeof packageName === "string" && packageName.length > 0);
}

function validateGoogleServicesJson(content) {
  const config = parseJson(content);

  if (config?.type === "service_account" || config?.private_key || config?.client_email) {
    throw new Error("google-services.json must be Firebase Android client config, not a Firebase Admin service-account JSON file.");
  }

  if (!config?.project_info || !Array.isArray(config.client)) {
    throw new Error("google-services.json is not a Firebase Android client configuration file.");
  }

  const packageNames = androidPackageNames(config);

  if (!packageNames.includes(EXPECTED_PACKAGE)) {
    throw new Error(
      `google-services.json does not contain an Android client for ${EXPECTED_PACKAGE}.`,
    );
  }

  return config;
}

async function materialize(options) {
  const content = decodeBase64(process.env[options.envName], options.envName);
  validateGoogleServicesJson(content);
  await mkdir(path.dirname(options.output), { recursive: true });
  const temporaryOutput = `${options.output}.tmp-${process.pid}-${Date.now()}`;

  try {
    await writeFile(temporaryOutput, content, { mode: 0o600 });
    await rename(temporaryOutput, options.output);
  } catch (error) {
    await unlink(temporaryOutput).catch(() => {});
    throw error;
  }

  console.log(`Wrote validated Android Firebase config to ${path.relative(process.cwd(), options.output)}`);
}

async function validateFile(filePath) {
  let content;

  try {
    content = await readFile(filePath, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error(`Missing google-services.json at ${filePath}.`);
    }

    throw error;
  }

  validateGoogleServicesJson(content);
  console.log(`Validated Android Firebase config at ${path.relative(process.cwd(), filePath)}`);
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));

    if (options.help) {
      console.log(usage());
      return;
    }

    if (options.validateFile) {
      await validateFile(options.validateFile);
      return;
    }

    await materialize(options);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

await main();
