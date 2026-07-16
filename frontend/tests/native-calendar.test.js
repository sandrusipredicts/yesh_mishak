import assert from 'node:assert/strict'
import test from 'node:test'

import { openCalendarEventPrompt, toPluginPromptOptions } from '../src/api/nativeCalendar.js'

const START = new Date(Date.now() + 60 * 60 * 1000)
const END = new Date(Date.now() + 3 * 60 * 60 * 1000)

function makePayload(overrides = {}) {
  return {
    title: 'Football game — Central Court',
    description: 'Football at Central Court — Today, 20:00',
    location: 'Central Court',
    start: START,
    end: END,
    url: 'https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999',
    ...overrides,
  }
}

function createPlugin({ createError } = {}) {
  const calls = { createEventWithPrompt: [] }

  return {
    calls,
    plugin: {
      async createEventWithPrompt(options) {
        calls.createEventWithPrompt.push(options)
        if (createError) {
          throw createError
        }
        return { id: 'native-event-id' }
      },
    },
  }
}

// --- unsupported platform ---

test('returns unsupported and never touches the plugin when unavailable', async () => {
  const result = await openCalendarEventPrompt(makePayload(), { plugin: null })

  assert.deepEqual(result, { outcome: 'unsupported' })
})

// --- successful prompt open ---

test('opens the prompt and reports "opened", never a false "saved" outcome', async () => {
  const { plugin, calls } = createPlugin()

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.deepEqual(result, { outcome: 'opened' })
  assert.equal(calls.createEventWithPrompt.length, 1)
})

test('passes the mapped payload fields through to the plugin call', async () => {
  const { plugin, calls } = createPlugin()
  const payload = makePayload()

  await openCalendarEventPrompt(payload, { plugin })

  assert.deepEqual(calls.createEventWithPrompt[0], {
    title: payload.title,
    location: payload.location,
    description: payload.description,
    url: payload.url,
    startDate: payload.start.getTime(),
    endDate: payload.end.getTime(),
  })
})

// --- invalid payload (never calls the plugin) ---

test('returns failed and never calls the plugin for a payload with no valid start', async () => {
  const { plugin, calls } = createPlugin()

  const result = await openCalendarEventPrompt(makePayload({ start: null }), { plugin })

  assert.deepEqual(result, { outcome: 'failed', reason: 'invalid-payload' })
  assert.equal(calls.createEventWithPrompt.length, 0)
})

test('returns failed and never calls the plugin for a null payload', async () => {
  const { plugin, calls } = createPlugin()

  const result = await openCalendarEventPrompt(null, { plugin })

  assert.deepEqual(result, { outcome: 'failed', reason: 'invalid-payload' })
  assert.equal(calls.createEventWithPrompt.length, 0)
})

// --- cancellation is not an error ---

test('classifies a user-cancellation error as cancelled, not failed', async () => {
  const { plugin } = createPlugin({ createError: new Error('User cancelled the request.') })

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.deepEqual(result, { outcome: 'cancelled' })
})

// --- permission denial ---

test('classifies a permission-denied error as denied', async () => {
  const { plugin } = createPlugin({ createError: new Error('Calendar permission was denied.') })

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.deepEqual(result, { outcome: 'denied' })
})

// --- no compatible calendar app (Android ActivityNotFoundException) ---

test('classifies "no activity found" (no compatible calendar app) as unavailable, not a generic failure', async () => {
  const { plugin } = createPlugin({
    createError: new Error(
      'No Activity found to handle Intent { act=android.intent.action.INSERT dat=content://com.android.calendar/events (has extras) }',
    ),
  })

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.deepEqual(result, { outcome: 'unavailable', reason: 'no-calendar-app' })
})

// --- native failure, sanitized ---

test('returns a structured failure when the native call throws an unrecognized error', async () => {
  const { plugin } = createPlugin({ createError: new Error('native bridge exploded') })

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.equal(result.outcome, 'failed')
  assert.equal(result.reason, 'native bridge exploded')
})

test('never throws even when the native call rejects with a non-Error value', async () => {
  const { plugin } = createPlugin({ createError: 'plain string rejection' })

  const result = await openCalendarEventPrompt(makePayload(), { plugin })

  assert.equal(result.outcome, 'failed')
})

// --- option mapping ---

test('toPluginPromptOptions maps a payload to the plugin option shape', () => {
  const payload = makePayload()
  const options = toPluginPromptOptions(payload)

  assert.deepEqual(options, {
    title: payload.title,
    location: payload.location,
    description: payload.description,
    url: payload.url,
    startDate: payload.start.getTime(),
    endDate: payload.end.getTime(),
  })
})

test('toPluginPromptOptions never leaks undefined as the string "undefined"', () => {
  const options = toPluginPromptOptions({})

  assert.equal(options.title, '')
  assert.equal(options.location, '')
  assert.equal(options.description, '')
})
