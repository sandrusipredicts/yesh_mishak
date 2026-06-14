import { useMemo, useState } from 'react'

import { israelCities } from '../data/israelCities'

function OnboardingPage({ onComplete }) {
  const [city, setCity] = useState('')
  const [error, setError] = useState('')
  const normalizedCity = city.trim()

  const suggestions = useMemo(() => {
    if (!normalizedCity) {
      return []
    }

    return israelCities
      .filter((cityName) => cityName.includes(normalizedCity))
      .slice(0, 6)
  }, [normalizedCity])

  function handleSubmit(event) {
    event.preventDefault()

    if (!normalizedCity) {
      setError('בחר עיר כדי להמשיך.')
      return
    }

    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', normalizedCity)
    onComplete?.()
  }

  function handleSuggestionClick(cityName) {
    setCity(cityName)
    setError('')
  }

  return (
    <main className="onboarding-page">
      <section className="onboarding-panel" aria-labelledby="onboarding-title">
        <h1 id="onboarding-title">yesh_mishak</h1>

        <ul className="onboarding-lines">
          <li>מצא משחקים לידך</li>
          <li>פתח משחק בשכונה שלך</li>
          <li>קבל התראה כשחסרים שחקנים</li>
        </ul>

        <form className="onboarding-form" onSubmit={handleSubmit}>
          <label htmlFor="city-input">עיר</label>
          <input
            id="city-input"
            type="text"
            value={city}
            onChange={(event) => {
              setCity(event.target.value)
              setError('')
            }}
            autoComplete="off"
            placeholder="לדוגמה: ירוחם"
          />

          {suggestions.length > 0 ? (
            <ul className="city-suggestions" aria-label="City suggestions">
              {suggestions.map((cityName) => (
                <li key={cityName}>
                  <button type="button" onClick={() => handleSuggestionClick(cityName)}>
                    {cityName}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          {error ? <p className="onboarding-error">{error}</p> : null}

          <button className="primary-panel-button" type="submit">
            Let's go
          </button>
        </form>
      </section>
    </main>
  )
}

export default OnboardingPage
