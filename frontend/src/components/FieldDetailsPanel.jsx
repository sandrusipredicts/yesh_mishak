import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MapPin } from 'lucide-react'
import GamePanel from './GamePanel'
import OpenGameModal from './OpenGameModal'
import FieldReportModal from './FieldReportModal'
import Modal from './Modal'
import { launchGoogleMapsNavigation } from '../api/googleMapsNavigation'
import { getLastKnownLocation } from '../api/locationService'
import { launchWazeNavigation } from '../api/wazeNavigation'
import { evaluateLocationAccuracy, USE_CASES } from '../utils/locationAccuracy'

function getActiveGame(field) {
  return field?.active_game ?? field?.activeGame ?? null
}

function getUpcomingGames(field) {
  const upcomingGames = field?.upcoming_games ?? field?.upcomingGames ?? []
  return Array.isArray(upcomingGames) ? upcomingGames : []
}

function getWaterCoolerValue(field) {
  return field.has_water_cooler ?? field.has_water
}

function getNavigationCoordinates(field) {
  const rawLatitude = field?.lat ?? field?.latitude
  const rawLongitude = field?.lng ?? field?.longitude

  if (
    rawLatitude === null ||
    rawLatitude === undefined ||
    rawLongitude === null ||
    rawLongitude === undefined ||
    (typeof rawLatitude === 'string' && rawLatitude.trim() === '') ||
    (typeof rawLongitude === 'string' && rawLongitude.trim() === '')
  ) {
    return null
  }

  const latitude = Number(rawLatitude)
  const longitude = Number(rawLongitude)

  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null
  }

  return { latitude, longitude }
}

