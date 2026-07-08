export const USE_CASES = {
  USER_MARKER: 'USER_MARKER',
  NEARBY_FIELDS: 'NEARBY_FIELDS',
  NAVIGATION_LAUNCH: 'NAVIGATION_LAUNCH',
  PROXIMITY_VALIDATION: 'PROXIMITY_VALIDATION',
}

const REQUIREMENTS = {
  [USE_CASES.USER_MARKER]: {
    requiredLevel: 'Medium',
    targetMeters: 100,
    maxAcceptableMeters: 500,
  },
  [USE_CASES.NEARBY_FIELDS]: {
    requiredLevel: 'Medium',
    targetMeters: 100,
    maxAcceptableMeters: 500,
  },
  [USE_CASES.NAVIGATION_LAUNCH]: {
    requiredLevel: 'Low',
    targetMeters: 500,
    maxAcceptableMeters: 2000,
  },
  [USE_CASES.PROXIMITY_VALIDATION]: {
    requiredLevel: 'High',
    targetMeters: 50,
    maxAcceptableMeters: 100,
  },
}

export function getAccuracyRequirement(useCase) {
  return REQUIREMENTS[useCase] || null
}

export function evaluateLocationAccuracy(location, useCase) {
  const req = getAccuracyRequirement(useCase)
  if (!req) {
    return {
      useCase,
      accuracyMeters: null,
      requiredLevel: 'unknown',
      targetMeters: null,
      maxAcceptableMeters: null,
      isAccurateEnough: false,
      isIdeal: false,
      severity: 'unknown',
      message: 'Invalid or unknown use case',
    }
  }

  // Support both accuracy and accuracyMeters property names
  const rawAccuracy = location ? (location.accuracy !== undefined ? location.accuracy : location.accuracyMeters) : undefined
  const isValid = typeof rawAccuracy === 'number' && Number.isFinite(rawAccuracy) && rawAccuracy > 0
  const accuracyMeters = typeof rawAccuracy === 'number' && Number.isFinite(rawAccuracy) ? rawAccuracy : null

  if (!isValid) {
    return {
      useCase,
      accuracyMeters,
      requiredLevel: req.requiredLevel,
      targetMeters: req.targetMeters,
      maxAcceptableMeters: req.maxAcceptableMeters,
      isAccurateEnough: false,
      isIdeal: false,
      severity: 'unknown',
      message: 'Location accuracy is unknown or invalid',
    }
  }

  const isIdeal = accuracyMeters <= req.targetMeters
  const isAccurateEnough = accuracyMeters <= req.maxAcceptableMeters

  let severity = 'poor'
  let message = 'Location accuracy is poor'

  if (isIdeal) {
    severity = 'ideal'
    message = 'Location accuracy is ideal'
  } else if (isAccurateEnough) {
    severity = 'acceptable'
    message = 'Location accuracy is acceptable'
  }

  return {
    useCase,
    accuracyMeters,
    requiredLevel: req.requiredLevel,
    targetMeters: req.targetMeters,
    maxAcceptableMeters: req.maxAcceptableMeters,
    isAccurateEnough,
    isIdeal,
    severity,
    message,
  }
}
