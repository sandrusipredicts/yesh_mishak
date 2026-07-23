import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, '..');
const ANDROID_DIR = path.resolve(FRONTEND_DIR, 'android');

const isWindows = process.platform === 'win32';
const gradlewCmd = isWindows ? '.\\gradlew.bat' : './gradlew';

const isOfficial = process.argv.includes('--official');

function runCommand(command, args, options = {}) {
  console.log(`> ${command} ${args.join(' ')}`);
  const result = spawnSync(command, args, { stdio: 'inherit', ...options });
  if (result.error) {
    console.error(`Error launching command: ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`Command failed with exit code ${result.status}`);
    process.exit(result.status);
  }
  return result;
}

export function extractJsonFromOutput(output) {
  const startMarker = '===SENTRY_METADATA_START===';
  const endMarker = '===SENTRY_METADATA_END===';
  const startIndex = output.indexOf(startMarker);
  const endIndex = output.indexOf(endMarker);

  if (startIndex === -1 || endIndex === -1) {
    throw new Error('Failed to locate metadata JSON boundaries in Gradle output.');
  }
  
  if (output.indexOf(startMarker, startIndex + 1) !== -1 || output.indexOf(endMarker, endIndex + 1) !== -1) {
    throw new Error('Duplicate metadata markers found in Gradle output.');
  }

  const jsonString = output.substring(startIndex + startMarker.length, endIndex).trim();
  try {
    return JSON.parse(jsonString);
  } catch (err) {
    throw new Error(`Failed to parse metadata JSON: ${err.message}`);
  }
}

export function validateMetadata(metadata) {
  if (metadata.applicationId !== 'com.yeshmishak.app') {
    throw new Error(`Invalid applicationId: expected 'com.yeshmishak.app', got '${metadata.applicationId}'`);
  }
  if (!metadata.versionName || !/^\d+\.\d+\.\d+$/.test(metadata.versionName)) {
    throw new Error(`Invalid versionName: '${metadata.versionName}' must follow semantic versioning.`);
  }
  if (!Number.isInteger(metadata.versionCode) || metadata.versionCode <= 0) {
    throw new Error(`Invalid versionCode: '${metadata.versionCode}' must be a positive integer.`);
  }
  const expectedRelease = `${metadata.applicationId}@${metadata.versionName}+${metadata.versionCode}`;
  if (metadata.release !== expectedRelease) {
    throw new Error(`Invalid release string: expected '${expectedRelease}', got '${metadata.release}'`);
  }
  const expectedDist = String(metadata.versionCode);
  if (metadata.dist !== expectedDist) {
    throw new Error(`Invalid dist string: expected '${expectedDist}', got '${metadata.dist}'`);
  }
  return metadata;
}

export function resolveMetadata(runGradle = () => spawnSync(gradlewCmd, [':app:printSentryMetadata', '-q'], { cwd: ANDROID_DIR, encoding: 'utf8', shell: isWindows })) {
  console.log('> Resolving Android metadata from Gradle...');
  const result = runGradle();

  if (result.error) {
    console.error(`Failed to execute gradle: ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`Gradle metadata extraction failed with exit code ${result.status}`);
    if (result.stderr) console.error(result.stderr);
    if (result.stdout) console.log(result.stdout);
    process.exit(result.status);
  }

  try {
    const metadata = extractJsonFromOutput(result.stdout);
    validateMetadata(metadata);
    console.log(`Resolved canonical metadata: release=${metadata.release}, dist=${metadata.dist}`);
    return metadata;
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
}

export function validateOfficialEnvironment(env, isOfficial) {
  if (isOfficial) {
    if (!env.SENTRY_AUTH_TOKEN) {
      throw new Error('ERROR: SENTRY_AUTH_TOKEN is required for official release builds.');
    }
    if (!env.SENTRY_ORG) {
      throw new Error('ERROR: SENTRY_ORG is required for official release builds.');
    }
    if (!env.SENTRY_MOBILE_PROJECT) {
      throw new Error('ERROR: SENTRY_MOBILE_PROJECT is required for official release builds.');
    }
  } else {
    if (!env.SENTRY_AUTH_TOKEN) {
      console.warn('WARNING: SENTRY_AUTH_TOKEN is missing. Source maps will NOT be uploaded.');
    }
  }
}

function main() {
  const isOfficial = process.argv.includes('--official');
  const metadata = resolveMetadata();

  try {
    validateOfficialEnvironment(process.env, isOfficial);
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }

  if (isOfficial) {
    process.env.VITE_SENTRY_ENVIRONMENT = 'production';
    process.env.ANDROID_OFFICIAL_RELEASE = 'true';
  }

  // Inject canonical metadata into environment
  process.env.VITE_SENTRY_RELEASE = metadata.release;
  process.env.VITE_SENTRY_DIST = metadata.dist;

  // Run web build
  runCommand('npm', ['run', 'build:android:web'], { cwd: FRONTEND_DIR, shell: isWindows });

  // Verify web bundle
  runCommand('npm', ['run', 'build:android:verify', '--', '--bundle-only'], { cwd: FRONTEND_DIR, shell: isWindows });

  // Sync Capacitor assets
  runCommand('npm', ['run', 'build:android:sync'], { cwd: FRONTEND_DIR, shell: isWindows });

  // Verify copied assets
  runCommand('npm', ['run', 'build:android:verify', '--', '--assets-only'], { cwd: FRONTEND_DIR, shell: isWindows });

  console.log('\n--- SUCCESS ---');
  console.log('Canonical Release: ' + metadata.release);
  console.log('Canonical Dist: ' + metadata.dist);
  console.log('Android assets successfully prepared. Ready for `gradlew bundleRelease` or similar.');
}

import url from 'node:url';
if (process.argv[1] && import.meta.url === url.pathToFileURL(process.argv[1]).href) {
  main();
}
