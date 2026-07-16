import { israelCities } from '../data/israelCities.js'
import {
  ONBOARDING_STEPS,
  ONBOARDING_VERSION,
  PERMISSION_OUTCOMES,
} from './onboardingSteps.js'

export const ONBOARDING_STORAGE_KEY = 'onboarding_state'
export const LEGACY_ONBOARDING_DONE_KEY = 'onboarding_done'
export const LEGACY_CITY_KEY = 'userCity'

function storageAvailable(storage) {
  return storage && typeof storage.getItem === 'function' && typeof storage.setItem === 'function'
}
function isValidCity(city) {
  return typeof city === 'string' && israelCities.includes(city.trim())
}

function isValidOutcome(value) {
  return PERMISSION_OUTCOMES.includes(value)
}

function createState(overrides = {}) {
  const now = new Date().toISOString()
  return {
    version: ONBOARDING_VERSION,
    status: 'in_progress',
    currentStep: ONBOARDING_STEPS[0],
    completedSteps: [],
    city: '',
    locationPermission: 'pending',
    notificationPermission: 'pending',
    startedAt: now,
    updatedAt: now,
    completedAt: null,
    ...overrides,
  }
}

export function validateOnboardingState(value) {
  if (!value || typeof value !== 'object' || value.version !== ONBOARDING_VERSION) return null
  if (!['in_progress', 'completed'].includes(value.status)) return null
  if (!ONBOARDING_STEPS.includes(value.currentStep)) return null
  if (!Array.isArray(value.completedSteps)) return null
  if (!value.completedSteps.every((step) => ONBOARDING_STEPS.includes(step))) return null
  if (value.city && !isValidCity(value.city)) return null
  if (!isValidOutcome(value.locationPermission)) return null
  if (!isValidOutcome(value.notificationPermission)) return null

  return createState({
    ...value,
    city: value.city?.trim() || '',
    completedSteps: [...new Set(value.completedSteps)],
  })
}

export function resolveOnboardingState(storage = globalThis.localStorage) {
  if (!storageAvailable(storage)) {
    return { state: createState(), persisted: false, migrated: false }
  }

  try {
    const raw = storage.getItem(ONBOARDING_STORAGE_KEY)
    if (raw) {
      const parsed = validateOnboardingState(JSON.parse(raw))
      if (parsed) return { state: parsed, persisted: true, migrated: false }
    }

    const legacyCity = storage.getItem(LEGACY_CITY_KEY)?.trim() || ''
    const legacyDone = storage.getItem(LEGACY_ONBOARDING_DONE_KEY) === 'true'
    const hasLanguage = storage.getItem('language_selected') === 'true'
      || ['he', 'en'].includes(storage.getItem('app_language'))
    const canMigrateCompleted = legacyDone || (hasLanguage && isValidCity(legacyCity))

    if (canMigrateCompleted) {
      const completed = createState({
        status: 'completed',
        currentStep: 'ready',
        completedSteps: [...ONBOARDING_STEPS],
        city: isValidCity(legacyCity) ? legacyCity : '',
        locationPermission: 'skipped',
        notificationPermission: 'skipped',
        completedAt: new Date().toISOString(),
      })
      storage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(completed))
      return { state: completed, persisted: true, migrated: true }
    }

    return {
      state: createState({ city: isValidCity(legacyCity) ? legacyCity : '' }),
      persisted: true,
      migrated: false,
    }
  } catch {
    return { state: createState(), persisted: false, migrated: false }
  }
}

export function saveOnboardingState(state, storage = globalThis.localStorage) {
  const validated = validateOnboardingState({
    ...state,
    version: ONBOARDING_VERSION,
    updatedAt: new Date().toISOString(),
  })
  if (!validated || !storageAvailable(storage)) return { ok: false, state }

  try {
    storage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(validated))
    if (validated.city) storage.setItem(LEGACY_CITY_KEY, validated.city)
    if (validated.status === 'completed') {
      storage.setItem(LEGACY_ONBOARDING_DONE_KEY, 'true')
    }
    return { ok: true, state: validated }
  } catch {
    return { ok: false, state: validated }
  }
}

export function completeOnboardingState(state, storage = globalThis.localStorage) {
  return saveOnboardingState({
    ...state,
    status: 'completed',
    currentStep: 'ready',
    completedSteps: [...ONBOARDING_STEPS],
    completedAt: new Date().toISOString(),
  }, storage)
}
