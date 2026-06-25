import { useEffect, useId, useMemo, useRef, useState } from 'react'

const MAX_SUGGESTIONS = 10

function CityAutocomplete({
  id,
  value,
  onChange,
  disabled = false,
  cities,
  placeholder,
}) {
  const reactId = useId()
  const listboxId = `${id || reactId}-listbox`
  const optionIdPrefix = `${id || reactId}-option`
  const normalizedValue = value || ''
  const [inputText, setInputText] = useState(normalizedValue)
  const [lastSyncedValue, setLastSyncedValue] = useState(normalizedValue)
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)

  const wrapperRef = useRef(null)
  const inputTextRef = useRef(inputText)
  const valueRef = useRef(normalizedValue)
  const citiesRef = useRef(cities)

  if (normalizedValue !== lastSyncedValue) {
    setLastSyncedValue(normalizedValue)
    if (normalizedValue) {
      setInputText(normalizedValue)
    }
  }

  useEffect(() => {
    inputTextRef.current = inputText
  }, [inputText])

  useEffect(() => {
    valueRef.current = normalizedValue
  }, [normalizedValue])

  useEffect(() => {
    citiesRef.current = cities
  }, [cities])

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false)
        setHighlightedIndex(-1)
        if (!citiesRef.current.includes(inputTextRef.current.trim())) {
          setInputText(valueRef.current)
        }
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('touchstart', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [])

  const suggestions = useMemo(() => {
    const query = inputText.trim()
    if (!query) {
      return cities.slice(0, MAX_SUGGESTIONS)
    }
    const startsWith = []
    const contains = []
    for (const city of cities) {
      if (city.startsWith(query)) {
        startsWith.push(city)
      } else if (city.includes(query)) {
        contains.push(city)
      }
    }
    return [...startsWith, ...contains].slice(0, MAX_SUGGESTIONS)
  }, [inputText, cities])

  function selectCity(city) {
    setInputText(city)
    setIsOpen(false)
    setHighlightedIndex(-1)
    onChange(city)
  }

  function handleInputChange(event) {
    const next = event.target.value
    setInputText(next)
    setIsOpen(true)
    setHighlightedIndex(-1)
    if (cities.includes(next.trim())) {
      onChange(next.trim())
    } else if (normalizedValue) {
      onChange('')
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setIsOpen(true)
      setHighlightedIndex((index) => Math.min(index + 1, suggestions.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      if (isOpen && highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        event.preventDefault()
        selectCity(suggestions[highlightedIndex])
      }
    } else if (event.key === 'Escape') {
      setIsOpen(false)
      setHighlightedIndex(-1)
    }
  }

  const isExpanded = isOpen && !disabled && suggestions.length > 0

  return (
    <div className="city-autocomplete" ref={wrapperRef}>
      <input
        id={id}
        type="text"
        value={inputText}
        onChange={handleInputChange}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        autoComplete="off"
        dir="auto"
        placeholder={placeholder}
        role="combobox"
        aria-expanded={isExpanded}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-activedescendant={
          isExpanded && highlightedIndex >= 0
            ? `${optionIdPrefix}-${highlightedIndex}`
            : undefined
        }
      />
      {isExpanded ? (
        <ul
          id={listboxId}
          className="city-autocomplete-suggestions"
          role="listbox"
        >
          {suggestions.map((city, index) => (
            <li
              key={city}
              id={`${optionIdPrefix}-${index}`}
              role="option"
              aria-selected={index === highlightedIndex}
              className={
                index === highlightedIndex
                  ? 'city-autocomplete-option is-highlighted'
                  : 'city-autocomplete-option'
              }
              onMouseDown={(event) => {
                event.preventDefault()
                selectCity(city)
              }}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {city}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export default CityAutocomplete
