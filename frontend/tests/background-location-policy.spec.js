import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const FRONTEND_ROOT = path.resolve(import.meta.dirname, '..')

function readFileIfExists(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf-8')
  } catch {
    return null
  }
}

function readSourceFiles(dir, extensions) {
  const results = []
  const excluded = new Set([
    'node_modules', 'dist', 'build', '.gradle', 'test-results',
    'playwright-report', '.capacitor', 'Pods',
  ])

  function walk(current) {
    let entries
    try {
      entries = fs.readdirSync(current, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      if (excluded.has(entry.name)) continue
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) {
        walk(full)
      } else if (extensions.some((ext) => entry.name.endsWith(ext))) {
        results.push(full)
      }
    }
  }

  walk(dir)
  return results
}

test('Android manifest does not declare ACCESS_BACKGROUND_LOCATION permission', () => {
  const manifestPath = path.join(
    FRONTEND_ROOT, 'android', 'app', 'src', 'main', 'AndroidManifest.xml',
  )
  const content = readFileIfExists(manifestPath)
  if (content === null) {
    test.skip()
    return
  }
  const permissionLines = content
    .split('\n')
    .filter((line) => line.includes('uses-permission') && !line.trimStart().startsWith('<!--'))
  for (const line of permissionLines) {
    expect(
      line.includes('ACCESS_BACKGROUND_LOCATION'),
      'AndroidManifest.xml must not declare ACCESS_BACKGROUND_LOCATION',
    ).toBe(false)
  }
})

test('iOS Info.plist does not contain Always Location keys', () => {
  const plistPath = path.join(FRONTEND_ROOT, 'ios', 'App', 'App', 'Info.plist')
  const content = readFileIfExists(plistPath)
  if (content === null) {
    test.skip()
    return
  }
  expect(content).not.toContain('NSLocationAlwaysUsageDescription')
  expect(content).not.toContain('NSLocationAlwaysAndWhenInUseUsageDescription')
})

test('no background-location plugins in package.json', () => {
  const pkgPath = path.join(FRONTEND_ROOT, 'package.json')
  const content = readFileIfExists(pkgPath)
  expect(content).not.toBeNull()

  const forbidden = [
    '@capacitor/background-runner',
    '@capacitor/background-task',
    'capacitor-background-geolocation',
    'cordova-plugin-background-geolocation',
  ]
  for (const pkg of forbidden) {
    expect(content).not.toContain(pkg)
  }
})

test('application source does not use watchPosition', () => {
  const srcDir = path.join(FRONTEND_ROOT, 'src')
  const files = readSourceFiles(srcDir, ['.js', '.jsx', '.ts', '.tsx'])

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8')
    const relative = path.relative(FRONTEND_ROOT, file)
    expect(
      content.includes('watchPosition'),
      `${relative} must not contain watchPosition`,
    ).toBe(false)
  }
})
