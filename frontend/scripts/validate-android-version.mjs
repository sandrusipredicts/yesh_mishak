#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_BUILD_GRADLE = path.join(FRONTEND_ROOT, "android", "app", "build.gradle");

const VERSION_CODE_PATTERN = /^\s*def\s+appVersionCode\s*=\s*(\S+)\s*$/m;
const VERSION_NAME_PATTERN = /^\s*def\s+appVersionName\s*=\s*"([^"]*)"\s*$/m;
const SEMVER_PATTERN = /^\d+\.\d+\.\d+$/;

export function parseAndroidVersion(buildGradleContent) {
  const versionCodeMatch = buildGradleContent.match(VERSION_CODE_PATTERN);
  if (!versionCodeMatch) {
    throw new Error("Could not find 'def appVersionCode = <int>' in build.gradle.");
  }

  const versionNameMatch = buildGradleContent.match(VERSION_NAME_PATTERN);
  if (!versionNameMatch) {
    throw new Error('Could not find \'def appVersionName = "<version>"\' in build.gradle.');
  }

  const rawVersionCode = versionCodeMatch[1];
  if (!/^\d+$/.test(rawVersionCode)) {
    throw new Error(`Android versionCode '${rawVersionCode}' must be a positive integer literal.`);
  }

  const versionCode = Number.parseInt(rawVersionCode, 10);
  if (!Number.isInteger(versionCode) || versionCode <= 0) {
    throw new Error(`Android versionCode '${rawVersionCode}' must be a positive integer.`);
  }

  const versionName = versionNameMatch[1];
  if (!SEMVER_PATTERN.test(versionName)) {
    throw new Error(
      `Android versionName '${versionName}' must follow MAJOR.MINOR.PATCH semantic versioning (e.g. 1.0.0).`,
    );
  }

  return { versionCode, versionName };
}

async function main() {
  try {
    const buildGradlePath = process.argv[2]
      ? path.resolve(process.argv[2])
      : DEFAULT_BUILD_GRADLE;
    const content = await readFile(buildGradlePath, "utf8");
    const { versionCode, versionName } = parseAndroidVersion(content);
    console.log(`Android version configuration is valid: versionCode=${versionCode} versionName=${versionName}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await main();
}
