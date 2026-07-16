import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App as CapacitorApp } from '@capacitor/app'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Circle, MapContainer, Marker, Popup, TileLayer, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import { Bell, LocateFixed, Settings } from 'lucide-react'
import { getFieldById, getFields } from '../api/fields'
import { getGameById } from '../api/games'
import AddFieldModal from '../components/AddFieldModal'
import FieldDetailsPanel from '../components/FieldDetailsPanel'
import NotificationInboxModal from '../components/NotificationInboxModal'
import NotificationsModal from '../components/NotificationsModal'
import { getStoredSessionUserId } from '../api/auth'
import { getNotifications, getUnreadNotificationCount } from '../api/notifications'
import { recordLinkOpen } from '../api/shareAnalytics'
import { checkExistingPermission } from '../api/locationPermission'
import { getCurrentLocation } from '../api/locationService'
import { evaluateLocationAccuracy, USE_CASES } from '../utils/locationAccuracy'
import { classifyLocationFailure, getLocationFailureMessage } from '../utils/locationFailure'
import { createNotificationSync } from '../utils/notificationSync'

const DEFAULT_CENTER = [30.9872, 34.9314]
const DEFAULT_ZOOM = 14
const UNREAD_COUNT_POLL_MS = import.meta.env.DEV ? 1000 : 20000
const FIELD_LOAD_DEBOUNCE_MS = 250
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

function participantFingerprint(participant, index) {
  const user = participant?.user ?? {}
  return [
    participant?.user_id ?? participant?.userId ?? user.id ?? '',
    participant?.username ?? user.username ?? '',
    participant?.name ?? participant?.full_name ?? participant?.display_name ??
      user.name ?? user.full_name ?? user.display_name ?? '',
    index,
  ].join(':')
}

function participantsFingerprint(game) {
  const participants = game?.participants
  if (!Array.isArray(participants)) {
    return ''
  }

  return participants.map(participantFingerprint).join(',')
}

function gameFingerprint(game) {
  if (!game) {
    return '-'
  }

  return [
    game.id ?? '',
    game.status ?? '',
    game.players_present ?? game.playersPresent ?? '',
    game.max_players ?? game.maxPlayers ?? '',
    game.scheduled_at ?? game.scheduledAt ?? '',
    game.started_at ?? game.startedAt ?? '',
    game.expires_at ?? game.expiresAt ?? '',
    game.age_note ?? game.ageNote ?? '',
    game.created_by ?? game.createdBy ?? '',
    participantsFingerprint(game),
  ].join(':')
}

function fieldsFingerprint(fields) {
  if (!fields.length) {
    return ''
  }

  const parts = new Array(fields.length)
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i]
    const ag = f.active_game ?? f.activeGame
    const ug = f.upcoming_games ?? f.upcomingGames
    const upcomingFingerprint = Array.isArray(ug)
      ? ug
        .map((game) => gameFingerprint(game))
        .join(',')
      : ''
    parts[i] =
      `${f.id}|${f.name ?? ''}|${f.sport_type ?? f.sportType ?? ''}|` +
      `${f.surface_type ?? f.surfaceType ?? ''}|${f.status ?? ''}|` +
      `${f.approval_status ?? f.approvalStatus ?? ''}|${f.verified ?? ''}|` +
      `${f.lat ?? f.latitude ?? ''},${f.lng ?? f.longitude ?? ''}|` +
      `${f.players_present ?? f.playersPresent ?? ''}:${f.max_players ?? f.maxPlayers ?? ''}|` +
      `${f.has_nets ?? f.hasNets ?? ''}|${f.has_water_cooler ?? f.has_water ?? f.hasWaterCooler ?? f.hasWater ?? ''}|` +
      `${f.opening_hours ?? f.openingHours ?? ''}|${f.notes ?? ''}|` +
      `${gameFingerprint(ag)}|` +
      `${upcomingFingerprint}`
  }

  return parts.join('\n')
}

