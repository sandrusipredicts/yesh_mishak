import assert from 'node:assert/strict'
import test from 'node:test'

import { israelCities } from '../src/data/israelCities.js'
import {
  completeOnboardingState,
  ONBOARDING_STORAGE_KEY,
  resolveOnboardingState,
  saveOnboardingState,
} from '../src/onboarding/onboardingStorage.js'

function createStorage(seed = {}, { failReads = false, failWrites = false } = {}) {
  const values = new Map(Object.entries(seed))
  return {
    getItem(key) {
      if (failReads) throw new Error('read failed')
      return values.has(key) ? values.get(key) : null
    },
    setItem(key, value) {
      if (failWrites) throw new Error('write failed')
      values.set(key, String(value))
    },
    value(key) { return values.get(key) },
  }
}

test('starts a new six-step state without storing coordinates', () => {
  const { state } = resolveOnboardingState(createStorage())
  assert.equal(state.currentStep, 'welcome')
  assert.equal(state.locationPermission, 'pending')
  assert.equal(state.notificationPermission, 'pending')
  assert.equal('latitude' in state, false)
  assert.equal('longitude' in state, false)
})

test('migrates legacy completed users without forcing the walkthrough', () => {
  const storage = createStorage({
    onboarding_done: 'true',
    userCity: israelCities[0],
    app_language: 'he',
  })
  const result = resolveOnboardingState(storage)
  assert.equal(result.state.status, 'completed')
  assert.equal(result.state.city, israelCities[0])
  assert.equal(result.migrated, true)
  assert.ok(storage.value(ONBOARDING_STORAGE_KEY))
})

test('migrates a valid language and city even without the legacy completion marker', () => {
  const result = resolveOnboardingState(createStorage({
    language_selected: 'true',
    userCity: israelCities[1],
  }))
  assert.equal(result.state.status, 'completed')
  assert.equal(result.state.city, israelCities[1])
})

test('resumes valid partial progress and permission outcomes', () => {
  const storage = createStorage()
  const initial = resolveOnboardingState(storage).state
  const saved = saveOnboardingState({
    ...initial,
    currentStep: 'notifications',
    completedSteps: ['welcome', 'city', 'location'],
    city: israelCities[2],
    locationPermission: 'denied',
  }, storage)
  assert.equal(saved.ok, true)
  const resumed = resolveOnboardingState(storage).state
  assert.equal(resumed.currentStep, 'notifications')
  assert.equal(resumed.locationPermission, 'denied')
})

test('invalid JSON and unsupported versions reset safely', () => {
  const invalid = resolveOnboardingState(createStorage({ onboarding_state: '{bad' }))
  assert.equal(invalid.state.currentStep, 'welcome')

  const future = resolveOnboardingState(createStorage({
    onboarding_state: JSON.stringify({ version: 999, status: 'completed' }),
  }))
  assert.equal(future.state.version, 1)
  assert.equal(future.state.status, 'in_progress')
})

test('write failure is reported and completion is not claimed', () => {
  const storage = createStorage({}, { failWrites: true })
  const state = resolveOnboardingState(storage).state
  assert.equal(saveOnboardingState({ ...state, city: israelCities[0] }, storage).ok, false)
  assert.equal(completeOnboardingState({ ...state, city: israelCities[0] }, storage).ok, false)
})

test('storage read failure does not crash state resolution', () => {
  const result = resolveOnboardingState(createStorage({}, { failReads: true }))
  assert.equal(result.persisted, false)
  assert.equal(result.state.currentStep, 'welcome')
})
