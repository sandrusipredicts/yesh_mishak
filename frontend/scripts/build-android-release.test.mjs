import { test } from 'node:test';
import assert from 'node:assert';
import { extractJsonFromOutput, validateMetadata } from './build-android-release.mjs';

test('extractJsonFromOutput extracts valid JSON correctly', () => {
  const output = `Some gradle logging
===SENTRY_METADATA_START===
{ "applicationId": "test" }
===SENTRY_METADATA_END===
More logging`;
  const result = extractJsonFromOutput(output);
  assert.deepStrictEqual(result, { applicationId: 'test' });
});

test('extractJsonFromOutput throws on missing marker', () => {
  const output = `Some gradle logging
===SENTRY_METADATA_START===
{ "applicationId": "test" }`;
  assert.throws(() => extractJsonFromOutput(output), /Failed to locate metadata JSON boundaries/);
});

test('extractJsonFromOutput throws on duplicate markers', () => {
  const output = `
===SENTRY_METADATA_START===
{}
===SENTRY_METADATA_END===
===SENTRY_METADATA_START===
{}
===SENTRY_METADATA_END===
  `;
  assert.throws(() => extractJsonFromOutput(output), /Duplicate metadata markers/);
});

test('extractJsonFromOutput throws on malformed JSON', () => {
  const output = `
===SENTRY_METADATA_START===
{ "app": }
===SENTRY_METADATA_END===
`;
  assert.throws(() => extractJsonFromOutput(output), /Failed to parse metadata JSON/);
});

test('validateMetadata passes valid metadata', () => {
  const valid = {
    applicationId: 'com.yeshmishak.app',
    versionName: '1.2.3',
    versionCode: 42,
    release: 'com.yeshmishak.app@1.2.3+42',
    dist: '42'
  };
  assert.deepStrictEqual(validateMetadata(valid), valid);
});

test('validateMetadata throws on wrong applicationId', () => {
  assert.throws(() => validateMetadata({
    applicationId: 'com.wrong.app',
    versionName: '1.2.3', versionCode: 42, release: 'com.wrong.app@1.2.3+42', dist: '42'
  }), /Invalid applicationId/);
});

test('validateMetadata throws on empty or invalid versionName', () => {
  const base = { applicationId: 'com.yeshmishak.app', versionCode: 1, dist: '1', release: 'com.yeshmishak.app@1.0+1' };
  assert.throws(() => validateMetadata({ ...base, versionName: '' }), /Invalid versionName/);
  assert.throws(() => validateMetadata({ ...base, versionName: '1.0' }), /Invalid versionName/);
  assert.throws(() => validateMetadata({ ...base, versionName: 'v1.0.0' }), /Invalid versionName/);
});

test('validateMetadata throws on invalid versionCode', () => {
  const base = { applicationId: 'com.yeshmishak.app', versionName: '1.0.0', dist: '1', release: 'com.yeshmishak.app@1.0.0+1' };
  assert.throws(() => validateMetadata({ ...base, versionCode: 0 }), /Invalid versionCode/);
  assert.throws(() => validateMetadata({ ...base, versionCode: -5 }), /Invalid versionCode/);
  assert.throws(() => validateMetadata({ ...base, versionCode: 1.5 }), /Invalid versionCode/);
  assert.throws(() => validateMetadata({ ...base, versionCode: '1' }), /Invalid versionCode/);
});

test('validateMetadata throws on release mismatch', () => {
  const base = { applicationId: 'com.yeshmishak.app', versionName: '1.0.0', versionCode: 1, dist: '1' };
  assert.throws(() => validateMetadata({ ...base, release: 'com.yeshmishak.app@1.0.0' }), /Invalid release string/);
  assert.throws(() => validateMetadata({ ...base, release: 'wrong' }), /Invalid release string/);
});

test('validateMetadata throws on dist mismatch', () => {
  const base = { applicationId: 'com.yeshmishak.app', versionName: '1.0.0', versionCode: 1, release: 'com.yeshmishak.app@1.0.0+1' };
  assert.throws(() => validateMetadata({ ...base, dist: '2' }), /Invalid dist string/);
  assert.throws(() => validateMetadata({ ...base, dist: 1 }), /Invalid dist string/); // must be string
});


import { validateOfficialEnvironment } from './build-android-release.mjs';
test('validateOfficialEnvironment handles valid and invalid envs', () => {
  assert.throws(() => validateOfficialEnvironment({}, true), /SENTRY_AUTH_TOKEN is required/);
  assert.throws(() => validateOfficialEnvironment({ SENTRY_AUTH_TOKEN: '1' }, true), /SENTRY_ORG is required/);
  assert.throws(() => validateOfficialEnvironment({ SENTRY_AUTH_TOKEN: '1', SENTRY_ORG: 'a' }, true), /SENTRY_MOBILE_PROJECT is required/);
  assert.doesNotThrow(() => validateOfficialEnvironment({ SENTRY_AUTH_TOKEN: '1', SENTRY_ORG: 'a', SENTRY_MOBILE_PROJECT: 'p' }, true));
  assert.doesNotThrow(() => validateOfficialEnvironment({}, false));
});
