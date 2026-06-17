import { useState } from 'react'

import { createGame } from '../api/games'

function getErrorMessage(error) {
  if (error?.response?.status === 401) {
    return 'צריך להתחבר כדי לפתוח משחק'
  }

  const detail = error?.response?.data?.detail ?? error?.response?.data?.message ?? ''

  if (String(detail).toLowerCase().includes('active game already exists')) {
    return 'כבר יש משחק פעיל במגרש הזה'
  }

  if (detail) {
    return String(detail)
  }

  return 'Could not open game. Please try again.'
}

function OpenGameModal({ field, onClose, onCreated }) {
  const fieldSportType = field?.sport_type ?? ''
  const [sportType, setSportType] = useState(fieldSportType === 'both' ? '' : fieldSportType)
  const [playersPresent, setPlayersPresent] = useState('1')
  const [maxPlayers, setMaxPlayers] = useState('10')
  const [ageNote, setAgeNote] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()

    const playersPresentNumber = Number(playersPresent)
    const maxPlayersNumber = Number(maxPlayers)

    if (!sportType.trim()) {
      setError('Sport type is required.')
      return
    }

    if (!['football', 'basketball'].includes(sportType.trim())) {
      setError('Choose football or basketball.')
      return
    }

    if (!Number.isFinite(playersPresentNumber) || playersPresentNumber < 1) {
      setError('Players present must be at least 1.')
      return
    }

    if (!Number.isFinite(maxPlayersNumber) || maxPlayersNumber < playersPresentNumber) {
      setError('Max players must be greater than or equal to players present.')
      return
    }

    setError('')
    setIsSubmitting(true)

    try {
      await createGame({
        field_id: field.id,
        sport_type: sportType.trim(),
        players_present: playersPresentNumber,
        max_players: maxPlayersNumber,
        age_note: ageNote.trim(),
      })
      await onCreated?.()
      onClose()
    } catch (createError) {
      setError(getErrorMessage(createError))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="open-game-modal" role="dialog" aria-modal="true" aria-labelledby="open-game-title">
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
          x
        </button>

        <h2 id="open-game-title">Open Game</h2>

        <form className="open-game-form" onSubmit={handleSubmit}>
          <label>
            Sport type
            <select
              value={sportType}
              onChange={(event) => setSportType(event.target.value)}
              required
            >
              {fieldSportType === 'both' ? <option value="">Choose sport</option> : null}
              {(fieldSportType === 'football' || fieldSportType === 'both') ? (
                <option value="football">Football</option>
              ) : null}
              {(fieldSportType === 'basketball' || fieldSportType === 'both') ? (
                <option value="basketball">Basketball</option>
              ) : null}
            </select>
          </label>

          <label>
            Players present
            <input
              type="number"
              min="1"
              value={playersPresent}
              onChange={(event) => setPlayersPresent(event.target.value)}
              required
            />
          </label>

          <label>
            Max players
            <input
              type="number"
              min="2"
              value={maxPlayers}
              onChange={(event) => setMaxPlayers(event.target.value)}
              required
            />
          </label>

          <label>
            Age note
            <input
              type="text"
              value={ageNote}
              onChange={(event) => setAgeNote(event.target.value)}
              placeholder="18+"
            />
          </label>

          {error ? <p className="modal-error">{error}</p> : null}

          <button className="primary-panel-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Opening...' : 'Open Game'}
          </button>
        </form>
      </section>
    </div>
  )
}

export default OpenGameModal
