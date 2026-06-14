import { useCallback, useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { getFields } from '../api/fields'

const DEFAULT_CENTER = [30.9872, 34.9314]
const DEFAULT_ZOOM = 14
const TILE_URL =
  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="256" height="256"%3E%3Crect width="256" height="256" fill="%23eef2f7"/%3E%3Cpath d="M0 0H256V256H0Z" fill="none" stroke="%23d8dee8" stroke-width="1"/%3E%3C/svg%3E'

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
    className: '',
    html: `<span class="field-marker ${color}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
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

function FieldLoader({ center, onError, onFieldsLoaded }) {
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
  }, [center, loadFields, map])

  return null
}

function MapPage() {
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [fields, setFields] = useState([])
  const [error, setError] = useState('')

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

  return (
    <main className="map-page">
      {error ? <div className="map-error">{error}</div> : null}

      <button className="floating-button top" type="button" aria-label="Notifications">
        Bell
      </button>

      <MapContainer center={center} zoom={DEFAULT_ZOOM} className="map-canvas">
        <TileLayer attribution="Local test tiles" url={TILE_URL} />
        <RecenterMap center={center} />
        <FieldLoader center={center} onError={setError} onFieldsLoaded={setFields} />

        {fields.map((field) => {
          const position = getFieldPosition(field)
          const activeGame = getActiveGame(field)

          if (!position) {
            return null
          }

          const color = getMarkerColor(field)

          return (
            <Marker icon={markerIcons[color]} key={field.id} position={position}>
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

      <button className="floating-button bottom" type="button" aria-label="Add field">
        +
      </button>
    </main>
  )
}

export default MapPage
