import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, '..');
const DIST_DIR = path.resolve(FRONTEND_DIR, 'dist');
const ASSETS_DIR = path.resolve(FRONTEND_DIR, 'android', 'app', 'src', 'main', 'assets', 'public');

async function getFiles(dir) {
  const dirents = await fs.readdir(dir, { withFileTypes: true });
  const files = await Promise.all(dirents.map((dirent) => {
    const res = path.resolve(dir, dirent.name);
    return dirent.isDirectory() ? getFiles(res) : res;
  }));
  return Array.prototype.concat(...files);
}

async function hashFile(filePath) {
  const content = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

async function verifyBundle(release, dist) {
  console.log(`Verifying bundle for release: ${release}, dist: ${dist}`);
  const metadataPath = path.resolve(DIST_DIR, 'sentry-build-metadata.json');
  let metaStr;
  try {
    metaStr = await fs.readFile(metadataPath, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') {
      console.error(`ERROR: sentry-build-metadata.json not found in dist directory!`);
      process.exit(1);
    }
    console.error(`ERROR: Failed to read sentry-build-metadata.json: ${err.message}`);
    process.exit(1);
  }

  let meta;
  try {
    meta = JSON.parse(metaStr);
  } catch (err) {
    console.error(`ERROR: Failed to parse sentry-build-metadata.json: ${err.message}`);
    process.exit(1);
  }

  if (meta.release !== release) {
    console.error(`ERROR: Canonical release '${release}' not found in manifest (found '${meta.release}')!`);
    process.exit(1);
  }
  if (meta.dist !== dist) {
    console.error(`ERROR: Canonical dist '${dist}' not found in manifest (found '${meta.dist}')!`);
    process.exit(1);
  }
  
  console.log('Bundle verification passed.');
}

async function verifyAssets() {
  console.log('Verifying Capacitor synced assets recursively...');
  try {
    const distFiles = await getFiles(DIST_DIR);
    const assetFiles = await getFiles(ASSETS_DIR);
    
    // Create relative maps
    const distMap = new Map();
    for (const f of distFiles) {
      // Normalize to posix-style relative paths
      const rel = path.relative(DIST_DIR, f).split(path.sep).join('/');
      distMap.set(rel, await hashFile(f));
    }
    
    const assetMap = new Map();
    for (const f of assetFiles) {
      const rel = path.relative(ASSETS_DIR, f).split(path.sep).join('/');
      assetMap.set(rel, await hashFile(f));
    }

    // Exclude explicitly justified generated/native-only files injected by Capacitor
    assetMap.delete('capacitor.config.json');
    assetMap.delete('cordova.js');
    assetMap.delete('cordova_plugins.js');

    const mismatches = [];
    const missingInAssets = [];
    
    for (const [rel, hash] of distMap) {
      if (!assetMap.has(rel)) {
        missingInAssets.push(rel);
      } else if (assetMap.get(rel) !== hash) {
        mismatches.push(rel);
      }
      assetMap.delete(rel);
    }
    
    const extraInAssets = Array.from(assetMap.keys());

    if (mismatches.length > 0 || missingInAssets.length > 0 || extraInAssets.length > 0) {
      console.error('ERROR: Asset verification failed!');
      if (mismatches.length > 0) console.error(`Mismatched hashes: ${mismatches.join(', ')}`);
      if (missingInAssets.length > 0) console.error(`Missing in Android assets: ${missingInAssets.join(', ')}`);
      if (extraInAssets.length > 0) console.error(`Extra/stale files in Android assets: ${extraInAssets.join(', ')}`);
      process.exit(1);
    }
  } catch (err) {
    console.error('ERROR: Failed to compare assets:', err.message);
    process.exit(1);
  }
  console.log('Assets recursive verification passed. Hashes perfectly align.');
}

async function main() {
  const args = process.argv.slice(2);
  const bundleOnly = args.includes('--bundle-only');
  const assetsOnly = args.includes('--assets-only');
  
  const release = process.env.VITE_SENTRY_RELEASE;
  const dist = process.env.VITE_SENTRY_DIST;

  if (bundleOnly || (!bundleOnly && !assetsOnly)) {
    if (!release || !dist) {
      console.error('ERROR: VITE_SENTRY_RELEASE and VITE_SENTRY_DIST must be set in the environment.');
      process.exit(1);
    }
    await verifyBundle(release, dist);
  }
  
  if (assetsOnly || (!bundleOnly && !assetsOnly)) {
    await verifyAssets();
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
