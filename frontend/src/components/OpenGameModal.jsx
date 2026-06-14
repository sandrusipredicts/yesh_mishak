import { useState } from 'react'

import { createGame } from '../api/games'

function getErrorMessage(error) {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message ?? ''

  if (String(detail).toLowerCase().includes('active game already exists')) {
    return 'כבר יש משחק פעיל במגרש הזה'
  }

  return 'Could not open game. Please try again.'
}

function OpenGameModal({ field, onClose, onCreated }) {
  const [sportType, setSportType] = useState(field?.sport_type ?? '')
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

    if (!Number.isFinite(playersPresentNumber) || playersPresentNumber < 1) {
      setError('Players present must be at least 1.')
      return
    }

    if (!Number.isFinite(maxPlayersNumber) || maxPlayersNumber <= playersPresentNumber) {
      setError('Max players must be greater than players present.')
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
      onCreated?.()
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
            <input
              type="text"
              value={sportType}
              onChange={(event) => setSportType(event.target.value)}
              required
            />
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