function isPositionWithinBounds(position, bounds) {
  const [lat, lng] = position
  return (
    lat <= bounds.getNorth() &&
    lat >= bounds.getSouth() &&
    lng <= bounds.getEast() &&
    lng >= bounds.getWest()
  )
}

function mergeFieldsById(currentFields, loadedFields, bounds) {
  const incomingById = new Map()
  for (const field of loadedFields) {
    if (field?.id != null) {
      incomingById.set(field.id, field)
    }
  }

  // Upsert in place: existing fields keep their array position, and their
  // object identity when the data is unchanged; unseen fields are appended.
  // A bounds-limited response must never evict fields the user panned away
  // from (Map Fixing 1 audit, root cause #1) — that guarantee is preserved
  // below by only pruning fields whose own position falls inside the
  // bounds that were just queried.
  let merged = currentFields
  if (incomingById.size) {
    merged = currentFields.map((field) => {
      const incoming = incomingById.get(field.id)
      if (!incoming || fieldsFingerprint([incoming]) === fieldsFingerprint([field])) {
        return field
      }
      return incoming
    })

    const existingIds = new Set(currentFields.map((field) => field.id))
    for (const field of loadedFields) {
      if (field?.id != null && !existingIds.has(field.id)) {
        merged.push(field)
      }
    }
  }

  if (!bounds) {
    return merged
  }

  // A field whose coordinates fall inside the just-queried bounds but is
  // missing from the response is genuinely gone (removed/rejected/
  // unapproved) — drop it so it doesn't linger from a stale cache or an
  // earlier fetch. Fields outside these bounds are left untouched.
  return merged.filter((field) => {
    if (incomingById.has(field.id)) {
      return true
    }

    const position = getFieldPosition(field)
    if (!position) {
      return true
    }

    return !isPositionWithinBounds(position, bounds)
  })
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

function MapTileLayer({ onInitialTileError, onInitialTileLoaded, onInitialTilesReady }) {
  const tileEventHandlers = useMemo(
    () => ({
      load: onInitialTilesReady,
      tileload: onInitialTileLoaded,
      tileerror: onInitialTileError,
    }),
    [onInitialTileError, onInitialTileLoaded, onInitialTilesReady],
  )

  return (
    <TileLayer
      attribution="&copy; OpenStreetMap contributors"
      eventHandlers={tileEventHandlers}
      url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    />
  )
}

function FieldLoader({ onError, onFieldsLoaded, onLoadingChange, reloadKey }) {
  const { t } = useTranslation()
  const latestRequestId = useRef(0)
  const debounceTimerRef = useRef(null)

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

        onFieldsLoaded(Array.isArray(fields) ? fields : [], bounds)
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
      if (debounceTimerRef.current) {
        window.clearTimeout(debounceTimerRef.current)
      }

      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = null
        loadFields(map.getBounds())
      }, FIELD_LOAD_DEBOUNCE_MS)
    },
  })

  useEffect(() => {
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current)
      debounceTimerRef.current = null
    }

    loadFields(map.getBounds())
  }, [loadFields, map, reloadKey])

  useEffect(() => () => {
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current)
    }
  }, [])

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

