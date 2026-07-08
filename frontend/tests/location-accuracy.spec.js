import { test, expect } from '@playwright/test'
import { evaluateLocationAccuracy, getAccuracyRequirement, USE_CASES } from '../src/utils/locationAccuracy'

test.describe('Location Accuracy Utility Unit Tests', () => {
  test('getAccuracyRequirement returns correct thresholds for all use cases', () => {
    expect(getAccuracyRequirement(USE_CASES.USER_MARKER)).toEqual({
      requiredLevel: 'Medium',
      targetMeters: 100,
      maxAcceptableMeters: 500,
    })

    expect(getAccuracyRequirement(USE_CASES.NEARBY_FIELDS)).toEqual({
      requiredLevel: 'Medium',
      targetMeters: 100,
      maxAcceptableMeters: 500,
    })

    expect(getAccuracyRequirement(USE_CASES.NAVIGATION_LAUNCH)).toEqual({
      requiredLevel: 'Low',
      targetMeters: 500,
      maxAcceptableMeters: 2000,
    })

    expect(getAccuracyRequirement(USE_CASES.PROXIMITY_VALIDATION)).toEqual({
      requiredLevel: 'High',
      targetMeters: 50,
      maxAcceptableMeters: 100,
    })

    expect(getAccuracyRequirement('INVALID_USE_CASE')).toBeNull()
  })

  test('evaluateLocationAccuracy handles ideal accuracy', () => {
    const loc = { accuracy: 30 }
    const result = evaluateLocationAccuracy(loc, USE_CASES.PROXIMITY_VALIDATION)
    expect(result).toEqual({
      useCase: USE_CASES.PROXIMITY_VALIDATION,
      accuracyMeters: 30,
      requiredLevel: 'High',
      targetMeters: 50,
      maxAcceptableMeters: 100,
      isAccurateEnough: true,
      isIdeal: true,
      severity: 'ideal',
      message: 'Location accuracy is ideal',
    })
  })

  test('evaluateLocationAccuracy handles acceptable accuracy', () => {
    const loc = { accuracy: 80 }
    const result = evaluateLocationAccuracy(loc, USE_CASES.PROXIMITY_VALIDATION)
    expect(result).toEqual({
      useCase: USE_CASES.PROXIMITY_VALIDATION,
      accuracyMeters: 80,
      requiredLevel: 'High',
      targetMeters: 50,
      maxAcceptableMeters: 100,
      isAccurateEnough: true,
      isIdeal: false,
      severity: 'acceptable',
      message: 'Location accuracy is acceptable',
    })
  })

  test('evaluateLocationAccuracy handles poor accuracy', () => {
    const loc = { accuracy: 150 }
    const result = evaluateLocationAccuracy(loc, USE_CASES.PROXIMITY_VALIDATION)
    expect(result).toEqual({
      useCase: USE_CASES.PROXIMITY_VALIDATION,
      accuracyMeters: 150,
      requiredLevel: 'High',
      targetMeters: 50,
      maxAcceptableMeters: 100,
      isAccurateEnough: false,
      isIdeal: false,
      severity: 'poor',
      message: 'Location accuracy is poor',
    })
  })

  test('evaluateLocationAccuracy handles missing accuracy', () => {
    const loc = {}
    const result = evaluateLocationAccuracy(loc, USE_CASES.PROXIMITY_VALIDATION)
    expect(result).toEqual({
      useCase: USE_CASES.PROXIMITY_VALIDATION,
      accuracyMeters: null,
      requiredLevel: 'High',
      targetMeters: 50,
      maxAcceptableMeters: 100,
      isAccurateEnough: false,
      isIdeal: false,
      severity: 'unknown',
      message: 'Location accuracy is unknown or invalid',
    })
  })

  test('evaluateLocationAccuracy handles invalid accuracy values', () => {
    const testCases = [
      { accuracy: null },
      { accuracy: undefined },
      { accuracy: '30' },
      { accuracy: -10 },
      { accuracy: 0 },
      { accuracy: NaN },
      null,
    ]

    for (const loc of testCases) {
      const result = evaluateLocationAccuracy(loc, USE_CASES.USER_MARKER)
      expect(result.isAccurateEnough).toBe(false)
      expect(result.isIdeal).toBe(false)
      expect(result.severity).toBe('unknown')
      const raw = loc?.accuracy
      const expectedAccuracy = typeof raw === 'number' && Number.isFinite(raw) ? raw : null
      expect(result.accuracyMeters).toBe(expectedAccuracy)
    }
  })

  test('evaluateLocationAccuracy fallback support for accuracyMeters property name', () => {
    const loc = { accuracyMeters: 40 }
    const result = evaluateLocationAccuracy(loc, USE_CASES.PROXIMITY_VALIDATION)
    expect(result.accuracyMeters).toBe(40)
    expect(result.isIdeal).toBe(true)
    expect(result.severity).toBe('ideal')
  })
})
