import { useCallback, useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { Bell } from 'lucide-react'
import { getFields } from '../api/fields'
import AddFieldModal from '../components/AddFieldModal'
import FieldDetailsPanel from '../components/FieldDetailsPanel'
import NotificationsModal from '../components/NotificationsModal'

const DEFAULT_CENTER = [30.9872, 34.9314]
const DEFAULT_ZOOM = 14

function getStoredCurrentUserId() {
  if (typeof localStorage === 'undefined') {
    return ''
  }

  return (
    localStorage.getItem('currentUserId') ||
    localStorage.getItem('current_user_id') ||
    localStorage.getItem('user_id') ||
    ''
  )
}

function getFieldPosition(field) {
  const lat = Number(field.lat ?? field.latitude)
  const lng = Number(field.lng ?? field.longitude)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return null
  }

  return [lat, lng]
}

function getActiveGame(field) {
  return field.active_game ?? field.activeGame ?? null
}

function getMarkerColor(field) {
  const activeGame = getActiveGame(field)

  if (!activeGame) {
    return 'gray'
  }

  const maxPlayers = Number(activeGame.max_players)
  const playersPresent = Number(activeGame.players_present)

  if (!Number.isFinite(maxPlayers) || !Number.isFinite(playersPresent)) {
    return 'gray'
  }

  const missingPlayers = maxPlayers - playersPresent

  if (missingPlayers <= 0) {
    return 'gray'
  }

  if (missingPlayers <= 2) {
    return 'green'
  }

  if (missingPlayers <= 5) {
    return 'yellow'
  }

  return 'red'
}

function createMarkerIcon(color) {
  return L.divIcon({
    className: 'field-marker-icon',
    html: `<div class="field-marker ${color}"></div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function mapBoundsToParams(bounds) {
  return {
    north: bounds.getNorth(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    west: bounds.getWest(),
  }
}

function RecenterMap({ center }) {
  const map = useMap()

  useEffect(() => {
    map.setView(center)
  }, [center, map])

  return null
}

function FieldLoader({ center, onError, onFieldsLoaded, reloadKey }) {
  const loadFields = useCallback(
    async (bounds) => {
      try {
        const fields = await getFields(bounds ? mapBoundsToParams(bounds) : undefined)
        onFieldsLoaded(Array.isArray(fields) ? fields : [])
        onError('')
      } catch {
        onError('Could not load fields from the backend.')
        onFieldsLoaded([])
      }
    },
    [onError, onFieldsLoaded],
  )

  const map = useMapEvents({
    moveend() {
      loadFields(map.getBounds())
    },
  })

  useEffect(() => {
    loadFields(map.getBounds())
  }, [center, loadFields, map, reloadKey])

  return null
}

function MapPage() {
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [fields, setFields] = useState([])
  const [error, setError] = useState('')
  const [selectedField, setSelectedField] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false)
  const [currentUserId] = useState(getStoredCurrentUserId)
  const [isAddFieldOpen, setIsAddFieldOpen] = useState(false)
  const [fieldSubmitMessage, setFieldSubmitMessage] = useState('')

  useEffect(() => {
    if (!navigator.geolocation) {
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCenter([position.coords.latitude, position.coords.longitude])
      },
      () => {
        setCenter(DEFAULT_CENTER)
      },
    )
  }, [])

  const markerIcons = useMemo(
    () => ({
      gray: createMarkerIcon('gray'),
      green: createMarkerIcon('green'),
      yellow: createMarkerIcon('yellow'),
      red: createMarkerIcon('red'),
    }),
    [],
  )

  const handleFieldsLoaded = useCallback((loadedFields) => {
    setFields(loadedFields)
    setSelectedField((currentField) => {
      if (!currentField) {
        return currentField
      }

      return loadedFields.find((field) => field.id === currentField.id) ?? currentField
    })
  }, [])

  function refreshFields() {
    setReloadKey((currentReloadKey) => currentReloadKey + 1)
  }

  function handleFieldCreated() {
    setFieldSubmitMessage('Sent for VAR approval')
    refreshFields()
  }

  return (
    <main className="map-page">
      {error ? <div className="map-error">{error}</div> : null}
      {fieldSubmitMessage ? <div className="map-success">{fieldSubmitMessage}</div> : null}

      <button
        className="floating-button top"
        type="button"
        aria-label="Notifications"
        onClick={() => setIsNotificationsOpen(true)}
      >
        <Bell size={22} />
      </button>

      <MapContainer center={center} zoom={DEFAULT_ZOOM} className="map-canvas">
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <RecenterMap center={center} />
        <FieldLoader
          center={center}
          onError={setError}
          onFieldsLoaded={handleFieldsLoaded}
          reloadKey={reloadKey}
        />

        {fields.map((field) => {
          const position = getFieldPosition(field)
          const activeGame = getActiveGame(field)

          if (!position) {
            return null
          }

          const color = getMarkerColor(field)

          return (
            <Marker
              eventHandlers={{
                click: () => {
                  setSelectedField(field)
                },
              }}
              icon={markerIcons[color]}
              key={field.id}
              position={position}
            >
              <Popup>
                <div className="field-popup">
                  <h2>{field.name}</h2>
                  {field.sport_type ? <p>Sport: {field.sport_type}</p> : null}
                  <p>Active game: {activeGame?.status ?? 'none'}</p>
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>

      <button
        className="floating-button bottom"
        type="button"
        aria-label="Add field"
        onClick={() => {
          setFieldSubmitMessage('')
          setIsAddFieldOpen(true)
        }}
      >
        +
      </button>

      <FieldDetailsPanel
        field={selectedField}
        onClose={() => setSelectedField(null)}
        onGameCreated={refreshFields}
        currentUserId={currentUserId}
      />

      {isNotificationsOpen ? (
        <NotificationsModal fields={fields} onClose={() => setIsNotificationsOpen(false)} />
      ) : null}

      {isAddFieldOpen ? (
        <AddFieldModal onClose={() => setIsAddFieldOpen(false)} onCreated={handleFieldCreated} />
      ) : null}
    </main>
  )
}

export default MapPage
