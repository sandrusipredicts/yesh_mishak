import { test } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { verifyBundle, verifyAssets } from './verify-android-build.mjs';

async function createTempDir() {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'verify-android-build-test-'));
  return tmpDir;
}

test('verifyBundle: passes with valid metadata manifest', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({
    release: 'com.yeshmishak.app@1.0.6+7',
    dist: '7'
  }));

  // Should not throw
  await verifyBundle('com.yeshmishak.app@1.0.6+7', '7', tmp);
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on missing manifest', async () => {
  const tmp = await createTempDir();
  await assert.rejects(
    () => verifyBundle('r', 'd', tmp),
    /not found in dist directory/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on malformed JSON', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), '{ "bad": ');
  
  await assert.rejects(
    () => verifyBundle('r', 'd', tmp),
    /Failed to parse sentry-build-metadata.json/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on missing release', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({ dist: '7' }));
  
  await assert.rejects(
    () => verifyBundle('expected-release', '7', tmp),
    /Canonical release 'expected-release' not found in manifest/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on missing dist', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({ release: 'expected-release' }));
  
  await assert.rejects(
    () => verifyBundle('expected-release', '7', tmp),
    /Canonical dist '7' not found in manifest/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on wrong release', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({ release: 'wrong-release', dist: '7' }));
  
  await assert.rejects(
    () => verifyBundle('expected-release', '7', tmp),
    /Canonical release 'expected-release' not found in manifest/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: fails on wrong dist', async () => {
  const tmp = await createTempDir();
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({ release: 'expected-release', dist: 'wrong-dist' }));
  
  await assert.rejects(
    () => verifyBundle('expected-release', '7', tmp),
    /Canonical dist '7' not found in manifest/
  );
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyBundle: unrelated literal 7 in a JS file does not affect verification', async () => {
  const tmp = await createTempDir();
  // Provide the wrong dist in the metadata JSON
  await fs.writeFile(path.join(tmp, 'sentry-build-metadata.json'), JSON.stringify({
    release: 'com.yeshmishak.app@1.0.6+7',
    dist: '5'
  }));

  // Even if we drop an unrelated JS file that contains "7" or `7` into the directory
  // (the script no longer crawls JS files anyway, so it should definitely fail
  // because the metadata is wrong)
  await fs.writeFile(path.join(tmp, 'unrelated.js'), 'const a = `7`; const b = "7"; dist: 7');

  await assert.rejects(
    () => verifyBundle('com.yeshmishak.app@1.0.6+7', '7', tmp),
    /Canonical dist '7' not found in manifest/
  );
  
  await fs.rm(tmp, { recursive: true, force: true });
});

test('verifyAssets: matching dist and Android manifests pass', async () => {
  const distTmp = await createTempDir();
  const assetTmp = await createTempDir();

  await fs.writeFile(path.join(distTmp, 'sentry-build-metadata.json'), '{"dist":"7"}');
  await fs.writeFile(path.join(distTmp, 'app.js'), 'console.log("hello")');

  await fs.writeFile(path.join(assetTmp, 'sentry-build-metadata.json'), '{"dist":"7"}');
  await fs.writeFile(path.join(assetTmp, 'app.js'), 'console.log("hello")');
  
  // Excluded plugins automatically ignored
  await fs.writeFile(path.join(assetTmp, 'capacitor.config.json'), 'ignored');

  await verifyAssets(distTmp, assetTmp);
  
  await fs.rm(distTmp, { recursive: true, force: true });
  await fs.rm(assetTmp, { recursive: true, force: true });
});

test('verifyAssets: Android copied manifest differs from dist manifest fails', async () => {
  const distTmp = await createTempDir();
  const assetTmp = await createTempDir();

  await fs.writeFile(path.join(distTmp, 'sentry-build-metadata.json'), '{"dist":"7"}');
  await fs.writeFile(path.join(assetTmp, 'sentry-build-metadata.json'), '{"dist":"5"}'); // Mismatch!

  await assert.rejects(
    () => verifyAssets(distTmp, assetTmp),
    /Mismatched hashes: sentry-build-metadata.json/
  );
  
  await fs.rm(distTmp, { recursive: true, force: true });
  await fs.rm(assetTmp, { recursive: true, force: true });
});

test('verifyAssets: Android copied manifest missing fails', async () => {
  const distTmp = await createTempDir();
  const assetTmp = await createTempDir();

  await fs.writeFile(path.join(distTmp, 'sentry-build-metadata.json'), '{"dist":"7"}');

  await assert.rejects(
    () => verifyAssets(distTmp, assetTmp),
    /Missing in Android assets: sentry-build-metadata.json/
  );
  
  await fs.rm(distTmp, { recursive: true, force: true });
  await fs.rm(assetTmp, { recursive: true, force: true });
});

test('verifyAssets: recursive asset mismatch still fails', async () => {
  const distTmp = await createTempDir();
  const assetTmp = await createTempDir();

  await fs.writeFile(path.join(distTmp, 'app.js'), 'var a = 1;');
  await fs.writeFile(path.join(assetTmp, 'app.js'), 'var a = 2;'); // Mismatch

  await assert.rejects(
    () => verifyAssets(distTmp, assetTmp),
    /Mismatched hashes: app.js/
  );
  
  await fs.rm(distTmp, { recursive: true, force: true });
  await fs.rm(assetTmp, { recursive: true, force: true });
});

test('verifyAssets: unexpected stale Android asset still fails', async () => {
  const distTmp = await createTempDir();
  const assetTmp = await createTempDir();

  await fs.writeFile(path.join(assetTmp, 'stale.js'), 'console.log("stale")');

  await assert.rejects(
    () => verifyAssets(distTmp, assetTmp),
    /Extra\/stale files in Android assets: stale.js/
  );
  
  await fs.rm(distTmp, { recursive: true, force: true });
  await fs.rm(assetTmp, { recursive: true, force: true });
});
