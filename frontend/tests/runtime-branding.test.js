import assert from 'node:assert/strict'
import test from 'node:test'

import en from '../src/locales/en/common.js'
import { normalizeBusinessName, replaceLegacyBranding } from '../src/branding/runtimeBranding.js'

test('replaceLegacyBranding injects dynamic business name into user-facing copy', () => {
  const businessName = 'ZOHAR'

  const welcomeTitle = replaceLegacyBranding(en.onboarding.welcome.title, businessName)
  const shareTitle = replaceLegacyBranding(en.game.share.title, businessName)

  assert.equal(welcomeTitle, `Welcome to ${businessName}`)
  assert.equal(shareTitle, `{{sport}} game at {{field}} - ${businessName}`)
  assert.equal(welcomeTitle.includes('Yesh Mishak'), false)
  assert.equal(shareTitle.includes('Yesh Mishak'), false)
})

test('normalizeBusinessName enforces safe fallback name', () => {
  assert.equal(normalizeBusinessName('  ZOHAR  '), 'ZOHAR')
  assert.equal(normalizeBusinessName('   ', 'Tenant Default'), 'Tenant Default')
  assert.equal(normalizeBusinessName('', ''), 'Business')
})

test('runtime brand update propagates through translation output', async () => {
  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
  }
  globalThis.navigator = { language: 'en', languages: ['en'] }
  globalThis.document = {
    documentElement: { lang: '', dir: '' },
    body: { dir: '' },
  }

  const i18nModule = await import('../src/i18n/index.js')

  i18nModule.setRuntimeBrandName('ZOHAR')
  const translated = i18nModule.default.t('onboarding.welcome.title')

  assert.equal(translated, 'Welcome to ZOHAR')
  assert.equal(translated.includes('Yesh Mishak'), false)
})
