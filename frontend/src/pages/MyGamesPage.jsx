import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowRight, ArrowLeft } from 'lucide-react'
import { getMyGames } from '../api/games'

const STATUS_LABELS = {
  open: 'statusOpen',
  full: 'statusFull',
  finished: 'statusFinished',
  cancelled: 'statusCancelled',
}

const SPORT_LABELS = {
  football: 'football',
  basketball: 'basketball',
}

function parseDate(value) {
  if (!value) {
    return null
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDate(value, locale) {
  const date = parseDate(value)
  if (!date) {
    return ''
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function getDisplayDate(game) {
  if (game.scheduled_at) {
    return game.scheduled_at
  }

  return game.started_at || game.expires_at
}

function GameRow({ game, t, locale }) {
  const statusKey = STATUS_LABELS[game.status] || game.status
  const sportKey = SPORT_LABELS[game.sport_type] || game.sport_type
  const displayDate = formatDate(getDisplayDate(game), locale)

  return (
    <div className="my-games-row">
      <div className="my-games-row-main">
        <span className="my-games-field-name">{game.field_name || '—'}</span>
        {game.is_creator && (
          <span className="my-games-organizer-badge">{t('myGames.organizer')}</span>
        )}
      </div>
      <div className="my-games-row-details">
        <span className="my-games-sport">{t(`myGames.${sportKey}`, sportKey)}</span>
        <span className="my-games-separator">·</span>
        <span className="my-games-players">
          {t('myGames.players', { current: game.players_present, max: game.max_players })}
        </span>
        <span className="my-games-separator">·</span>
        <span className={`my-games-status my-games-status-${game.status}`}>
          {t(`myGames.${statusKey}`, game.status)}
        </span>
      </div>
      {displayDate && <div className="my-games-row-date">{displayDate}</div>}
    </div>
  )
}

function GameSection({ title, games, emptyText, t, locale }) {
  if (!games || games.length === 0) {
    return (
      <div className="my-games-section">
        <h3 className="my-games-section-title">{title}</h3>
        <p className="my-games-empty">{emptyText}</p>
      </div>
    )
  }

  return (
    <div className="my-games-section">
      <h3 className="my-games-section-title">{title} ({games.length})</h3>
      <div className="my-games-list">
        {games.map((game) => (
          <GameRow key={game.id} game={game} t={t} locale={locale} />
        ))}
      </div>
    </div>
  )
}

function filterCreatorOnly(games) {
  if (!games) {
    return []
  }

  return games.filter((g) => g.is_creator)
}

function MyGamesPage({ onBack }) {
  const { i18n, t } = useTranslation()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [organizerOnly, setOrganizerOnly] = useState(false)
  const isRtl = i18n.dir() === 'rtl'
  const BackArrow = isRtl ? ArrowRight : ArrowLeft

  const loadGames = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getMyGames()
      setData(result)
    } catch {
      setError(t('myGames.loadError'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadGames()
  }, [loadGames])

  const displayData = organizerOnly && data
    ? {
        active_games: filterCreatorOnly(data.active_games),
        upcoming_games: filterCreatorOnly(data.upcoming_games),
        past_games: filterCreatorOnly(data.past_games),
        cancelled_games: filterCreatorOnly(data.cancelled_games),
      }
    : data

  const hasAnyGames = data && (
    data.active_games?.length > 0 ||
    data.upcoming_games?.length > 0 ||
    data.past_games?.length > 0 ||
    data.cancelled_games?.length > 0
  )

  return (
    <div className="my-games-page">
      <header className="my-games-header">
        <button type="button" className="my-games-back-button" onClick={onBack}>
          <BackArrow size={20} />
          {t('myGames.back')}
        </button>
        <h2 className="my-games-title">{t('myGames.title')}</h2>
        {hasAnyGames && (
          <button
            type="button"
            className={`my-games-filter-toggle${organizerOnly ? ' my-games-filter-active' : ''}`}
            onClick={() => setOrganizerOnly((v) => !v)}
          >
            {t('myGames.organizedByMe')}
          </button>
        )}
      </header>

      {loading && <p className="my-games-loading">{t('myGames.loading')}</p>}
      {error && (
        <div className="my-games-error">
          <p>{error}</p>
          <button type="button" onClick={loadGames}>{t('admin.retry')}</button>
        </div>
      )}

      {!loading && !error && !hasAnyGames && (
        <p className="my-games-empty-all">{t('myGames.emptyAll')}</p>
      )}

      {!loading && !error && hasAnyGames && (
        <div className="my-games-sections">
          <GameSection
            title={t('myGames.activeGames')}
            games={displayData.active_games}
            emptyText={t('myGames.emptyActive')}
            t={t}
            locale={i18n.language}
          />
          <GameSection
            title={t('myGames.upcomingGames')}
            games={displayData.upcoming_games}
            emptyText={t('myGames.emptyUpcoming')}
            t={t}
            locale={i18n.language}
          />
          <GameSection
            title={t('myGames.pastGames')}
            games={displayData.past_games}
            emptyText={t('myGames.emptyPast')}
            t={t}
            locale={i18n.language}
          />
          <GameSection
            title={t('myGames.cancelledGames')}
            games={displayData.cancelled_games}
            emptyText={t('myGames.emptyCancelled')}
            t={t}
            locale={i18n.language}
          />
        </div>
      )}
    </div>
  )
}

export default MyGamesPage
