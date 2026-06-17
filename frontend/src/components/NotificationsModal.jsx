import { useEffect, useRef, useState } from 'react'

import { getFields } from '../api/fields'
import {
  deletePushToken,
  getNotificationPreferences,
  savePushToken,
  sendTestPush,
  updateNotificationPreferences,
} from '../api/notifications'
import { israelCities } from '../data/israelCities'
import { requestFirebasePushToken } from '../firebaseMessaging'
import CityAutocomplete from './CityAutocomplete'

const DEFAULT_CITY = 'ירוחם'
const DEFAULT_RADIUS_KM = 5
const GEOLOCATION_TIMEOUT_MS = 15000
const GEOLOCATION_ERROR_GRACE_MS = 1200
const STORED_PUSH_TOKEN_KEY = 'firebase_push_token'

function getGeolocationErrorDetails(error) {
  if (!error || typeof error.code !== 'number') {
    return {
      code: 'UNKNOWN',
      label: 'UNKNOWN',
      message: 'Location failed without a browser error message.',
    }
  }

  const labels = {
    [error.PERMISSION_DENIED]: 'PERMISSION_DENIED',
    [error.POSITION_UNAVAILABLE]: 'POSITION_UNAVAILABLE',
    [error.TIMEOUT]: 'TIMEOUT',
  }

  return {
    code: error.code,
    label: labels[error.code] ?? 'UNKNOWN',
    message: error.message || 'The browser did not provide more details.',
  }
}

function formatGeolocationError(error) {
  const details = getGeolocationErrorDetails(error)

  if (details.label === 'PERMISSION_DENIED') {
    return `Location permission was denied. (${details.label}: ${details.message})`
  }

  if (details.label === 'POSITION_UNAVAILABLE') {
    return `The browser could not determine your current location. (${details.label}: ${details.message})`
  }

  if (details.label === 'TIMEOUT') {
    return `Location lookup timed out. (${details.label}: ${details.message})`
  }

  return `Could not get current location. (${details.label}: ${details.message})`
}

function getFieldLabel(field) {
  return field.name ?? field.title ?? `Field ${field.id}`
}

function parsePreferences(preferences) {
  const rows = Array.isArray(preferences) ? preferences : []
  const distancePreference = rows.find((preference) => preference.notification_type === 'radius')
  const cityPreference = rows.find((preference) => preference.notification_type === 'city')
  const fieldPreferences = rows.filter(
    (preference) => preference.notification_type === 'specific_field',
  )

  return {
    distanceEnabled: distancePreference?.enabled ?? true,
    distanceRadiusKm: Number(distancePreference?.radius_km ?? DEFAULT_RADIUS_KM),
    distanceLat: distancePreference?.lat ?? null,
    distanceLng: distancePreference?.lng ?? null,
    cityEnabled: cityPreference?.enabled ?? false,
    cityName: cityPreference?.city ?? DEFAULT_CITY,
    specificFieldsEnabled: fieldPreferences.some((preference) => preference.enabled),
    selectedFieldIds: fieldPreferences
      .filter((preference) => preference.enabled)
      .map((preference) => preference.field_id)
      .filter(Boolean),
  }
}

