import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import CityAutocomplete from '../CityAutocomplete'
import { israelCities } from '../../data/israelCities'
import { setAccountCity } from '../../onboarding/onboardingStorage'
import OnboardingLayout from './OnboardingLayout'

// Device-scoped onboarding completion/permission-education never repeats
// for a second account (E08-02 approved decision) — but the starting city
// is personal, account-scoped data. When an authenticated account has no
// city of its own yet, this is the *only* thing it is asked to do: no
// welcome/location/notifications/guide replay, no native permission APIs,
// reusing the existing onboarding city step's copy and the same shared
// OnboardingLayout/CityAutocomplete primitives rather than a second
// onboarding system.
function AccountCityStep({ userId, onSelected }) {
  const { t } = useTranslation()
  const [city, setCity] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const selectedCityIsValid = useMemo(() => israelCities.includes(city), [city])

  function handleContinue() {
    if (isBusy || !selectedCityIsValid) return
    setIsBusy(true)
    setAccountCity(userId, city)
    onSelected(city)
  }

  return (
    <OnboardingLayout
      title={t('onboarding.cityStep.title')}
      description={t('onboarding.cityStep.description')}
      primaryLabel={t('onboarding.continue')}
      onPrimary={handleContinue}
      primaryDisabled={!selectedCityIsValid}
      isBusy={isBusy}
    >
      <div className="onboarding-city-field">
        <label htmlFor="account-city-input">{t('onboarding.city')}</label>
        <CityAutocomplete
          id="account-city-input"
          value={city}
          onChange={setCity}
          cities={israelCities}
          placeholder={t('onboarding.cityPlaceholder')}
        />
        {city && !selectedCityIsValid ? <p role="alert">{t('onboarding.chooseCity')}</p> : null}
      </div>
    </OnboardingLayout>
  )
}

export default AccountCityStep
