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

export async function hashFile(filePath) {
  const content = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

export async function verifyBundle(release, dist, distDir = DIST_DIR) {
  console.log(`Verifying bundle for release: ${release}, dist: ${dist}`);
  const metadataPath = path.resolve(distDir, 'sentry-build-metadata.json');
  let metaStr;
  try {
    metaStr = await fs.readFile(metadataPath, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(`sentry-build-metadata.json not found in dist directory!`);
    }
    throw new Error(`Failed to read sentry-build-metadata.json: ${err.message}`);
  }

  let meta;
  try {
    meta = JSON.parse(metaStr);
  } catch (err) {
    throw new Error(`Failed to parse sentry-build-metadata.json: ${err.message}`);
  }

  if (meta.release !== release) {
    throw new Error(`Canonical release '${release}' not found in manifest (found '${meta.release}')!`);
  }
  if (meta.dist !== dist) {
    throw new Error(`Canonical dist '${dist}' not found in manifest (found '${meta.dist}')!`);
  }

  console.log('Bundle verification passed.');
}

export async function verifyAssets(distDir = DIST_DIR, assetsDir = ASSETS_DIR) {
  console.log('Verifying Capacitor synced assets recursively...');
  try {
    const distFiles = await getFiles(distDir);
    const assetFiles = await getFiles(assetsDir);

    // Create relative maps
    const distMap = new Map();
    for (const f of distFiles) {
      // Normalize to posix-style relative paths
      const rel = path.relative(distDir, f).split(path.sep).join('/');
      distMap.set(rel, await hashFile(f));
    }

    const assetMap = new Map();
    for (const f of assetFiles) {
      const rel = path.relative(assetsDir, f).split(path.sep).join('/');
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
      let errMsg = 'Asset verification failed!';
      if (mismatches.length > 0) errMsg += ` Mismatched hashes: ${mismatches.join(', ')}`;
      if (missingInAssets.length > 0) errMsg += ` Missing in Android assets: ${missingInAssets.join(', ')}`;
      if (extraInAssets.length > 0) errMsg += ` Extra/stale files in Android assets: ${extraInAssets.join(', ')}`;
      throw new Error(errMsg);
    }
  } catch (err) {
    throw new Error(`Failed to compare assets: ${err.message}`);
  }
  console.log('Assets recursive verification passed. Hashes perfectly align.');
}

async function main() {
  const args = process.argv.slice(2);
  const bundleOnly = args.includes('--bundle-only');
  const assetsOnly = args.includes('--assets-only');

  const release = process.env.VITE_SENTRY_RELEASE;
  const dist = process.env.VITE_SENTRY_DIST;

  try {
    if (bundleOnly || (!bundleOnly && !assetsOnly)) {
      if (!release || !dist) {
        throw new Error('VITE_SENTRY_RELEASE and VITE_SENTRY_DIST must be set in the environment.');
      }
      await verifyBundle(release, dist);
    }

    if (assetsOnly || (!bundleOnly && !assetsOnly)) {
      await verifyAssets();
    }
  } catch (err) {
    console.error(`ERROR: ${err.message}`);
    process.exit(1);
  }
}

const isMain = process.argv[1] === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}
