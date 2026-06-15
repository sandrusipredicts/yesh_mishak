import { useEffect, useState } from 'react'

import { adminCloseGame, adminExtendGame, getAdminGames } from '../../api/admin'

function formatValue(value, fallback = '—') {
  return value || fallback
}

function formatDate(value) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return date.toLocaleString()
}

function formatPlayers(game) {
  if (
    game.players_present === null ||
    game.players_present === undefined ||
    game.max_players === null ||
    game.max_players === undefined
  ) {
    return '—'
  }

  return `${game.players_present} / ${game.max_players}`
}

function getParticipantsCount(game) {
  return game.participants?.length || 0
}

function GamesTable({ games, isActive, onExtend, onClose, workingGameId }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table admin-games-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Sport</th>
            <th>Players</th>
            <th>Status</th>
            <th>Started</th>
            <th>Expires</th>
            <th>Participants</th>
            {isActive ? <th>Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {games.map((game) => (
            <tr key={game.id}>
              <td>{formatValue(game.field_name, 'Unknown field')}</td>
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
                      Extend
                    </button>
                    <button
                      className="admin-danger-button"
                      type="button"
                      onClick={() => onClose(game.id)}
                      disabled={workingGameId === game.id}
                    >
                      Close
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
  const [activeGames, setActiveGames] = useState([])
  const [finishedGames, setFinishedGames] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [workingGameId, setWorkingGameId] = useState('')

  async function loadGames() {
    setIsLoading(true)
    setLoadError('')

    try {
      const games = await getAdminGames()
      setActiveGames(Array.isArray(games.active) ? games.active : [])
      setFinishedGames(Array.isArray(games.finished) ? games.finished : [])
    } catch {
      setLoadError('Failed to load games.')
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
          setLoadError('Failed to load games.')
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
  }, [])

  async function handleExtend(gameId) {
    setWorkingGameId(gameId)
    setActionError('')

    try {
      await adminExtendGame(gameId)
      await loadGames()
    } catch {
      setActionError('Failed to extend game.')
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
      setActionError('Failed to close game.')
    } finally {
      setWorkingGameId('')
    }
  }

  return (
    <div className="admin-games">
      {isLoading ? <p className="admin-loading">Loading games...</p> : null}
      {loadError ? <p className="admin-error">{loadError}</p> : null}
      {actionError ? <p className="admin-error">{actionError}</p> : null}

      {!isLoading && !loadError ? (
        <>
          <section className="admin-games-section" aria-labelledby="active-games-title">
            <h3 id="active-games-title">Active Games</h3>
            {activeGames.length ? (
              <GamesTable
                games={activeGames}
                isActive
                onExtend={handleExtend}
                onClose={handleClose}
                workingGameId={workingGameId}
              />
            ) : (
              <p className="admin-empty-state">No active games.</p>
            )}
          </section>

          <section className="admin-games-section" aria-labelledby="finished-games-title">
            <h3 id="finished-games-title">Recently Finished Games</h3>
            {finishedGames.length ? (
              <GamesTable games={finishedGames} isActive={false} workingGameId={workingGameId} />
            ) : (
              <p className="admin-empty-state">No finished games found.</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}

export default AdminGames
