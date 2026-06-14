import { useEffect, useState } from 'react'

import { getFields } from '../api/fields'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
} from '../api/notifications'

const DEFAULT_CITY = 'ירוחם'
const DEFAULT_RADIUS_KM = 5
const GEOLOCATION_TIMEOUT_MS = 15000

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
      .map((preference) => preference.field_id)
      .filter(Boolean),
  }
}

function NotificationsModal({ fields = [], onClose }) {
  const [availableFields, setAvailableFields] = useState(fields)
  const [distanceEnabled, setDistanceEnabled] = useState(true)
  const [distanceRadiusKm, setDistanceRadiusKm] = useState(DEFAULT_RADIUS_KM)
  const [distanceLat, setDistanceLat] = useState(null)
  const [distanceLng, setDistanceLng] = useState(null)
  const [cityEnabled, setCityEnabled] = useState(false)
  const [cityName, setCityName] = useState(DEFAULT_CITY)
  const [specificFieldsEnabled, setSpecificFieldsEnabled] = useState(false)
  const [selectedFieldIds, setSelectedFieldIds] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [savedMessage, setSavedMessage] = useState('')

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
        setDistanceLat(parsedPreferences.distanceLat)
        setDistanceLng(parsedPreferences.distanceLng)
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

      console.log('Requesting geolocation for radius notifications')
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const lat = position.coords.latitude
          const lng = position.coords.longitude
          console.log('Geolocation success', lat, lng)
          resolve({
            lat,
            lng,
          })
        },
        (geolocationError) => {
          const details = getGeolocationErrorDetails(geolocationError)
          console.error('Geolocation failed', {
            code: details.code,
            label: details.label,
            message: details.message,
          })
          reject(new Error(formatGeolocationError(geolocationError)))
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

    setIsSaving(true)
    setError('')
    setSavedMessage('')

    try {
      let nextDistanceLat = distanceLat
      let nextDistanceLng = distanceLng
      let nextDistanceEnabled = distanceEnabled
      let locationErrorMessage = ''

      if (distanceEnabled) {
        try {
          const currentLocation = await getCurrentLocation()
          nextDistanceLat = currentLocation.lat
          nextDistanceLng = currentLocation.lng
          setDistanceLat(nextDistanceLat)
          setDistanceLng(nextDistanceLng)
        } catch (locationError) {
          locationErrorMessage = locationError.message
          nextDistanceEnabled = false
          nextDistanceLat = null
          nextDistanceLng = null
          setDistanceLat(null)
          setDistanceLng(null)
        }
      }

      await updateNotificationPreferences({
        distance_enabled: nextDistanceEnabled,
        distance_radius_km: Number(distanceRadiusKm),
        distance_lat: nextDistanceLat,
        distance_lng: nextDistanceLng,
        city_enabled: cityEnabled,
        city_name: cityName.trim() || DEFAULT_CITY,
        specific_fields_enabled: specificFieldsEnabled,
        selected_field_ids: selectedFieldIds,
      })
      if (locationErrorMessage) {
        setError(`${locationErrorMessage} Distance notifications were not enabled.`)
        setSavedMessage('City and specific field preferences saved.')
      } else {
        setSavedMessage('Notification preferences saved.')
      }
    } catch (saveError) {
      setError(saveError.message || 'Could not save notification preferences.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="notifications-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notifications-title"
      >
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
          x
        </button>

        <h2 id="notifications-title">Notification settings</h2>

        {isLoading ? (
          <p className="settings-loading">Loading preferences...</p>
        ) : (
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
              <label className="settings-input">
                City
                <input
                  type="text"
                  value={cityName}
                  onChange={(event) => setCityName(event.target.value)}
                  disabled={!cityEnabled}
                />
              </label>
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
        )}
      </section>
    </div>
  )
}

export default NotificationsModal
