import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { createGame } from '../api/games'

function getErrorMessage(error, t) {
  if (error?.response?.status === 401) {
    return t('openGame.authRequired')
  }

  const detail = error?.response?.data?.detail ?? error?.response?.data?.message ?? ''

  if (String(detail).toLowerCase().includes('active game already exists')) {
    return t('openGame.alreadyExists')
  }

  if (detail) {
    return String(detail)
  }

  return t('openGame.failed')
}

function OpenGameModal({ field, onClose, onCreated }) {
  const { t } = useTranslation()
  const fieldSportType = field?.sport_type ?? ''
  const [sportType, setSportType] = useState(fieldSportType === 'both' ? '' : fieldSportType)
  const [gameTiming, setGameTiming] = useState('now')
  const [scheduledDate, setScheduledDate] = useState('')
  const [scheduledTime, setScheduledTime] = useState('')
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
      setError(t('openGame.sportRequired'))
      return
    }

    if (!['football', 'basketball'].includes(sportType.trim())) {
      setError(t('openGame.chooseFootballOrBasketball'))
      return
    }

    if (!Number.isFinite(playersPresentNumber) || playersPresentNumber < 1) {
      setError(t('openGame.playersMin'))
      return
    }

    if (!Number.isFinite(maxPlayersNumber) || maxPlayersNumber < playersPresentNumber) {
      setError(t('openGame.maxPlayersInvalid'))
      return
    }

    let scheduledAt
    if (gameTiming === 'future') {
      if (!scheduledDate || !scheduledTime) {
        setError(t('openGame.futureDateRequired'))
        return
      }

      const scheduledDateTime = new Date(`${scheduledDate}T${scheduledTime}`)
      if (Number.isNaN(scheduledDateTime.getTime())) {
        setError(t('openGame.invalidDateTime'))
        return
      }

      if (scheduledDateTime.getTime() <= Date.now()) {
        setError(t('openGame.pastDate'))
        return
      }

      scheduledAt = scheduledDateTime.toISOString()
    }

    setError('')
    setIsSubmitting(true)

    try {
      const payload = {
        field_id: field.id,
        sport_type: sportType.trim(),
        players_present: playersPresentNumber,
        max_players: maxPlayersNumber,
        age_note: ageNote.trim(),
      }

      if (scheduledAt) {
        payload.scheduled_at = scheduledAt
      }

      await createGame(payload)
      await onCreated?.()
      onClose()
    } catch (createError) {
      setError(getErrorMessage(createError, t))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="open-game-modal" role="dialog" aria-modal="true" aria-labelledby="open-game-title">
        <button className="modal-close-button" type="button" onClick={onClose} aria-label={t('field.close')}>
          x
        </button>

        <h2 id="open-game-title">{t('openGame.title')}</h2>

        <form className="open-game-form" onSubmit={handleSubmit}>
          <div className="schedule-mode-options" role="radiogroup" aria-label={t('openGame.timing')}>
            <label>
              <input
                type="radio"
                name="gameTiming"
                value="now"
                checked={gameTiming === 'now'}
                onChange={(event) => setGameTiming(event.target.value)}
              />
              {t('openGame.now')}
            </label>
            <label>
              <input
                type="radio"
                name="gameTiming"
                value="future"
                checked={gameTiming === 'future'}
                onChange={(event) => setGameTiming(event.target.value)}
              />
              {t('openGame.future')}
            </label>
          </div>

          {gameTiming === 'future' ? (
            <div className="future-game-fields">
              <label>
                {t('openGame.date')}
                <input
                  type="date"
                  value={scheduledDate}
                  onChange={(event) => setScheduledDate(event.target.value)}
                  required
                />
              </label>

              <label>
                {t('openGame.time')}
                <input
                  type="time"
                  value={scheduledTime}
                  onChange={(event) => setScheduledTime(event.target.value)}
                  required
                />
              </label>
            </div>
          ) : null}

          <label>
            {t('openGame.sportType')}
            <select
              value={sportType}
              onChange={(event) => setSportType(event.target.value)}
              required
            >
              {fieldSportType === 'both' ? <option value="">{t('openGame.chooseSport')}</option> : null}
              {(fieldSportType === 'football' || fieldSportType === 'both') ? (
                <option value="football">{t('openGame.football')}</option>
              ) : null}
              {(fieldSportType === 'basketball' || fieldSportType === 'both') ? (
                <option value="basketball">{t('openGame.basketball')}</option>
              ) : null}
            </select>
          </label>

          <label>
            {t('openGame.playersPresent')}
            <input
              type="number"
              inputMode="numeric"
              pattern="[0-9]*"
              min="1"
              value={playersPresent}
              onChange={(event) => setPlayersPresent(event.target.value)}
              required
            />
          </label>

          <label>
            {t('openGame.maxPlayers')}
            <input
              type="number"
              inputMode="numeric"
              pattern="[0-9]*"
              min="2"
              value={maxPlayers}
              onChange={(event) => setMaxPlayers(event.target.value)}
              required
            />
          </label>

          <label>
            {t('openGame.ageNote')}
            <input
              type="text"
              value={ageNote}
              onChange={(event) => setAgeNote(event.target.value)}
              placeholder="18+"
            />
          </label>

          {error ? <p className="modal-error">{error}</p> : null}

          <button className="primary-panel-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? t('openGame.opening') : t('openGame.title')}
          </button>
        </form>
      </section>
    </div>
  )
}

export default OpenGameModal