function FieldDetailsPanel({ field, onClose, onGameCreated, currentUserId }) {
  const { i18n, t } = useTranslation()
  const [isOpenGameModalOpen, setIsOpenGameModalOpen] = useState(false)
  const [isNavigationModalOpen, setIsNavigationModalOpen] = useState(false)
  const [isFieldReportModalOpen, setIsFieldReportModalOpen] = useState(false)

  if (!field) {
    return null
  }

  const activeGame = getActiveGame(field)
  const upcomingGames = getUpcomingGames(field)
  const status = field.approval_status ?? field.status ?? ''
  const isPending = String(status).toLowerCase() === 'pending'
  const navigationCoordinates = getNavigationCoordinates(field)
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  function formatBoolean(value) {
    if (value === true) {
      return t('field.yes')
    }

    if (value === false) {
      return t('field.no')
    }

    return t('field.notSpecified')
  }

  function getPlayerCount(game) {
    if (!game) {
      return null
    }

    const playersPresent = game.players_present
    const maxPlayers = game.max_players

    if (playersPresent === undefined || maxPlayers === undefined) {
      return null
    }

    return t('field.playersOutOf', { current: playersPresent, max: maxPlayers })
  }

  function formatScheduledAt(value) {
    if (!value) {
      return t('field.dateNotSet')
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return t('field.invalidDate')
    }

    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date)
  }

  async function openNavigation(provider) {
    if (!navigationCoordinates) {
      setIsNavigationModalOpen(false)
      return
    }

    const userLoc = getLastKnownLocation()
    if (userLoc) {
      evaluateLocationAccuracy(userLoc, USE_CASES.NAVIGATION_LAUNCH)
    }

    const { latitude, longitude } = navigationCoordinates

    if (provider === 'waze') {
      const result = await launchWazeNavigation(latitude, longitude)
      if (result.opened) {
        setIsNavigationModalOpen(false)
      }
      return
    }

    const result = launchGoogleMapsNavigation(latitude, longitude)
    if (result.opened) {
      setIsNavigationModalOpen(false)
    }
  }

  function handleGameStateChanged() {
    return onGameCreated?.(field.id)
  }

  const playerCount = getPlayerCount(activeGame)
  const isAnyModalOpen = isOpenGameModalOpen || isFieldReportModalOpen || isNavigationModalOpen

  return (
    <>
      <aside
        className="field-details-panel"
        aria-label={t('field.details')}
        inert={isAnyModalOpen}
      >
      <button className="panel-close-button" type="button" onClick={onClose} aria-label={t('field.close')}>
        x
      </button>

      <div className="panel-header">
        <h2>{field.name ?? t('field.unnamed')}</h2>
        {isPending ? <span className="approval-badge">{t('field.pendingApproval')}</span> : null}
      </div>

      <dl className="field-details-list">
        <div>
          <dt>{t('field.surfaceType')}</dt>
          <dd>{field.surface_type ? t(`values.${field.surface_type}`, field.surface_type) : t('field.notSpecified')}</dd>
        </div>
        <div>
          <dt>{t('field.hasNets')}</dt>
          <dd>{formatBoolean(field.has_nets)}</dd>
        </div>
        <div>
          <dt>{t('field.hasWaterCooler')}</dt>
          <dd>{formatBoolean(getWaterCoolerValue(field))}</dd>
        </div>
        <div>
          <dt>{t('field.openingHours')}</dt>
          <dd>{field.opening_hours ?? t('field.notSpecified')}</dd>
        </div>
        <div>
          <dt>{t('field.notes')}</dt>
          <dd>{field.notes ?? t('field.noNotes')}</dd>
        </div>
        <div>
          <dt>{t('field.status')}</dt>
          <dd>{status ? t(`values.${status}`, status) : t('field.notSpecified')}</dd>
        </div>
      </dl>

      {activeGame ? (
        <div className="active-game-summary">
          <p>{playerCount ?? t('field.activeGameAvailable')}</p>
          <GamePanel
            game={activeGame}
            currentUserId={currentUserId}
            onUpdate={handleGameStateChanged}
          />
        </div>
      ) : null}

      {upcomingGames.length ? (
        <section className="upcoming-games-section" aria-labelledby="upcoming-games-title">
          <h3 id="upcoming-games-title">{t('field.upcomingGames')}</h3>
          <div className="upcoming-games-list">
            {upcomingGames.map((game) => (
              <article className="upcoming-game-card" key={game.id}>
                <p>{formatScheduledAt(game.scheduled_at)}</p>
                <GamePanel
                  game={game}
                  currentUserId={currentUserId}
                  onUpdate={handleGameStateChanged}
                />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {!activeGame ? (
        <button
          className="primary-panel-button"
          type="button"
          onClick={() => setIsOpenGameModalOpen(true)}
        >
          {t('field.openGame')}
        </button>
      ) : null}

      {navigationCoordinates ? (
        <button
          className="primary-panel-button navigation-panel-button"
          type="button"
          onClick={() => setIsNavigationModalOpen(true)}
        >
          <MapPin size={18} aria-hidden="true" />
          <span>{t('field.navigateToField')}</span>
        </button>
      ) : null}

      <button
        className="primary-panel-button report-panel-button"
        type="button"
        onClick={() => setIsFieldReportModalOpen(true)}
      >
        {t('field.reportField')}
      </button>

      </aside>

      {isOpenGameModalOpen ? (
        <OpenGameModal
          field={field}
          onClose={() => setIsOpenGameModalOpen(false)}
          onCreated={handleGameStateChanged}
        />
      ) : null}

      {isFieldReportModalOpen ? (
        <FieldReportModal
          field={field}
          onClose={() => setIsFieldReportModalOpen(false)}
        />
      ) : null}

      <Modal
        isOpen={isNavigationModalOpen && !!navigationCoordinates}
        onClose={() => setIsNavigationModalOpen(false)}
        className="navigation-modal"
        ariaLabelledBy="navigation-modal-title"
      >
        <h2 id="navigation-modal-title">{t('field.openNavigation')}</h2>

        <div className="navigation-options">
          <button
            className="navigation-option-button waze"
            type="button"
            onClick={() => openNavigation('waze')}
          >
            <span className="navigation-provider-dot" aria-hidden="true" />
            Waze
          </button>
          <button
            className="navigation-option-button google"
            type="button"
            onClick={() => openNavigation('google')}
          >
            <span className="navigation-provider-dot" aria-hidden="true" />
            Google Maps
          </button>
          <button
            className="navigation-cancel-button"
            type="button"
            onClick={() => setIsNavigationModalOpen(false)}
          >
            {t('field.cancel')}
          </button>
        </div>
      </Modal>
    </>
  )
}

export default FieldDetailsPanel
