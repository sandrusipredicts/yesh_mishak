import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { createField } from '../api/fields'
import { getApiErrorMessage } from '../api/errors'

const DEFAULT_POSITION = [30.9872, 34.9314]
const locationPinIcon = L.divIcon({
  className: 'location-picker-pin-icon',
  html: '<div class="location-picker-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
})

function LocationPicker({ position, onPositionChange }) {
  const map = useMap()

  useMapEvents({
    click(event) {
      const nextPosition = [event.latlng.lat, event.latlng.lng]
      onPositionChange(nextPosition)
      map.panTo(nextPosition)
    },
  })

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

  useEffect(() => {
    map.setView(position)
    map.invalidateSize()
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
  const [position, setPosition] = useState(DEFAULT_POSITION)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError(t('addField.locationUnavailable'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (location) => {
        setPosition([location.coords.latitude, location.coords.longitude])
        setError('')
      },
      () => {
        setError(t('addField.locationFailed'))
      },
    )
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!name.trim()) {
      setError(t('addField.nameRequired'))
      return
    }

    if (!Number.isFinite(position[0]) || !Number.isFinite(position[1])) {
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
        city: localStorage.getItem('userCity') || '',
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
    <div className="modal-backdrop" role="presentation">
      <section className="add-field-modal" role="dialog" aria-modal="true" aria-labelledby="add-field-title">
        <button className="modal-close-button" type="button" onClick={onClose} aria-label={t('field.close')}>
          x
        </button>

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

          <div className="location-picker">
            <div className="location-picker-header">
              <span>{t('addField.location')}</span>
              <button type="button" onClick={useCurrentLocation}>
                {t('addField.useCurrentLocation')}
              </button>
            </div>
            <MapContainer center={position} zoom={15} className="location-picker-map">
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <LocationMapSync position={position} />
              <LocationPicker position={position} onPositionChange={setPosition} />
            </MapContainer>
            <p>
              {t('addField.coordinates', {
                lat: position[0].toFixed(6),
                lng: position[1].toFixed(6),
              })}
            </p>
          </div>

          <p className="form-hint">{t('addField.locationHint')}</p>

          {error ? <p className="modal-error">{error}</p> : null}

          <div className="field-report-actions">
            <button className="secondary-modal-button" type="button" onClick={onClose} disabled={isSubmitting}>
              {t('addField.cancel')}
            </button>
            <button className="primary-modal-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('addField.submitting') : t('addField.submit')}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

export default AddFieldModal
