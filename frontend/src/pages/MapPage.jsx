import { useCallback, useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { Bell, Settings } from 'lucide-react'
import { getFieldById, getFields } from '../api/fields'
import AddFieldModal from '../components/AddFieldModal'
import FieldDetailsPanel from '../components/FieldDetailsPanel'
import NotificationInboxModal from '../components/NotificationInboxModal'
import NotificationsModal from '../components/NotificationsModal'
import { getStoredSessionUserId } from '../api/auth'
import { getNotifications, getUnreadNotificationCount } from '../api/notifications'

const DEFAULT_CENTER = [30.9872, 34.9314]
const DEFAULT_ZOOM = 14
const UNREAD_COUNT_POLL_MS = import.meta.env.DEV ? 1000 : 20000

function getStoredCurrentUserId() {
  if (typeof localStorage === 'undefined') {
    return ''
  }

  return getStoredSessionUserId()
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

function MapPage({ currentUserId: authenticatedUserId }) {
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [fields, setFields] = useState([])
  const [error, setError] = useState('')
  const [selectedField, setSelectedField] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false)
  const [isNotificationPreferencesOpen, setIsNotificationPreferencesOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadNotificationCount, setUnreadNotificationCount] = useState(0)
  const currentUserId = authenticatedUserId || getStoredCurrentUserId()
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

  const refreshNotifications = useCallback(async () => {
    try {
      const [loadedNotifications, unreadCountResult] = await Promise.all([
        getNotifications(),
        getUnreadNotificationCount(),
      ])
      setNotifications(Array.isArray(loadedNotifications) ? loadedNotifications : [])
      setUnreadNotificationCount(Number(unreadCountResult?.unread_count ?? 0))
    } catch {
      setNotifications([])
      setUnreadNotificationCount(0)
    }
  }, [])

  const refreshUnreadCount = useCallback(async () => {
    try {
      const unreadCountResult = await getUnreadNotificationCount()
      setUnreadNotificationCount(Number(unreadCountResult?.unread_count ?? 0))
    } catch {
      setUnreadNotificationCount(0)
    }
  }, [])

  useEffect(() => {
    let isMounted = true

    Promise.all([getNotifications(), getUnreadNotificationCount()])
      .then(([loadedNotifications, unreadCountResult]) => {
        if (isMounted) {
          setNotifications(Array.isArray(loadedNotifications) ? loadedNotifications : [])
          setUnreadNotificationCount(Number(unreadCountResult?.unread_count ?? 0))
        }
      })
      .catch(() => {
        if (isMounted) {
          setNotifications([])
          setUnreadNotificationCount(0)
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (!currentUserId) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        refreshUnreadCount()
      }
    }, UNREAD_COUNT_POLL_MS)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [currentUserId, refreshUnreadCount])

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

  const refreshFieldState = useCallback(
    async (fieldId) => {
      const targetFieldId = fieldId || selectedField?.id

      if (!targetFieldId) {
        refreshFields()
        await refreshUnreadCount()
        return
      }

      try {
        const updatedField = await getFieldById(targetFieldId)
        setFields((currentFields) => {
          const existingIndex = currentFields.findIndex((field) => field.id === updatedField.id)

          if (existingIndex === -1) {
            return [...currentFields, updatedField]
          }

          return currentFields.map((field) =>
            field.id === updatedField.id ? updatedField : field,
          )
        })
        setSelectedField(updatedField)
        await refreshUnreadCount()
      } catch {
        refreshFields()
        await refreshUnreadCount()
      }
    },
    [refreshUnreadCount, selectedField?.id],
  )

  function handleFieldCreated() {
    setFieldSubmitMessage('Sent for VAR approval')
    refreshFields()
  }

  async function handleNotificationTarget(notification) {
    const targetFieldId = notification.field_id
    const targetGameId = notification.game_id
    const findTargetField = (candidateFields) => candidateFields.find((field) => {
      const activeGame = getActiveGame(field)
      return field.id === targetFieldId || activeGame?.id === targetGameId
    })

    let targetField = findTargetField(fields)

    if (!targetField) {
      try {
        const loadedFields = await getFields()
        const nextFields = Array.isArray(loadedFields) ? loadedFields : []
        setFields(nextFields)
        targetField = findTargetField(nextFields)
      } catch {
        targetField = null
      }
    }

    if (targetField) {
      setSelectedField(targetField)
      setIsNotificationsOpen(false)
    }
  }

  const notificationsLabel = unreadNotificationCount
    ? `Notifications, ${unreadNotificationCount} unread`
    : 'Notifications'

  return (
    <main className="map-page">
      {error ? <div className="map-error">{error}</div> : null}
      {fieldSubmitMessage ? <div className="map-success">{fieldSubmitMessage}</div> : null}

      <button
        className="floating-button top"
        type="button"
        aria-label={notificationsLabel}
        onClick={() => {
          setIsNotificationsOpen(true)
          refreshNotifications()
        }}
      >
        <Bell size={22} />
        {unreadNotificationCount ? (
          <span className="notification-badge" aria-hidden="true">
            {unreadNotificationCount}
          </span>
        ) : null}
      </button>

      <button
        className="floating-button preferences"
        type="button"
        aria-label="Notification preferences"
        onClick={() => setIsNotificationPreferencesOpen(true)}
      >
        <Settings size={22} />
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
        onGameCreated={refreshFieldState}
        currentUserId={currentUserId}
      />

      {isNotificationsOpen ? (
        <NotificationInboxModal
          notifications={notifications}
          onClose={() => setIsNotificationsOpen(false)}
          onNotificationsChange={setNotifications}
          onRefreshNotifications={refreshNotifications}
          onRefreshUnreadCount={refreshUnreadCount}
          onUnreadCountChange={setUnreadNotificationCount}
          onOpenTarget={handleNotificationTarget}
        />
      ) : null}

      {isNotificationPreferencesOpen ? (
        <NotificationsModal
          fields={fields}
          onClose={() => setIsNotificationPreferencesOpen(false)}
          onPreferencesSaved={refreshUnreadCount}
        />
      ) : null}

      {isAddFieldOpen ? (
        <AddFieldModal onClose={() => setIsAddFieldOpen(false)} onCreated={handleFieldCreated} />
      ) : null}
    </main>
  )
}

export default MapPage
