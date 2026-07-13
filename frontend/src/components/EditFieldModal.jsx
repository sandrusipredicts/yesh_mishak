import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import Modal from './Modal'
import CityAutocomplete from './CityAutocomplete'

import { updateAdminField } from '../api/admin'
import { getApiErrorMessage } from '../api/errors'
import { israelCities } from '../data/israelCities'

// Display-only fallback so the map has something to render for a legacy
// field with no valid coordinates yet. Never submitted as real data.
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

function getFieldPosition(field) {
  const lat = Number(field?.lat)
  const lng = Number(field?.lng)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return [lat, lng]
}

function getErrorMessage(error, t) {
  const statusCode = error?.response?.status

  if (statusCode === 409) {
    return t('editField.duplicateWarning')
  }
  if (statusCode === 403) {
    return t('editField.permissionDenied')
  }
  if (statusCode === 404) {
    return t('editField.notFound')
  }

  return getApiErrorMessage(error, t('editField.saveFailed'))
}

function textField(value) {
  return value ?? ''
}

function EditFieldModal({ field, onClose, onSaved }) {
  const { t } = useTranslation()
  const initialPosition = useMemo(() => getFieldPosition(field), [field])

  const initialCity = textField(field?.city)
  const initialSurfaceType = textField(field?.surface_type)
  const initialOpeningHours = textField(field?.opening_hours)
  const initialNotes = textField(field?.notes)

  const [name, setName] = useState(textField(field?.name))
  const [sportType, setSportType] = useState(field?.sport_type ?? 'football')
  const [surfaceType, setSurfaceType] = useState(initialSurfaceType)
  const [hasNets, setHasNets] = useState(Boolean(field?.has_nets))
  const [hasWater, setHasWater] = useState(Boolean(field?.has_water))
  const [openingHours, setOpeningHours] = useState(initialOpeningHours)
  const [notes, setNotes] = useState(initialNotes)
  const [city, setCity] = useState(initialCity)
  const [position, setPosition] = useState(initialPosition)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showUnsavedConfirm, setShowUnsavedConfirm] = useState(false)

  const trimmedCity = city.trim()
  const cityChanged = trimmedCity !== initialCity
  // A legacy/imported field's existing city may not be in today's known-city
  // list. That must never block saving unrelated changes — only re-validate
  // the city format when the admin actually edits it (E02-01 edge case: a
  // field with legacy/missing values stays editable).
  const isCityKnown = !cityChanged || !trimmedCity || israelCities.includes(trimmedCity)
  const positionChanged =
    Boolean(position) !== Boolean(initialPosition) ||
    (position && initialPosition && (position[0] !== initialPosition[0] || position[1] !== initialPosition[1]))

  function handlePositionChange(nextPosition) {
    setPosition(nextPosition)
    setError('')
  }

  function isDirty() {
    return (
      name.trim() !== textField(field?.name) ||
      sportType !== (field?.sport_type ?? 'football') ||
      surfaceType.trim() !== initialSurfaceType ||
      hasNets !== Boolean(field?.has_nets) ||
      hasWater !== Boolean(field?.has_water) ||
      openingHours.trim() !== initialOpeningHours ||
      notes.trim() !== initialNotes ||
      trimmedCity !== initialCity ||
      positionChanged
    )
  }

  function buildChangedPayload() {
    const payload = {}

    if (name.trim() !== textField(field?.name)) payload.name = name.trim()
    if (sportType !== (field?.sport_type ?? 'football')) payload.sport_type = sportType
    if (surfaceType.trim() !== initialSurfaceType) payload.surface_type = surfaceType.trim()
    if (hasNets !== Boolean(field?.has_nets)) payload.has_nets = hasNets
    if (hasWater !== Boolean(field?.has_water)) payload.has_water = hasWater
    if (openingHours.trim() !== initialOpeningHours) payload.opening_hours = openingHours.trim()
    if (notes.trim() !== initialNotes) payload.notes = notes.trim()
    if (trimmedCity !== initialCity) payload.city = trimmedCity
    if (positionChanged && position) {
      payload.lat = position[0]
      payload.lng = position[1]
    }

    return payload
  }

  function requestClose() {
    if (isSubmitting) {
      return
    }

    if (isDirty()) {
      setShowUnsavedConfirm(true)
      return
    }

    onClose()
  }

  function confirmDiscardAndClose() {
    setShowUnsavedConfirm(false)
    onClose()
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (isSubmitting) {
      return
    }

    if (!name.trim()) {
      setError(t('editField.nameRequired'))
      return
    }

    if (trimmedCity && !isCityKnown) {
      setError(t('editField.cityInvalid'))
      return
    }

    const payload = buildChangedPayload()

    if (Object.keys(payload).length === 0) {
      onClose()
      return
    }

    setError('')
    setIsSubmitting(true)

    try {
      const response = await updateAdminField(field.id, payload)
      onSaved?.(response.field ?? response)
      onClose()
    } catch (submitError) {
      setError(getErrorMessage(submitError, t))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!field) {
    return null
  }

  return (
    <>
      <Modal
        isOpen={true}
        onClose={requestClose}
        className="add-field-modal edit-field-modal"
        ariaLabelledBy="edit-field-title"
      >
        <h2 id="edit-field-title">{t('editField.title')}</h2>

        <form className="add-field-form" onSubmit={handleSubmit}>
          <label htmlFor="edit-field-name">
            {t('addField.fieldName')}
            <input
              id="edit-field-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('addField.fieldNamePlaceholder')}
              required
            />
          </label>

          <label htmlFor="edit-field-sport-type">
            {t('addField.sportType')}
            <select
              id="edit-field-sport-type"
              value={sportType}
              onChange={(event) => setSportType(event.target.value)}
            >
              <option value="football">{t('addField.football')}</option>
              <option value="basketball">{t('addField.basketball')}</option>
              <option value="both">{t('addField.both')}</option>
            </select>
          </label>

          <label htmlFor="edit-field-surface-type">
            {t('addField.surfaceType')}
            <input
              id="edit-field-surface-type"
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

          <label htmlFor="edit-field-opening-hours">
            {t('addField.openingHours')}
            <input
              id="edit-field-opening-hours"
              type="text"
              value={openingHours}
              onChange={(event) => setOpeningHours(event.target.value)}
              placeholder={t('addField.openingPlaceholder')}
            />
          </label>

          <label htmlFor="edit-field-notes">
            {t('addField.notes')}
            <textarea
              id="edit-field-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder={t('addField.notesPlaceholder')}
              rows="3"
            />
          </label>

          <div className="settings-input">
            <label htmlFor="edit-field-city-input">{t('addField.city')}</label>
            <CityAutocomplete
              id="edit-field-city-input"
              value={city}
              onChange={setCity}
              cities={israelCities}
              placeholder={t('addField.cityPlaceholder')}
              aria-describedby={trimmedCity && !isCityKnown ? 'error-edit-field-city' : undefined}
            />
            {trimmedCity && !isCityKnown ? (
              <span className="form-field-error" id="error-edit-field-city">
                {t('addField.cityInvalid')}
              </span>
            ) : null}
          </div>

          <div className="location-picker">
            <div className="location-picker-header">
              <span>{t('addField.location')}</span>
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
              <LocationClickHandler onPositionChange={handlePositionChange} />
              {position ? (
                <LocationPicker position={position} onPositionChange={handlePositionChange} />
              ) : null}
            </MapContainer>
            {position ? (
              <p>
                {t('addField.coordinates', {
                  latitude: position[0].toFixed(6),
                  longitude: position[1].toFixed(6),
                })}
              </p>
            ) : (
              <p className="form-hint">{t('editField.locationMissing')}</p>
            )}
          </div>

          <p className="form-hint">{t('addField.locationHint')}</p>

          {error ? <p className="modal-error" role="alert">{error}</p> : null}

          <div className="field-report-actions">
            <button
              className="secondary-modal-button"
              type="button"
              onClick={requestClose}
              disabled={isSubmitting}
            >
              {t('editField.cancel')}
            </button>
            <button className="primary-modal-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('editField.saving') : t('editField.save')}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={showUnsavedConfirm}
        onClose={() => setShowUnsavedConfirm(false)}
        isConfirm={true}
        ariaLabelledBy="edit-field-unsaved-title"
      >
        <h3 id="edit-field-unsaved-title">{t('editField.unsavedTitle')}</h3>
        <p>{t('editField.unsavedMessage')}</p>
        <div className="confirm-modal-actions">
          <button
            type="button"
            className="secondary-modal-button"
            onClick={() => setShowUnsavedConfirm(false)}
          >
            {t('editField.unsavedKeepEditing')}
          </button>
          <button type="button" className="danger-modal-button" onClick={confirmDiscardAndClose}>
            {t('editField.unsavedDiscard')}
          </button>
        </div>
      </Modal>
    </>
  )
}

export default EditFieldModal
