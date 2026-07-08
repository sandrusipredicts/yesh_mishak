import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import Modal from './Modal'
import CityAutocomplete from './CityAutocomplete'

import { createField } from '../api/fields'
import { getApiErrorMessage } from '../api/errors'
import { getCurrentLocation } from '../api/locationService'
import { israelCities } from '../data/israelCities'

// Display-only fallback so the map has something to render before the user
// has chosen a real field location. This must never be submitted as a
// field's actual coordinates or used to infer a city.
const MAP_DISPLAY_FALLBACK_CENTER = [31.4, 35.0]
const MAP_DISPLAY_FALLBACK_ZOOM = 7
const SELECTED_LOCATION_ZOOM = 15

const locationPinIcon = L.divIcon({
  className: 'location-picker-pin-icon',
  html: '<div class="location-picker-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
})

function LocationClickHandler({ onPositionChange }) {
  const map = useMap()

  useMapEvents({
    click(event) {
      const nextPosition = [event.latlng.lat, event.latlng.lng]
      onPositionChange(nextPosition)
      map.panTo(nextPosition)
    },
  })

  return null
}

function LocationPicker({ position, onPositionChange }) {
  return (
    <Marker
      draggable
      eventHandlers={{
        dragend(event) {
          const markerPosition = event.target.getLatLng()
          onPositionChange([markerPosition.lat, markerPosition.lng])
        },
      }}
      icon={locationPinIcon}
      position={position}
    />
  )
}

function LocationMapSync({ position }) {
  const map = useMap()
  const hadPositionRef = useRef(false)

  useEffect(() => {
    map.invalidateSize()

    if (!position) {
      return
    }

    if (!hadPositionRef.current) {
      map.setView(position, SELECTED_LOCATION_ZOOM)
      hadPositionRef.current = true
    } else {
      map.setView(position)
    }
  }, [map, position])

  return null
}

function getErrorMessage(error, t) {
  if (error?.response?.status === 401) {
    return t('addField.authRequired')
  }

  return getApiErrorMessage(error, t('addField.submitFailed'))
}