function NotificationsModal({
  fields = [],
  onClose,
}) {
  const isSavingRef = useRef(false)
  const [availableFields, setAvailableFields] = useState(fields)
  const [distanceEnabled, setDistanceEnabled] = useState(true)
  const [distanceRadiusKm, setDistanceRadiusKm] = useState(DEFAULT_RADIUS_KM)
  const [cityEnabled, setCityEnabled] = useState(false)
  const [cityName, setCityName] = useState(DEFAULT_CITY)
  const [specificFieldsEnabled, setSpecificFieldsEnabled] = useState(false)
  const [selectedFieldIds, setSelectedFieldIds] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isPushSaving, setIsPushSaving] = useState(false)
  const [pushToken, setPushToken] = useState(
    () => localStorage.getItem(STORED_PUSH_TOKEN_KEY) || '',
  )
  const [error, setError] = useState('')
  const [savedMessage, setSavedMessage] = useState('')
  const [pushMessage, setPushMessage] = useState('')
  useEffect(() => {
    let isMounted = true

    async function loadPreferences() {
      setIsLoading(true)
      setError('')

      try {
        const [preferences, loadedFields] = await Promise.all([
          getNotificationPreferences(),
          fields.length ? Promise.resolve(fields) : getFields(),
        ])

        if (!isMounted) {
          return
        }

        const parsedPreferences = parsePreferences(preferences)
        setDistanceEnabled(parsedPreferences.distanceEnabled)
        setDistanceRadiusKm(parsedPreferences.distanceRadiusKm)
        setCityEnabled(parsedPreferences.cityEnabled)
        setCityName(parsedPreferences.cityName)
        setSpecificFieldsEnabled(parsedPreferences.specificFieldsEnabled)
        setSelectedFieldIds(parsedPreferences.selectedFieldIds)
        setAvailableFields(Array.isArray(loadedFields) ? loadedFields : [])
      } catch {
        if (isMounted) {
          setError('Could not load notification preferences.')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadPreferences()

    return () => {
      isMounted = false
    }
  }, [fields])

  function toggleSelectedField(fieldId) {
    setSelectedFieldIds((currentFieldIds) =>
      currentFieldIds.includes(fieldId)
        ? currentFieldIds.filter((currentFieldId) => currentFieldId !== fieldId)
        : [...currentFieldIds, fieldId],
    )
  }

  function getCurrentLocation() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Browser location is not available.'))
        return
      }

      let isSettled = false
      let pendingErrorTimer = null
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (isSettled) {
            return
          }

          if (pendingErrorTimer) {
            clearTimeout(pendingErrorTimer)
            pendingErrorTimer = null
          }

          isSettled = true
          const lat = position.coords.latitude
          const lng = position.coords.longitude
          resolve({
            lat,
            lng,
          })
        },
        (geolocationError) => {
          if (isSettled) {
            return
          }

          if (pendingErrorTimer) {
            return
          }

          pendingErrorTimer = setTimeout(() => {
            if (isSettled) {
              return
            }

            isSettled = true
            pendingErrorTimer = null
            reject(new Error(formatGeolocationError(geolocationError)))
          }, GEOLOCATION_ERROR_GRACE_MS)
        },
        {
          enableHighAccuracy: false,
          timeout: GEOLOCATION_TIMEOUT_MS,
          maximumAge: 0,
        },
      )
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (isSavingRef.current) {
      return
    }

    isSavingRef.current = true
    setIsSaving(true)
    setError('')
    setSavedMessage('')

    try {
      const trimmedCity = cityName.trim()
      const isValidCity = israelCities.includes(trimmedCity)

      if (cityEnabled && !isValidCity) {
        setError('Please pick a city from the suggestions.')
        return
      }

      let nextDistanceLat = null
      let nextDistanceLng = null
      let nextDistanceEnabled = false
      let locationErrorMessage = ''

      if (distanceEnabled) {
        try {
          const currentLocation = await getCurrentLocation()
          nextDistanceLat = currentLocation.lat
          nextDistanceLng = currentLocation.lng
          nextDistanceEnabled = true
        } catch (locationError) {
          locationErrorMessage = locationError.message
          nextDistanceEnabled = false
          nextDistanceLat = null
          nextDistanceLng = null
        }
      }

      const notificationPayload = {
        distance_enabled: nextDistanceEnabled,
        distance_radius_km: Number(distanceRadiusKm),
        distance_lat: nextDistanceLat,
        distance_lng: nextDistanceLng,
        city_enabled: cityEnabled,
        city_name: isValidCity ? trimmedCity : DEFAULT_CITY,
        specific_fields_enabled: specificFieldsEnabled,
        selected_field_ids: selectedFieldIds,
      }

      await updateNotificationPreferences(notificationPayload)
      if (locationErrorMessage) {
        setError(`${locationErrorMessage} Distance notifications were not enabled.`)
        setSavedMessage('City and specific field preferences saved.')
      } else {
        setSavedMessage('Notification preferences saved.')
      }
    } catch (saveError) {
      setError(saveError.message || 'Could not save notification preferences.')
    } finally {
      isSavingRef.current = false
      setIsSaving(false)
    }
  }

  async function handleEnablePush() {
    setIsPushSaving(true)
    setError('')
    setPushMessage('')

    try {
      const token = await requestFirebasePushToken()
      await savePushToken(token)
      localStorage.setItem(STORED_PUSH_TOKEN_KEY, token)
      setPushToken(token)
      setPushMessage('Push notifications enabled on this browser.')
    } catch (pushError) {
      setError(pushError.message || 'Could not enable push notifications.')
    } finally {
      setIsPushSaving(false)
    }
  }

  async function handleDisablePush() {
    setIsPushSaving(true)
    setError('')
    setPushMessage('')

    try {
      await deletePushToken(pushToken)
      localStorage.removeItem(STORED_PUSH_TOKEN_KEY)
      setPushToken('')
      setPushMessage('Push notifications disabled on this browser.')
    } catch (pushError) {
      setError(pushError.message || 'Could not disable push notifications.')
    } finally {
      setIsPushSaving(false)
    }
  }

  async function handleTestPush() {
    setIsPushSaving(true)
    setError('')
    setPushMessage('')

    try {
      await sendTestPush()
      setPushMessage('Test push sent.')
    } catch (pushError) {
      const detail = pushError?.response?.data?.detail
      setError(detail || pushError.message || 'Could not send test push.')
    } finally {
      setIsPushSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="notifications-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-preferences-title"
      >
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
          x
        </button>

        <h2 id="notification-preferences-title">Notification Preferences</h2>

        {isLoading ? (
          <p className="settings-loading">Loading preferences...</p>
        ) : (
          <>
            <section className="settings-section">
              <div className="push-actions">
                <button
                  className="secondary-panel-button"
                  type="button"
                  onClick={pushToken ? handleDisablePush : handleEnablePush}
                  disabled={isPushSaving}
                >
                  {pushToken ? 'Disable push' : 'Enable push'}
                </button>
                <button
                  className="secondary-panel-button"
                  type="button"
                  onClick={handleTestPush}
                  disabled={isPushSaving || !pushToken}
                >
                  Test push
                </button>
              </div>
              {pushMessage ? <p className="modal-success">{pushMessage}</p> : null}
            </section>

            <form className="notifications-form" onSubmit={handleSubmit}>
              <section className="settings-section">
                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={distanceEnabled}
                    onChange={(event) => setDistanceEnabled(event.target.checked)}
                  />
                  Distance notifications
                </label>
                <label className="settings-range">
                  Radius: {distanceRadiusKm} km
                  <input
                    type="range"
                    min="1"
                    max="20"
                    value={distanceRadiusKm}
                    onChange={(event) => setDistanceRadiusKm(event.target.value)}
                    disabled={!distanceEnabled}
                  />
                </label>
              </section>

              <section className="settings-section">
                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={cityEnabled}
                    onChange={(event) => setCityEnabled(event.target.checked)}
                  />
                  City notifications
                </label>
                <div className="settings-input">
                  <label htmlFor="notifications-city-input">City</label>
                  <CityAutocomplete
                    id="notifications-city-input"
                    value={cityName}
                    onChange={setCityName}
                    disabled={!cityEnabled}
                    cities={israelCities}
                  />
                </div>
              </section>

              <section className="settings-section">
                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={specificFieldsEnabled}
                    onChange={(event) => setSpecificFieldsEnabled(event.target.checked)}
                  />
                  Specific fields notifications
                </label>

                <div className="field-selection-list">
                  {availableFields.length ? (
                    availableFields.map((field) => (
                      <label className="field-selection-option" key={field.id}>
                        <input
                          type="checkbox"
                          checked={selectedFieldIds.includes(field.id)}
                          onChange={() => toggleSelectedField(field.id)}
                          disabled={!specificFieldsEnabled}
                        />
                        {getFieldLabel(field)}
                      </label>
                    ))
                  ) : (
                    <p>No fields available.</p>
                  )}
                </div>
              </section>

              {error ? <p className="modal-error">{error}</p> : null}
              {savedMessage ? <p className="modal-success">{savedMessage}</p> : null}

              <button className="primary-panel-button" type="submit" disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            </form>
          </>
        )}
      </section>
    </div>
  )
}

export default NotificationsModal
