// E09-02: client-side mirror of the backend analytics event registry
// (backend/app/analytics/registry.py). Keeps malformed payloads from ever
// leaving the device; the backend registry remains the authoritative
// contract. Extend both together (plus the CHECK constraints in
// backend/migrations/analytics_events.sql) when new events are approved.
//
// Privacy envelope (owner decision D1): events are strictly anonymous.
// Never declare properties that could carry user IDs, resource IDs, URLs,
// coordinates, or free text -- only closed enums of coarse values.

export const SCREEN_NAMES = Object.freeze([
  'map',
  'game_details',
  'profile',
  'notifications',
  'admin',
])

// Seed events approved in owner decision D2.
const EVENT_REGISTRY = Object.freeze({
  app_open: Object.freeze({}),
  screen_view: Object.freeze({
    screen: Object.freeze({ allowedValues: SCREEN_NAMES, required: true }),
  }),
})

export function isRegisteredEvent(eventName) {
  return Object.prototype.hasOwnProperty.call(EVENT_REGISTRY, eventName)
}

export function validateEvent(eventName, properties = {}) {
  if (!isRegisteredEvent(eventName)) {
    return [`unknown event_name: ${eventName}`]
  }
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    return ['properties must be a plain object']
  }

  const errors = []
  const spec = EVENT_REGISTRY[eventName]

  for (const propertyName of Object.keys(properties)) {
    if (!Object.prototype.hasOwnProperty.call(spec, propertyName)) {
      errors.push(`unknown property ${propertyName} for event ${eventName}`)
    }
  }

  for (const [propertyName, propertySpec] of Object.entries(spec)) {
    if (!Object.prototype.hasOwnProperty.call(properties, propertyName)) {
      if (propertySpec.required) {
        errors.push(`missing required property ${propertyName} for event ${eventName}`)
      }
      continue
    }

    const value = properties[propertyName]
    if (typeof value !== 'string') {
      errors.push(`property ${propertyName} for event ${eventName} must be a string`)
      continue
    }
    if (!propertySpec.allowedValues.includes(value)) {
      errors.push(`invalid value for property ${propertyName} of event ${eventName}`)
    }
  }

  return errors
}

export function isValidEvent(eventName, properties = {}) {
  return validateEvent(eventName, properties).length === 0
}

// App-level route -> approved screen name. Routes without an approved enum
// value (my-games, my-reports) are intentionally not tracked; the
// 'game_details' and 'notifications' enum values are reserved for later
// modal-level instrumentation (wiring them now would require touching
// MapPage/NotificationsModal, which E09-02 must not modify).
export function screenNameForPathname(pathname) {
  if (pathname === '/') {
    return 'map'
  }
  if (pathname === '/admin') {
    return 'admin'
  }
  if (pathname === '/settings') {
    return 'profile'
  }
  return null
}
