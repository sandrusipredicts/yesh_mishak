import path from "node:path";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import { parseAndroidVersion } from "./validate-android-version.mjs";

const scriptPath = path.resolve("scripts", "validate-android-version.mjs");
const tempDirs = [];

function buildGradle({ versionCode = "1", versionName = "1.0.0" } = {}) {
  return [
    "apply plugin: 'com.android.application'",
    "",
    `def appVersionCode = ${versionCode}`,
    `def appVersionName = "${versionName}"`,
    "",
    "android {",
    "    defaultConfig {",
    "        versionCode appVersionCode",
    "        versionName appVersionName",
    "    }",
    "}",
    "",
  ].join("\n");
}

async function tempFile(content) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "android-version-test-"));
  tempDirs.push(dir);
  const filePath = path.join(dir, "build.gradle");
  await writeFile(filePath, content);
  return filePath;
}

function runScript(filePath) {
  return spawnSync(process.execPath, [scriptPath, filePath], { encoding: "utf8" });
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("parseAndroidVersion", () => {
  it("parses a valid versionCode and versionName", () => {
    const result = parseAndroidVersion(buildGradle());
    assert.deepEqual(result, { versionCode: 1, versionName: "1.0.0" });
  });

  it("rejects a versionCode of zero", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionCode: "0" })), /positive integer/);
  });

  it("rejects a negative versionCode", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionCode: "-1" })), /positive integer literal/);
  });

  it("rejects a non-integer versionCode", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionCode: "1.5" })), /positive integer literal/);
  });

  it("rejects a versionName missing the patch component", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionName: "1.0" })), /MAJOR\.MINOR\.PATCH/);
  });

  it("rejects an empty versionName", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionName: "" })), /MAJOR\.MINOR\.PATCH/);
  });

  it("rejects a non-numeric versionName", () => {
    assert.throws(() => parseAndroidVersion(buildGradle({ versionName: "release-final" })), /MAJOR\.MINOR\.PATCH/);
  });

  it("throws when appVersionCode is missing", () => {
    assert.throws(() => parseAndroidVersion("android {}\n"), /appVersionCode/);
  });

  it("throws when appVersionName is missing", () => {
    assert.throws(
      () => parseAndroidVersion("def appVersionCode = 1\n"),
      /appVersionName/,
    );
  });
});

describe("validate-android-version CLI", () => {
  it("exits 0 and prints the resolved version for a valid file", async () => {
    const file = await tempFile(buildGradle({ versionCode: "7", versionName: "2.3.1" }));
    const result = runScript(file);

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /versionCode=7 versionName=2\.3\.1/);
  });

  it("exits non-zero with a clear message for an invalid versionName", async () => {
    const file = await tempFile(buildGradle({ versionName: "1.0" }));
    const result = runScript(file);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /MAJOR\.MINOR\.PATCH/);
  });

  it("exits non-zero with a clear message for an invalid versionCode", async () => {
    const file = await tempFile(buildGradle({ versionCode: "0" }));
    const result = runScript(file);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /positive integer/);
  });

  it("validates the real repository build.gradle by default", () => {
    const result = spawnSync(process.execPath, [scriptPath], { encoding: "utf8" });

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Android version configuration is valid/);
  });
});
