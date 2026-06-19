import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { Bell, LocateFixed, Settings } from 'lucide-react'
import { getFieldById, getFields } from '../api/fields'
import AddFieldModal from '../components/AddFieldModal'
import FieldDetailsPanel from '../components/FieldDetailsPanel'
import NotificationInboxModal from '../components/NotificationInboxModal'
import NotificationsModal from '../components/NotificationsModal'
import { getStoredSessionUserId } from '../api/auth'
import { getNotifications, getUnreadNotificationCount } from '../api/notifications'
import LanguageSwitcher from '../components/LanguageSwitcher'

const DEFAULT_CENTER = [30.9872, 34.9314]
const DEFAULT_ZOOM = 14
const UNREAD_COUNT_POLL_MS = import.meta.env.DEV ? 1000 : 20000
const USER_LOCATION_ZOOM = 16
const STADIUM_MARKER_SIZE = 54
const STADIUM_MARKER_ANCHOR = [STADIUM_MARKER_SIZE / 2, STADIUM_MARKER_SIZE / 2]
const CACHED_FIELDS_KEY = 'cached_fields'
const CACHED_FIELDS_TIMESTAMP_KEY = 'cached_fields_timestamp'
const STADIUM_MARKER_ASSETS = {
  active: '/stadium-active.png',
  inactive: '/stadium-inactive.png',
}

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

function hasActiveGame(field) {
  return Boolean(getActiveGame(field))
}

function readCachedFields() {
  if (typeof localStorage === 'undefined') {
    return { fields: [], timestamp: '' }
  }

  try {
    const cachedFields = JSON.parse(localStorage.getItem(CACHED_FIELDS_KEY) ?? '[]')
    const timestamp = localStorage.getItem(CACHED_FIELDS_TIMESTAMP_KEY) ?? ''

    return {
      fields: Array.isArray(cachedFields) ? cachedFields : [],
      timestamp,
    }
  } catch {
    return { fields: [], timestamp: '' }
  }
}

function writeCachedFields(fields) {
  if (typeof localStorage === 'undefined' || !Array.isArray(fields)) {
    return ''
  }

  const timestamp = new Date().toISOString()

  try {
    localStorage.setItem(CACHED_FIELDS_KEY, JSON.stringify(fields))
    localStorage.setItem(CACHED_FIELDS_TIMESTAMP_KEY, timestamp)
    return timestamp
  } catch {
    return ''
  }
}

function createMarkerIcon(status, label) {
  return L.divIcon({
    className: 'field-marker-icon',
    html: `
      <div class="field-marker field-marker--${status}" aria-label="${label}">
        <img class="field-marker-stadium" src="${STADIUM_MARKER_ASSETS[status]}" alt="" />
        <span class="field-marker-status" aria-hidden="true"></span>
      </div>
    `,
    iconSize: [STADIUM_MARKER_SIZE, STADIUM_MARKER_SIZE],
    iconAnchor: STADIUM_MARKER_ANCHOR,
  })
}