function MapPage({
  currentUserId: authenticatedUserId,
  deepLinkTarget = null,
  onDeepLinkHandled,
}) {
  const { t, i18n } = useTranslation()
  const isRtl = i18n.resolvedLanguage === 'he'
  const zoomPosition = isRtl ? 'bottomleft' : 'bottomright'
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [userLocation, setUserLocation] = useState(null)
  const [userLocationRequestId, setUserLocationRequestId] = useState(0)
  const cachedFieldsState = useMemo(() => readCachedFields(), [])
  const [fields, setFields] = useState(cachedFieldsState.fields)
  const fieldsRef = useRef(cachedFieldsState.fields)
  const fieldsFingerprintRef = useRef(fieldsFingerprint(cachedFieldsState.fields))
  const notificationFieldsRequestRef = useRef(0)
  const notificationSyncRef = useRef(null)
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
  // Non-blocking banner about the last location request. '' = hidden.
  // The Hebrew copy is dictated by docs/location-permission-strategy.md §7.
  const [locationNotice, setLocationNotice] = useState('')
  const [isLocatingUser, setIsLocatingUser] = useState(false)
  // '' | 'loading' | 'unavailable' — tracks resolution of an incoming
  // /game/{id} or /field/{id} deep link (ISSUE-272, ISSUE-273). Field/UI
  // state itself still lives in `selectedField`; this only drives the
  // shared loading/unavailable affordances below.
  const [deepLinkStatus, setDeepLinkStatus] = useState('')
  const [deepLinkMessage, setDeepLinkMessage] = useState('')
  const [tileLoadStatus, setTileLoadStatus] = useState('loading')
  const tileLoadStatusRef = useRef('loading')
  const initialTileStatsRef = useRef({ loaded: 0, failed: 0 })

  // Keep the merge base in sync with any future setFields caller that does
  // not go through commitFields.
  useEffect(() => {
    fieldsRef.current = fields
    fieldsFingerprintRef.current = fieldsFingerprint(fields)
  }, [fields])

  useEffect(() => {
    tileLoadStatusRef.current = tileLoadStatus
  }, [tileLoadStatus])

  // ISSUE-255: no automatic location request on mount. Location is only
  // acquired when the user taps "My Location", per point-of-need strategy.
  // When we already hold a fix from an earlier grant and the app returns
  // to the foreground, re-check the permission — if it was revoked in
  // Android settings, drop the marker cleanly and warn once.
  useEffect(() => {
    let isMounted = true
    let listenerHandle = null

    const revalidate = async () => {
      if (!isMounted) {
        return
      }
      const { state } = await checkExistingPermission()
      if (!isMounted) {
        return
      }
      if (state === 'denied') {
        setUserLocation((current) => (current ? null : current))
        setLocationNotice((currentNotice) =>
          currentNotice || t('map.locationRevoked'),
        )
      }
    }

    ;(async () => {
      const registration = await CapacitorApp.addListener('appStateChange', ({ isActive }) => {
        if (isActive) {
          revalidate()
        }
      })
      if (!isMounted) {
        registration.remove?.()
        return
      }
      listenerHandle = registration
    })().catch(() => {
      // No @capacitor/app on web / plugin failure: skip the resume hook.
    })

    return () => {
      isMounted = false
      listenerHandle?.remove?.()
    }
  }, [t])

  const handleRequestUserLocation = useCallback(async () => {
    if (isLocatingUser) {
      return
    }

    setIsLocatingUser(true)
    try {
      const result = await getCurrentLocation({ highAccuracy: true })
      if (result.ok) {
        const loc = result.location

        // Check if the successful location is actually malformed
        const failureType = classifyLocationFailure(loc)
        if (failureType === 'MALFORMED_LOCATION') {
          setUserLocation(null)
          setLocationNotice(t(getLocationFailureMessage(failureType)))
          return
        }

        const nextUserLocation = {
          position: [loc.latitude, loc.longitude],
          accuracy: loc.accuracyMeters,
        }
        setUserLocation(nextUserLocation)
        setCenter(nextUserLocation.position)
        setUserLocationRequestId((currentRequestId) => currentRequestId + 1)

        const markerEval = evaluateLocationAccuracy(loc, USE_CASES.USER_MARKER)
        const fieldsEval = evaluateLocationAccuracy(loc, USE_CASES.NEARBY_FIELDS)

        if (!markerEval.isAccurateEnough || !fieldsEval.isAccurateEnough) {
          setLocationNotice(`${t('map.approximateLocationWarning')} ${t('map.nearbyFieldsWarning')}`)
        } else {
          setLocationNotice('')
        }
        return
      }

      const failureType = classifyLocationFailure(result)
      const msgKey = getLocationFailureMessage(failureType)
      setLocationNotice(t(msgKey))
    } finally {
      setIsLocatingUser(false)
    }
  }, [isLocatingUser, t])

  const refreshNotifications = useCallback(() => {
    return notificationSyncRef.current?.refresh() ?? Promise.resolve({ applied: false })
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
    const notificationSync = createNotificationSync({
      loadNotifications: getNotifications,
      loadUnreadCount: getUnreadNotificationCount,
      onNotifications: setNotifications,
      onUnreadCount: setUnreadNotificationCount,
    })
    notificationSyncRef.current = notificationSync
    void notificationSync.refresh()

    return () => {
      notificationSync.dispose()
      if (notificationSyncRef.current === notificationSync) {
        notificationSyncRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    function handleNativePush() {
      notificationSyncRef.current?.handleForegroundPush()
    }

    window.addEventListener('native-push-received', handleNativePush)
    return () => {
      window.removeEventListener('native-push-received', handleNativePush)
    }
  }, [refreshNotifications])

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

  const handleInitialTilesReady = useCallback(() => {
    setTileLoadStatus((currentStatus) => (
      currentStatus === 'loading' && initialTileStatsRef.current.loaded === 0 &&
        initialTileStatsRef.current.failed > 0
        ? 'error'
        : 'ready'
    ))
  }, [])

  const handleInitialTileLoaded = useCallback(() => {
    if (tileLoadStatusRef.current === 'loading') {
      initialTileStatsRef.current.loaded += 1
    }
  }, [])

  const handleInitialTileError = useCallback(() => {
    if (tileLoadStatusRef.current === 'loading') {
      initialTileStatsRef.current.failed += 1
    }
  }, [])

  const commitFields = useCallback((nextFields) => {
    const nextFingerprint = fieldsFingerprint(nextFields)

    if (fieldsFingerprintRef.current === nextFingerprint) {
      return fieldsRef.current
    }

    fieldsFingerprintRef.current = nextFingerprint
    fieldsRef.current = nextFields
    setFields(nextFields)
    writeCachedFields(nextFields)

    return nextFields
  }, [])

  const upsertFieldById = useCallback((field) => {
    const currentFields = fieldsRef.current
    const existingIndex = currentFields.findIndex((candidate) => candidate.id === field.id)
    const nextFields = existingIndex === -1
      ? [...currentFields, field]
      : currentFields.map((candidate) => (candidate.id === field.id ? field : candidate))

    return commitFields(nextFields)
  }, [commitFields])

  const handleFieldsLoaded = useCallback((loadedFields, bounds) => {
    const merged = mergeFieldsById(fieldsRef.current, loadedFields, bounds)
    commitFields(merged)

    setSelectedField((currentField) => {
      if (!currentField) {
        return currentField
      }

      // If the merge just pruned this field (confirmed gone — e.g. removed
      // by an admin), close the panel instead of continuing to show stale
      // data for a field that no longer exists.
      const stillPresent = merged.some((field) => field.id === currentField.id)
      if (!stillPresent) {
        return null
      }

      return loadedFields.find((field) => field.id === currentField.id) ?? currentField
    })
  }, [commitFields])

  const handleSelectField = useCallback((field) => {
    setSelectedField(field)
  }, [])

  const fieldMarkers = useMemo(
    () =>
      fields.map((field) => (
        <FieldMarker
          field={field}
          key={field.id}
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
        upsertFieldById(updatedField)
        setSelectedField(updatedField)
        await refreshUnreadCount()
      } catch {
        refreshFields()
        await refreshUnreadCount()
      }
    },
    [refreshUnreadCount, selectedField?.id, upsertFieldById],
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
      // Same stale-response rule as FieldLoader: only the latest
      // notification-triggered load may merge into shared field state.
      const requestId = notificationFieldsRequestRef.current + 1
      notificationFieldsRequestRef.current = requestId

      try {
        const loadedFields = await getFields()
        const nextFields = Array.isArray(loadedFields) ? loadedFields : []
        if (requestId === notificationFieldsRequestRef.current) {
          // Notification loads use the same merge path as FieldLoader
          // responses so the cache, fingerprint, and merge base stay in sync.
          handleFieldsLoaded(nextFields)
        }
        // Finding this tap's target in this tap's response stays correct
        // even when a newer request has made the merge stale.
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

  // Shared by both deep-link resolvers below: merges a freshly-fetched
  // field into `fields` by id while keeping the marker cache/fingerprint
  // refs in sync with viewport-loaded fields.
  const mergeResolvedField = useCallback((field) => {
    upsertFieldById(field)
  }, [upsertFieldById])

  // ISSUE-272: resolves a /game/{game_id} deep link into the Game screen.
  // Always fetches fresh state from the server (never trusts cached field
  // data) so an existing game shows its latest status, a missing/deleted
  // game surfaces the unavailable state, and a finished/cancelled game is
  // still opened with its terminal status visible (not re-created).
  useEffect(() => {
    const targetGameId = deepLinkTarget?.routeType === 'game' ? deepLinkTarget.resourceId : null
    if (!targetGameId) {
      return undefined
    }

    let isCancelled = false

    async function resolveGameDeepLink() {
      setDeepLinkStatus('loading')
      setDeepLinkMessage('')

      try {
        const game = await getGameById(targetGameId)
        const fieldId = game?.field_id

        if (!fieldId) {
          throw new Error('game-missing-field-id')
        }

        const field = await getFieldById(fieldId)
        if (isCancelled) {
          return
        }

        const activeGame = getActiveGame(field)
        const upcomingGames = field.upcoming_games ?? field.upcomingGames ?? []
        const isCurrentGame =
          activeGame?.id === game.id || upcomingGames.some((upcoming) => upcoming.id === game.id)

        // A finished/cancelled game no longer appears in active_game or
        // upcoming_games, so it must be injected to be shown at all.
        const resolvedField = isCurrentGame ? field : { ...field, active_game: game }

        mergeResolvedField(field)
        setSelectedField(resolvedField)
        if (!deepLinkTarget.analyticsDeferred) {
          recordLinkOpen(deepLinkTarget, 'valid')
        }
        setDeepLinkStatus('')
      } catch (resolveError) {
        if (isCancelled) {
          return
        }

        const statusCode = resolveError?.response?.status
        if (!deepLinkTarget.analyticsDeferred) {
          recordLinkOpen(deepLinkTarget, statusCode === 404 ? 'not_found' : 'invalid', {
            errorCategory: statusCode === 404 ? 'resource_not_found' : 'resolution_failed',
          })
        }
        setDeepLinkStatus('unavailable')
        setDeepLinkMessage(
          statusCode === 404 ? t('game.deepLinkNotFound') : t('game.deepLinkLoadError'),
        )
      } finally {
        if (!isCancelled) {
          onDeepLinkHandled?.()
        }
      }
    }

    resolveGameDeepLink()

    return () => {
      isCancelled = true
    }
  }, [deepLinkTarget, mergeResolvedField, onDeepLinkHandled, t])

  // ISSUE-273: resolves a /field/{field_id} deep link. Always fetches fresh
  // state from the server (getFieldById already returns 404 for pending and
  // rejected fields per the visibility rules in docs/deep-link-architecture.md
  // §6.5, so those need no separate handling here). A closed/renovation field
  // still returns 200 and is opened normally — FieldDetailsPanel already
  // surfaces `field.status` inline, the same as a marker click would.
  useEffect(() => {
    const targetFieldId = deepLinkTarget?.routeType === 'field' ? deepLinkTarget.resourceId : null
    if (!targetFieldId) {
      return undefined
    }

    let isCancelled = false

    async function resolveFieldDeepLink() {
      setDeepLinkStatus('loading')
      setDeepLinkMessage('')

      try {
        const field = await getFieldById(targetFieldId)
        if (isCancelled) {
          return
        }

        mergeResolvedField(field)
        setSelectedField(field)
        if (!deepLinkTarget.analyticsDeferred) {
          recordLinkOpen(deepLinkTarget, 'valid')
        }

        const position = getFieldPosition(field)
        if (position) {
          setCenter(position)
        }

        setDeepLinkStatus('')
      } catch (resolveError) {
        if (isCancelled) {
          return
        }

        const statusCode = resolveError?.response?.status
        if (!deepLinkTarget.analyticsDeferred) {
          recordLinkOpen(deepLinkTarget, statusCode === 404 ? 'not_found' : 'invalid', {
            errorCategory: statusCode === 404 ? 'resource_not_found' : 'resolution_failed',
          })
        }
        setDeepLinkStatus('unavailable')
        setDeepLinkMessage(
          statusCode === 404 ? t('field.deepLinkNotFound') : t('field.deepLinkLoadError'),
        )
      } finally {
        if (!isCancelled) {
          onDeepLinkHandled?.()
        }
      }
    }

    resolveFieldDeepLink()

    return () => {
      isCancelled = true
    }
  }, [deepLinkTarget, mergeResolvedField, onDeepLinkHandled, t])

  const notificationsLabel = unreadNotificationCount
    ? t('map.notificationsUnread', { count: unreadNotificationCount })
    : t('map.notifications')

  return (
    <main className={`map-page${currentUserId ? ' has-toolbar' : ''}`}>
      {deepLinkStatus === 'unavailable' ? (
        <div className="location-notice" role="alert">
          <span>{deepLinkMessage}</span>
          <button
            type="button"
            className="location-notice-dismiss"
            aria-label={t('map.dismissNotice')}
            onClick={() => setDeepLinkStatus('')}
          >
            ×
          </button>
        </div>
      ) : error ? (
        <div className="map-error" role="alert">{error}</div>
      ) : null}
      {fieldSubmitMessage ? <div className="map-success">{fieldSubmitMessage}</div> : null}
      {locationNotice ? (
        <div className="location-notice" role="status">
          <span>{locationNotice}</span>
          <button
            type="button"
            className="location-notice-dismiss"
            aria-label={t('map.dismissNotice')}
            onClick={() => setLocationNotice('')}
          >
            ×
          </button>
        </div>
      ) : null}

      <div className="map-floating-controls">
        <div className="map-actions-stack top-start">
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
        </div>

        {!selectedField ? (
          <div className="map-actions-stack bottom-start">
            <button
              className="floating-button my-location"
              type="button"
              aria-label={t('map.myLocation')}
              onClick={handleRequestUserLocation}
              disabled={isLocatingUser}
            >
              <LocateFixed size={22} />
            </button>
          </div>
        ) : null}

        {!selectedField ? (
          <div className="map-actions-stack bottom-center">
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
          </div>
        ) : null}
      </div>

      <MapContainer center={center} zoom={DEFAULT_ZOOM} className="map-canvas" zoomControl={false}>
        <MapTileLayer
          onInitialTileError={handleInitialTileError}
          onInitialTileLoaded={handleInitialTileLoaded}
          onInitialTilesReady={handleInitialTilesReady}
        />
        <ZoomControl position={zoomPosition} key={zoomPosition} />
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

      {tileLoadStatus === 'loading' ? (
        <div className="map-tile-loading" role="status" aria-live="polite">
          <span className="map-tile-loading-shimmer" aria-hidden="true" />
          <span className="map-tile-loading-card">
            <span className="map-loading-spinner" aria-hidden="true" />
            <span>{t('map.loadingTiles')}</span>
          </span>
        </div>
      ) : tileLoadStatus === 'error' ? (
        <div className="map-tile-warning" role="status">
          {t('map.tileLoadError')}
        </div>
      ) : null}

      {deepLinkStatus === 'loading' ? (
        <div className="map-loading" role="status" aria-live="polite">
          <span className="map-loading-spinner" aria-hidden="true" />
          <span>
            {deepLinkTarget?.routeType === 'field'
              ? t('field.deepLinkLoading')
              : t('game.deepLinkLoading')}
          </span>
        </div>
      ) : isFieldsLoading && !fields.length ? (
        <div className="map-loading" role="status" aria-live="polite">
          <span className="map-loading-spinner" aria-hidden="true" />
          <span>{t('map.loadingFields')}</span>
        </div>
      ) : null}

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
