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
  let files;
  try {
    files = await getFiles(DIST_DIR);
  } catch (err) {
    console.error(`ERROR: Failed to read dist directory. Did the build run? ${err.message}`);
    process.exit(1);
  }
  
  const jsFiles = files.filter(f => f.endsWith('.js'));
  
  let foundRelease = false;
  let foundDist = false;
  let foundUnknown = false;

  for (const file of jsFiles) {
    const content = await fs.readFile(file, 'utf8');
    if (content.includes(`"${release}"`) || content.includes(`'${release}'`) || content.includes(release)) {
      foundRelease = true;
    }
    if (content.includes(`"${dist}"`) || content.includes(`'${dist}'`) || content.includes(`dist:${dist}`) || content.includes(`dist:"${dist}"`) || content.includes(`dist:'${dist}'`)) {
      foundDist = true;
    }
    // Check for the old fallback
    if (content.includes("release:'unknown'") || content.includes('release:"unknown"') || content.includes("dist:'unknown'") || content.includes('dist:"unknown"')) {
       foundUnknown = true;
    }
  }

  if (!foundRelease) {
    console.error(`ERROR: Canonical release '${release}' not found in any JS bundle file!`);
    process.exit(1);
  }
  if (!foundDist) {
    console.error(`ERROR: Canonical dist '${dist}' not found in any JS bundle file!`);
    process.exit(1);
  }
  if (foundUnknown) {
    console.error(`ERROR: 'unknown' fallback found in JS bundle files! Sentry initialization is falling back.`);
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
