import { useEffect, useMemo, useRef, useState } from 'react'

import { israelCities } from '../data/israelCities'

function normalizeSearchValue(value) {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function sortHebrewCities(cities) {
  return [...cities].sort((a, b) => a.localeCompare(b, 'he'))
}

function getCitySuggestions(query) {
  const normalizedQuery = normalizeSearchValue(query)
  const sortedCities = sortHebrewCities(israelCities)

  if (!normalizedQuery) {
    return sortedCities
  }

  const startsWithMatches = []
  const includesMatches = []

  sortedCities.forEach((cityName) => {
    const normalizedCityName = normalizeSearchValue(cityName)

    if (normalizedCityName.startsWith(normalizedQuery)) {
      startsWithMatches.push(cityName)
    } else if (normalizedCityName.includes(normalizedQuery)) {
      includesMatches.push(cityName)
    }
  })

  return [...sortHebrewCities(startsWithMatches), ...sortHebrewCities(includesMatches)]
}

function OnboardingPage({ onComplete }) {
  const selectorRef = useRef(null)
  const [city, setCity] = useState('')
  const [error, setError] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const normalizedCity = city.trim()

  const suggestions = useMemo(() => {
    return getCitySuggestions(city)
  }, [city])

  useEffect(() => {
    function handleDocumentMouseDown(event) {
      if (!selectorRef.current?.contains(event.target)) {
        setIsDropdownOpen(false)
      }
    }

    document.addEventListener('mousedown', handleDocumentMouseDown)

    return () => {
      document.removeEventListener('mousedown', handleDocumentMouseDown)
    }
  }, [])

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
    setIsDropdownOpen(false)
  }

  function handleInputKeyDown(event) {
    if (event.key === 'Escape') {
      setIsDropdownOpen(false)
      return
    }

    if (!isDropdownOpen && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      setIsDropdownOpen(true)
      return
    }

    if (!suggestions.length) {
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightedIndex((currentIndex) => (currentIndex + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex((currentIndex) => (
        currentIndex === 0 ? suggestions.length - 1 : currentIndex - 1
      ))
    } else if (event.key === 'Enter' && isDropdownOpen) {
      event.preventDefault()
      handleSuggestionClick(suggestions[highlightedIndex])
    }
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
          <div className="city-selector" ref={selectorRef}>
            <label htmlFor="city-input">עיר</label>
            <input
              id="city-input"
              type="text"
              value={city}
              onFocus={() => setIsDropdownOpen(true)}
              onChange={(event) => {
                setCity(event.target.value)
                setError('')
                setHighlightedIndex(0)
                setIsDropdownOpen(true)
              }}
              onKeyDown={handleInputKeyDown}
              autoComplete="off"
              aria-autocomplete="list"
              aria-expanded={isDropdownOpen}
              aria-controls="city-suggestions"
              placeholder="לדוגמה: ירוחם"
            />

            {isDropdownOpen && suggestions.length > 0 ? (
              <ul id="city-suggestions" className="city-suggestions" aria-label="City suggestions">
                {suggestions.map((cityName, index) => (
                  <li key={cityName}>
                    <button
                      type="button"
                      className={index === highlightedIndex ? 'is-highlighted' : ''}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => handleSuggestionClick(cityName)}
                    >
                      {cityName}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

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
