import { Buffer } from "node:buffer";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

const scriptPath = path.resolve("scripts", "materialize-google-services.mjs");
const expectedPackage = "com.yeshmishak.app";
const envName = "ANDROID_GOOGLE_SERVICES_JSON_BASE64";
const tempDirs = [];

function googleServicesJson(packageNames = [expectedPackage]) {
  return JSON.stringify({
    project_info: {
      project_number: "123456789",
      project_id: "synthetic-test-project",
      storage_bucket: "synthetic-test-project.firebasestorage.app",
    },
    client: packageNames.map((packageName, index) => ({
      client_info: {
        mobilesdk_app_id: `1:123456789:android:${index}`,
        android_client_info: {
          package_name: packageName,
        },
      },
      api_key: [{ current_key: "synthetic-api-key" }],
      services: {},
    })),
    configuration_version: "1",
  });
}

function serviceAccountJson() {
  return JSON.stringify({
    type: "service_account",
    project_id: "synthetic-test-project",
    private_key: "synthetic-private-key",
    client_email: "synthetic@example.invalid",
  });
}

function encode(value) {
  return Buffer.from(value, "utf8").toString("base64");
}

async function tempDir() {
  const dir = await mkdtemp(path.join(os.tmpdir(), "google-services-test-"));
  tempDirs.push(dir);
  return dir;
}

function runScript(args = [], env = {}, cwd = path.resolve(".")) {
  return spawnSync(process.execPath, [scriptPath, ...args], {
    cwd,
    env: {
      ...process.env,
      [envName]: undefined,
      ...env,
    },
    encoding: "utf8",
  });
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("materialize-google-services", () => {
  it("writes a decoded google-services.json with the expected Android package", async () => {
    const dir = await tempDir();
    const output = path.join(dir, "google-services.json");
    const fixture = googleServicesJson();

    const result = runScript(["--output", output], {
      [envName]: encode(fixture),
    });

    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(await readFile(output, "utf8")), JSON.parse(fixture));
  });

  it("overwrites a stale output file after validation succeeds", async () => {
    const dir = await tempDir();
    const output = path.join(dir, "google-services.json");
    const fixture = googleServicesJson();
    await writeFile(output, "stale");

    const result = runScript(["--output", output], {
      [envName]: encode(fixture),
    });

    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(await readFile(output, "utf8")), JSON.parse(fixture));
  });

  it("validates an existing google-services.json file", async () => {
    const dir = await tempDir();
    const file = path.join(dir, "google-services.json");
    await writeFile(file, googleServicesJson());

    const result = runScript(["--validate-file", file]);

    assert.equal(result.status, 0, result.stderr);
  });

  it("fails when a local validation file is missing", async () => {
    const dir = await tempDir();
    const missingFile = path.join(dir, "google-services.json");

    const result = runScript(["--validate-file", missingFile]);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Missing google-services\.json/);
  });

  it("fails when a local validation file is empty", async () => {
    const dir = await tempDir();
    const file = path.join(dir, "google-services.json");
    await writeFile(file, "");

    const result = runScript(["--validate-file", file]);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /empty/);
  });

  it("fails when a local validation file contains invalid JSON", async () => {
    const dir = await tempDir();
    const file = path.join(dir, "google-services.json");
    await writeFile(file, "{");

    const result = runScript(["--validate-file", file]);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /not valid JSON/);
  });

  it("rejects Firebase Admin service-account JSON", () => {
    const result = runScript([], {
      [envName]: encode(serviceAccountJson()),
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /service-account/);
  });

  it("fails when the required Base64 environment variable is missing", () => {
    const result = runScript();

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Missing required environment variable/);
  });

  it("fails when the Base64 value is malformed", () => {
    const result = runScript([], {
      [envName]: "not valid base64!",
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /not valid Base64/);
  });

  it("fails when decoded content is not valid JSON", () => {
    const result = runScript([], {
      [envName]: encode("{"),
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /not valid JSON/);
  });

  it("does not replace an existing file when decoded content fails validation", async () => {
    const dir = await tempDir();
    const output = path.join(dir, "google-services.json");
    const existing = googleServicesJson();
    await writeFile(output, existing);

    const result = runScript(["--output", output], {
      [envName]: encode(googleServicesJson(["com.example.other"])),
    });

    assert.notEqual(result.status, 0);
    assert.deepEqual(JSON.parse(await readFile(output, "utf8")), JSON.parse(existing));
  });

  it("fails when no Android client matches the expected package", () => {
    const result = runScript([], {
      [envName]: encode(googleServicesJson(["com.example.other"])),
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, new RegExp(expectedPackage));
  });

  it("accepts files with multiple clients when one matches the expected package", async () => {
    const dir = await tempDir();
    const output = path.join(dir, "google-services.json");

    const result = runScript(["--output", output], {
      [envName]: encode(googleServicesJson(["com.example.other", expectedPackage])),
    });

    assert.equal(result.status, 0, result.stderr);
  });

  it("does not print Firebase configuration values on success", async () => {
    const dir = await tempDir();
    const output = path.join(dir, "google-services.json");
    const fixture = googleServicesJson();

    const result = runScript(["--output", output], {
      [envName]: encode(fixture),
    });

    assert.equal(result.status, 0, result.stderr);
    assert.doesNotMatch(result.stdout, /synthetic-test-project|synthetic-api-key/);
    assert.doesNotMatch(result.stderr, /synthetic-test-project|synthetic-api-key/);
  });

  it("resolves the default output path from the frontend script location", () => {
    const repoRoot = path.resolve("..");
    const result = runScript(["--help"], {}, repoRoot);

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /materialize-google-services\.mjs/);
  });
});
