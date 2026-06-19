import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { adminCloseGame, adminExtendGame, getAdminGames } from '../../api/admin'

function GamesTable({ games, isActive, onExtend, onClose, workingGameId, locale, t }) {
  function formatValue(value, fallback = t('admin.missing')) {
    return value ? t(`values.${value}`, value) : fallback
  }

  function formatDate(value) {
    if (!value) {
      return t('admin.missing')
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return t('admin.missing')
    }

    return date.toLocaleString(locale)
  }

  function formatPlayers(game) {
    if (
      game.players_present === null ||
      game.players_present === undefined ||
      game.max_players === null ||
      game.max_players === undefined
    ) {
      return t('admin.missing')
    }

    return `${game.players_present} / ${game.max_players}`
  }

  function getParticipantsCount(game) {
    return game.participants?.length || 0
  }

  return (
    <div className="admin-table-wrap">
      <table className="admin-table admin-games-table">
        <thead>
          <tr>
            <th>{t('admin.field')}</th>
            <th>{t('admin.sport')}</th>
            <th>{t('admin.players')}</th>
            <th>{t('admin.status')}</th>
            <th>{t('admin.started')}</th>
            <th>{t('admin.expires')}</th>
            <th>{t('admin.participants')}</th>
            {isActive ? <th>{t('admin.actions')}</th> : null}
          </tr>
        </thead>
        <tbody>
          {games.map((game) => (
            <tr key={game.id}>
              <td>{formatValue(game.field_name, t('admin.unknownField'))}</td>
              <td>{formatValue(game.sport_type)}</td>
              <td>{formatPlayers(game)}</td>
              <td>{formatValue(game.status)}</td>
              <td>{formatDate(game.started_at)}</td>
              <td>{formatDate(game.expires_at)}</td>
              <td>{getParticipantsCount(game)}</td>
              {isActive ? (
                <td>
                  <div className="admin-game-actions">
                    <button
                      className="admin-secondary-button"
                      type="button"
                      onClick={() => onExtend(game.id)}
                      disabled={workingGameId === game.id}
                    >
                      {t('admin.extend')}
                    </button>
                    <button
                      className="admin-danger-button"
                      type="button"
                      onClick={() => onClose(game.id)}
                      disabled={workingGameId === game.id}
                    >
                      {t('admin.close')}
                    </button>
                  </div>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AdminGames() {
  const { i18n, t } = useTranslation()
  const [activeGames, setActiveGames] = useState([])
  const [finishedGames, setFinishedGames] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [workingGameId, setWorkingGameId] = useState('')
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  async function loadGames() {
    setIsLoading(true)
    setLoadError('')

    try {
      const games = await getAdminGames()
      setActiveGames(Array.isArray(games.active) ? games.active : [])
      setFinishedGames(Array.isArray(games.finished) ? games.finished : [])
    } catch {
      setLoadError(t('admin.failedLoadGames'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let isMounted = true

    async function loadInitialGames() {
      try {
        const games = await getAdminGames()
        if (isMounted) {
          setActiveGames(Array.isArray(games.active) ? games.active : [])
          setFinishedGames(Array.isArray(games.finished) ? games.finished : [])
        }
      } catch {
        if (isMounted) {
          setLoadError(t('admin.failedLoadGames'))
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadInitialGames()

    return () => {
      isMounted = false
    }
  }, [t])

  async function handleExtend(gameId) {
    setWorkingGameId(gameId)
    setActionError('')

    try {
      await adminExtendGame(gameId)
      await loadGames()
    } catch {
      setActionError(t('admin.failedExtendGame'))
    } finally {
      setWorkingGameId('')
    }
  }

  async function handleClose(gameId) {
    setWorkingGameId(gameId)
    setActionError('')

    try {
      await adminCloseGame(gameId)
      await loadGames()
    } catch {
      setActionError(t('admin.failedCloseGame'))
    } finally {
      setWorkingGameId('')
    }
  }

  return (
    <div className="admin-games">
      {isLoading ? <p className="admin-loading">{t('admin.loadingGames')}</p> : null}
      {loadError ? <p className="admin-error">{loadError}</p> : null}
      {actionError ? <p className="admin-error">{actionError}</p> : null}

      {!isLoading && !loadError ? (
        <>
          <section className="admin-games-section" aria-labelledby="active-games-title">
            <h3 id="active-games-title">{t('admin.activeGames')}</h3>
            {activeGames.length ? (
              <GamesTable
                games={activeGames}
                isActive
                onExtend={handleExtend}
                onClose={handleClose}
                workingGameId={workingGameId}
                locale={locale}
                t={t}
              />
            ) : (
              <p className="admin-empty-state">{t('admin.noActiveGames')}</p>
            )}
          </section>

          <section className="admin-games-section" aria-labelledby="finished-games-title">
            <h3 id="finished-games-title">{t('admin.finishedGames')}</h3>
            {finishedGames.length ? (
              <GamesTable
                games={finishedGames}
                isActive={false}
                workingGameId={workingGameId}
                locale={locale}
                t={t}
              />
            ) : (
              <p className="admin-empty-state">{t('admin.noFinishedGames')}</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}

export default AdminGames