function AddFieldModal({ onClose, onCreated }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [sportType, setSportType] = useState('football')
  const [surfaceType, setSurfaceType] = useState('asphalt')
  const [hasNets, setHasNets] = useState(false)
  const [hasWater, setHasWater] = useState(false)
  const [openingHours, setOpeningHours] = useState('')
  const [notes, setNotes] = useState('')
  const [city, setCity] = useState('')
  // No location is selected until the user explicitly provides one, either
  // via device geolocation or by tapping/dragging a pin on the map. This
  // must never be pre-filled with a fallback/display-only coordinate.
  const [position, setPosition] = useState(null)
  const [locationSource, setLocationSource] = useState(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const trimmedCity = city.trim()
  const isCityKnown = israelCities.includes(trimmedCity)

  async function useCurrentLocation() {
    const result = await getCurrentLocation({ highAccuracy: true })
    if (result.ok) {
      setPosition([result.location.latitude, result.location.longitude])
      setLocationSource('gps')
      setError('')
      return
    }

    if (result.needsSettings) {
      setError(t('map.locationSettings'))
    } else if (result.error === 'permission_denied') {
      setError(t('map.locationDenied'))
    } else if (result.error === 'unsupported') {
      setError(t('addField.locationUnavailable'))
    } else {
      setError(t('addField.locationFailed'))
    }
  }

  function handleManualPositionChange(nextPosition) {
    setPosition(nextPosition)
    setLocationSource('manual')
    setError('')
  }

  function hasConfirmedLocation() {
    return (
      Boolean(locationSource) &&
      Array.isArray(position) &&
      Number.isFinite(position[0]) &&
      Number.isFinite(position[1])
    )
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!name.trim()) {
      setError(t('addField.nameRequired'))
      return
    }

    if (!trimmedCity || !isCityKnown) {
      setError(t('addField.cityRequired'))
      return
    }

    if (!hasConfirmedLocation()) {
      setError(t('addField.locationRequired'))
      return
    }

    setError('')
    setIsSubmitting(true)

    try {
      await createField({
        name: name.trim(),
        lat: position[0],
        lng: position[1],
        sport_type: sportType,
        surface_type: surfaceType.trim(),
        has_nets: hasNets,
        has_water: hasWater,
        opening_hours: openingHours.trim(),
        city: trimmedCity,
        notes: notes.trim(),
      })
      onCreated?.()
      onClose()
    } catch (submitError) {
      setError(getErrorMessage(submitError, t))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      className="add-field-modal"
      ariaLabelledBy="add-field-title"
    >
      <h2 id="add-field-title">{t('addField.title')}</h2>

        <form className="add-field-form" onSubmit={handleSubmit}>
          <label>
            {t('addField.fieldName')}
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('addField.fieldNamePlaceholder')}
              required
            />
          </label>

          <label>
            {t('addField.sportType')}
            <select value={sportType} onChange={(event) => setSportType(event.target.value)}>
              <option value="football">{t('addField.football')}</option>
              <option value="basketball">{t('addField.basketball')}</option>
              <option value="both">{t('addField.both')}</option>
            </select>
          </label>

          <label>
            {t('addField.surfaceType')}
            <input
              type="text"
              value={surfaceType}
              onChange={(event) => setSurfaceType(event.target.value)}
              placeholder={t('addField.surfacePlaceholder')}
              required
            />
          </label>

          <div className="form-toggle-row">
            <label>
              <input
                type="checkbox"
                checked={hasNets}
                onChange={(event) => setHasNets(event.target.checked)}
              />
              {t('addField.hasNets')}
            </label>
            <label>
              <input
                type="checkbox"
                checked={hasWater}
                onChange={(event) => setHasWater(event.target.checked)}
              />
              {t('addField.hasWater')}
            </label>
          </div>

          <label>
            {t('addField.openingHours')}
            <input
              type="text"
              value={openingHours}
              onChange={(event) => setOpeningHours(event.target.value)}
              placeholder={t('addField.openingPlaceholder')}
            />
          </label>

          <label>
            {t('addField.notes')}
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder={t('addField.notesPlaceholder')}
              rows="3"
            />
          </label>

          <div className="settings-input">
            <label htmlFor="add-field-city-input">{t('addField.city')}</label>
            <CityAutocomplete
              id="add-field-city-input"
              value={city}
              onChange={setCity}
              cities={israelCities}
              placeholder={t('addField.cityPlaceholder')}
              aria-describedby={trimmedCity && !isCityKnown ? 'error-add-field-city' : undefined}
            />
            {trimmedCity && !isCityKnown ? (
              <span className="form-field-error" id="error-add-field-city">
                {t('addField.cityInvalid')}
              </span>
            ) : null}
          </div>

          <div className="location-picker">
            <div className="location-picker-header">
              <span>{t('addField.location')}</span>
              <button type="button" onClick={useCurrentLocation}>
                {t('addField.useCurrentLocation')}
              </button>
            </div>
            <MapContainer
              center={position || MAP_DISPLAY_FALLBACK_CENTER}
              zoom={position ? SELECTED_LOCATION_ZOOM : MAP_DISPLAY_FALLBACK_ZOOM}
              className="location-picker-map"
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <LocationMapSync position={position} />
              <LocationClickHandler onPositionChange={handleManualPositionChange} />
              {position ? (
                <LocationPicker position={position} onPositionChange={handleManualPositionChange} />
              ) : null}
            </MapContainer>
            {position ? (
              <p>
                {t('addField.coordinates', {
                  // Note: interpolation keys must avoid i18next's reserved
                  // `lng`/`lngs` option names (used to force a translation
                  // language), or the string silently falls back to
                  // fallbackLng regardless of the active app language.
                  latitude: position[0].toFixed(6),
                  longitude: position[1].toFixed(6),
                })}
              </p>
            ) : (
              <p className="form-hint">{t('addField.locationNotSet')}</p>
            )}
          </div>

          <p className="form-hint">{t('addField.locationHint')}</p>

          {error ? <p className="modal-error" role="alert">{error}</p> : null}

          <div className="field-report-actions">
            <button className="secondary-modal-button" type="button" onClick={onClose} disabled={isSubmitting}>
              {t('addField.cancel')}
            </button>
            <button className="primary-modal-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('addField.submitting') : t('addField.submit')}
            </button>
          </div>
        </form>
    </Modal>
  )
}

export default AddFieldModal
