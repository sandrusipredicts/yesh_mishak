import { useEffect, useState } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { createField } from '../api/fields'

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

function getErrorMessage(error) {
  if (error?.response?.status === 401) {
    return 'צריך להתחבר כדי להוסיף מגרש'
  }

  return 'Could not submit field. Please try again.'
}

function AddFieldModal({ onClose, onCreated }) {
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
      setError('Browser location is not available.')
      return
    }

    navigator.geolocation.getCurrentPosition(
      (location) => {
        setPosition([location.coords.latitude, location.coords.longitude])
        setError('')
      },
      () => {
        setError('Could not get current location.')
      },
    )
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!name.trim()) {
      setError('Field name is required.')
      return
    }

    if (!Number.isFinite(position[0]) || !Number.isFinite(position[1])) {
      setError('Field location is required.')
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
        notes: notes.trim(),
      })
      onCreated?.()
      onClose()
    } catch (submitError) {
      setError(getErrorMessage(submitError))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="add-field-modal" role="dialog" aria-modal="true" aria-labelledby="add-field-title">
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
          x
        </button>

        <h2 id="add-field-title">Add Field</h2>

        <form className="add-field-form" onSubmit={handleSubmit}>
          <label>
            Field name
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="מגרש שכונה"
              required
            />
          </label>

          <label>
            Sport type
            <select value={sportType} onChange={(event) => setSportType(event.target.value)}>
              <option value="football">Football</option>
              <option value="basketball">Basketball</option>
              <option value="both">Both</option>
            </select>
          </label>

          <label>
            Surface type
            <input
              type="text"
              value={surfaceType}
              onChange={(event) => setSurfaceType(event.target.value)}
              placeholder="asphalt"
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
              Has nets?
            </label>
            <label>
              <input
                type="checkbox"
                checked={hasWater}
                onChange={(event) => setHasWater(event.target.checked)}
              />
              Has water fountain?
            </label>
          </div>

          <label>
            Opening hours
            <input
              type="text"
              value={openingHours}
              onChange={(event) => setOpeningHours(event.target.value)}
              placeholder="תמיד פתוח"
            />
          </label>

          <label>
            Notes
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="יש תאורה בערב"
              rows="3"
            />
          </label>

          <div className="location-picker">
            <div className="location-picker-header">
              <span>Location</span>
              <button type="button" onClick={useCurrentLocation}>
                Use current location
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
              Lat: {position[0].toFixed(6)}, Lng: {position[1].toFixed(6)}
            </p>
          </div>

          {error ? <p className="modal-error">{error}</p> : null}

          <button className="primary-panel-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Submitting...' : 'Submit for approval'}
          </button>
        </form>
      </section>
    </div>
  )
}

export default AddFieldModal
