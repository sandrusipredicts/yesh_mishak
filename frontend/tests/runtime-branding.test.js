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