function createUserLocationIcon() {
  return L.divIcon({
    className: 'user-location-marker-icon',
    html: '<div class="user-location-marker"></div>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
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

function UserLocationFlyTo({ requestId, userLocation }) {
  const map = useMap()

  useEffect(() => {
    if (!requestId || !userLocation) {
      return
    }

    map.flyTo(userLocation.position, USER_LOCATION_ZOOM)
  }, [map, requestId, userLocation])

  return null
}

function FieldLoader({ onError, onFieldsLoaded, onLoadingChange, reloadKey }) {
  const { t } = useTranslation()
  const latestRequestId = useRef(0)

  const loadFields = useCallback(
    async (bounds) => {
      const requestId = latestRequestId.current + 1
      latestRequestId.current = requestId
      onLoadingChange(true)

      try {
        const fields = await getFields(bounds ? mapBoundsToParams(bounds) : undefined)
        if (requestId !== latestRequestId.current) {
          return
        }

        onFieldsLoaded(Array.isArray(fields) ? fields : [])
        onError('')
      } catch {
        if (requestId !== latestRequestId.current) {
          return
        }

        onError(t('map.loadFieldsError'))
      } finally {
        if (requestId === latestRequestId.current) {
          onLoadingChange(false)
        }
      }
    },
    [onError, onFieldsLoaded, onLoadingChange, t],
  )

  const map = useMapEvents({
    moveend() {
      loadFields(map.getBounds())
    },
  })

  useEffect(() => {
    loadFields(map.getBounds())
  }, [loadFields, map, reloadKey])

  return null
}

const FieldMarker = memo(function FieldMarker({ field, markerIcons, onSelectField }) {
  const { t } = useTranslation()
  const position = useMemo(() => getFieldPosition(field), [field])
  const activeGame = getActiveGame(field)
  const markerStatus = hasActiveGame(field) ? 'active' : 'inactive'
  const handleClick = useCallback(() => {
    onSelectField(field)
  }, [field, onSelectField])
  const eventHandlers = useMemo(
    () => ({
      click: handleClick,
    }),
    [handleClick],
  )

  if (!position) {
    return null
  }

  return (
    <Marker
      eventHandlers={eventHandlers}
      icon={markerIcons[markerStatus]}
      position={position}
    >
      <Popup>
        <div className="field-popup">
          <h2>{field.name}</h2>
          {field.sport_type ? <p>{t('map.sport')}: {t(`values.${field.sport_type}`, field.sport_type)}</p> : null}
          <p>{t('map.activeGame')}: {activeGame?.status ? t(`values.${activeGame.status}`, activeGame.status) : t('map.none')}</p>
        </div>
      </Popup>
    </Marker>
  )
})

function MapPage({ currentUserId: authenticatedUserId }) {
  const { t } = useTranslation()
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [userLocation, setUserLocation] = useState(null)
  const [userLocationRequestId, setUserLocationRequestId] = useState(0)
  const cachedFieldsState = useMemo(() => readCachedFields(), [])
  const [fields, setFields] = useState(cachedFieldsState.fields)
  const [isFieldsLoading, setIsFieldsLoading] = useState(!cachedFieldsState.fields.length)
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

    let isMounted = true

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!isMounted) {
          return
        }

        const nextUserLocation = {
          position: [position.coords.latitude, position.coords.longitude],
          accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
        }

        setUserLocation(nextUserLocation)
        setCenter(nextUserLocation.position)
      },
      () => {
        if (isMounted) {
          setUserLocation(null)
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      },
    )

    return () => {
      isMounted = false
    }
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
      active: createMarkerIcon('active', t('map.activeField')),
      inactive: createMarkerIcon('inactive', t('map.inactiveField')),
    }),
    [t],
  )
  const userLocationIcon = useMemo(() => createUserLocationIcon(), [])

  const handleFieldsLoaded = useCallback((loadedFields) => {
    setFields((currentFields) => {
      if (JSON.stringify(currentFields) === JSON.stringify(loadedFields)) {
        return currentFields
      }

      return loadedFields
    })
    writeCachedFields(loadedFields)
    setSelectedField((currentField) => {
      if (!currentField) {
        return currentField
      }

      return loadedFields.find((field) => field.id === currentField.id) ?? currentField
    })
  }, [])

  const handleSelectField = useCallback((field) => {
    setSelectedField(field)
  }, [])

  const fieldMarkers = useMemo(
    () =>
      fields.map((field, index) => (
        <FieldMarker
          field={field}
          key={`${field.id ?? field.name ?? 'field'}-${index}`}
          markerIcons={markerIcons}
          onSelectField={handleSelectField}
        />
      )),
    [fields, handleSelectField, markerIcons],
  )

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
    setFieldSubmitMessage(t('map.sentForApproval'))
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
    ? t('map.notificationsUnread', { count: unreadNotificationCount })
    : t('map.notifications')

  return (
    <main className="map-page">
      <LanguageSwitcher className="map-language-switcher" />
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
        aria-label={t('map.notificationPreferences')}
        onClick={() => setIsNotificationPreferencesOpen(true)}
      >
        <Settings size={22} />
      </button>

      {userLocation ? (
        <button
          className="floating-button my-location"
          type="button"
          aria-label={t('map.myLocation')}
          onClick={() => setUserLocationRequestId((currentRequestId) => currentRequestId + 1)}
        >
          <LocateFixed size={22} />
        </button>
      ) : null}

      <MapContainer center={center} zoom={DEFAULT_ZOOM} className="map-canvas">
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <RecenterMap center={center} />
        <UserLocationFlyTo requestId={userLocationRequestId} userLocation={userLocation} />
        <FieldLoader
          onError={setError}
          onFieldsLoaded={handleFieldsLoaded}
          onLoadingChange={setIsFieldsLoading}
          reloadKey={reloadKey}
        />

        {userLocation ? (
          <Fragment key="user-location-layer">
            {userLocation.accuracy ? (
              <Circle
                center={userLocation.position}
                pathOptions={{
                  color: '#2563eb',
                  fillColor: '#3b82f6',
                  fillOpacity: 0.12,
                  opacity: 0.24,
                  weight: 1,
                }}
                radius={userLocation.accuracy}
              />
            ) : null}
            <Marker
              icon={userLocationIcon}
              interactive={false}
              keyboard={false}
              position={userLocation.position}
              zIndexOffset={1000}
            />
          </Fragment>
        ) : null}

        {fieldMarkers}
      </MapContainer>

      {isFieldsLoading && !fields.length ? (
        <div className="map-loading" role="status" aria-live="polite">
          <span className="map-loading-spinner" aria-hidden="true" />
          <span>{t('map.loadingFields')}</span>
        </div>
      ) : null}

      <button
        className="floating-button bottom"
        type="button"
        aria-label={t('map.addField')}
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
