import { useEffect, useMemo, useRef, useState } from 'react'
import { Bell, MapPin, PlusCircle, Search, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { checkPushPermission } from '../api/nativePushNotifications'
import { checkExistingPermission } from '../api/locationPermission'
import { getCurrentLocation, getLastKnownLocation } from '../api/locationService'
import CityAutocomplete from '../components/CityAutocomplete'
import OnboardingLayout from '../components/onboarding/OnboardingLayout'
import { israelCities } from '../data/israelCities'
import {
  completeOnboardingState,
  saveOnboardingState,
} from '../onboarding/onboardingStorage'
import { ONBOARDING_STEPS } from '../onboarding/onboardingSteps'

const TOTAL_STEPS = ONBOARDING_STEPS.length

function OnboardingPage({ initialState, onComplete, onEnableNotifications }) {
  const { t } = useTranslation()
  const [state, setState] = useState(initialState)
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState('')
  const actionPendingRef = useRef(false)
  const stepIndex = Math.max(0, ONBOARDING_STEPS.indexOf(state.currentStep))
  const step = ONBOARDING_STEPS[stepIndex]

  const updateState = (updates) => {
    const next = { ...state, ...updates }
    const result = saveOnboardingState(next)
    setState(result.state)
    if (!result.ok) setError(t('onboarding.persistenceWarning'))
    return result
  }

  const moveTo = (nextStep, completedStep = step) => {
    setError('')
    updateState({
      currentStep: nextStep,
      completedSteps: completedStep
        ? [...new Set([...state.completedSteps, completedStep])]
        : state.completedSteps,
    })
  }

  const next = () => moveTo(ONBOARDING_STEPS[Math.min(stepIndex + 1, TOTAL_STEPS - 1)])
  const back = () => moveTo(ONBOARDING_STEPS[Math.max(stepIndex - 1, 0)], '')

  useEffect(() => {
    let active = true
    if (step === 'location' && state.locationPermission === 'pending') {
      checkExistingPermission().then(({ state: permission }) => {
        if (!active) return
        if (permission === 'granted') updateState({ locationPermission: 'granted' })
        else if (permission === 'unsupported') updateState({ locationPermission: 'unavailable' })
      })
    }
    if (step === 'notifications' && state.notificationPermission === 'pending') {
      checkPushPermission().then((permission) => {
        if (!active) return
        if (permission === 'granted') updateState({ notificationPermission: 'granted' })
        else if (permission === 'unsupported') updateState({ notificationPermission: 'unavailable' })
        else if (permission === 'denied') updateState({ notificationPermission: 'denied' })
      })
    }
    return () => { active = false }
    // State is intentionally sampled when a permission step becomes active.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  async function handleLocationPermission() {
    if (actionPendingRef.current) return
    actionPendingRef.current = true
    setIsBusy(true)
    setError('')
    try {
      const result = await getCurrentLocation({ highAccuracy: true, maxAge: 0 })
      const outcome = result.ok
        ? 'granted'
        : result.error === 'unsupported' || result.error === 'unavailable'
          ? 'unavailable'
          : 'denied'
      updateState({
        locationPermission: outcome,
        ...(result.ok ? {
          currentStep: 'notifications',
          completedSteps: [...new Set([...state.completedSteps, 'location'])],
        } : {}),
      })
      if (!result.ok) setError(t(`onboarding.location.${outcome}Message`))
    } catch {
      updateState({ locationPermission: 'unavailable' })
      setError(t('onboarding.location.unavailableMessage'))
    } finally {
      actionPendingRef.current = false
      setIsBusy(false)
    }
  }

  async function handleNotificationPermission() {
    if (actionPendingRef.current) return
    actionPendingRef.current = true
    setIsBusy(true)
    setError('')
    try {
      const result = await onEnableNotifications?.()
      const outcome = result?.outcome === 'granted' ? 'granted'
        : result?.outcome === 'unsupported' ? 'unavailable'
          : 'denied'
      updateState({
        notificationPermission: outcome,
        ...(outcome === 'granted' ? {
          currentStep: 'guide',
          completedSteps: [...new Set([...state.completedSteps, 'notifications'])],
        } : {}),
      })
      if (outcome !== 'granted') setError(t(`onboarding.notifications.${outcome}Message`))
    } catch {
      updateState({ notificationPermission: 'unavailable' })
      setError(t('onboarding.notifications.unavailableMessage'))
    } finally {
      actionPendingRef.current = false
      setIsBusy(false)
    }
  }

  async function handleFinish() {
    if (actionPendingRef.current) return
    actionPendingRef.current = true
    setIsBusy(true)
    setError('')
    try {
      const completion = completeOnboardingState(state)
      if (!completion.ok) {
        setError(t('onboarding.completionSaveFailed'))
        return
      }
      let mapEntryIntent = { type: 'city', city: completion.state.city }
      if (completion.state.locationPermission === 'granted') {
        const cached = getLastKnownLocation()
        const locationResult = cached
          ? { ok: true, location: cached }
          : await getCurrentLocation({ highAccuracy: true })
        if (locationResult.ok) {
          mapEntryIntent = {
            type: 'location',
            latitude: locationResult.location.latitude,
            longitude: locationResult.location.longitude,
            accuracy: locationResult.location.accuracyMeters,
          }
        }
      }
      setState(completion.state)
      onComplete?.(mapEntryIntent, completion.state)
    } finally {
      actionPendingRef.current = false
      setIsBusy(false)
    }
  }

  const selectedCityIsValid = useMemo(
    () => israelCities.includes(state.city),
    [state.city],
  )

  const common = { step: stepIndex + 1, total: TOTAL_STEPS, isBusy, error }

  if (step === 'welcome') return (
    <OnboardingLayout {...common} title={t('onboarding.welcome.title')} description={t('onboarding.welcome.description')} primaryLabel={t('onboarding.continue')} onPrimary={next}>
      <div className="onboarding-hero-icon"><Users aria-hidden="true" size={48} /></div>
    </OnboardingLayout>
  )

  if (step === 'city') return (
    <OnboardingLayout {...common} title={t('onboarding.cityStep.title')} description={t('onboarding.cityStep.description')} primaryLabel={t('onboarding.continue')} secondaryLabel={t('onboarding.back')} onPrimary={next} onSecondary={back} primaryDisabled={!selectedCityIsValid}>
      <div className="onboarding-city-field">
        <label htmlFor="onboarding-city-input">{t('onboarding.city')}</label>
        <CityAutocomplete id="onboarding-city-input" value={state.city} onChange={(city) => updateState({ city })} cities={israelCities} placeholder={t('onboarding.cityPlaceholder')} />
        {state.city && !selectedCityIsValid ? <p role="alert">{t('onboarding.chooseCity')}</p> : null}
      </div>
    </OnboardingLayout>
  )

  if (step === 'location') return (
    <OnboardingLayout {...common} title={t('onboarding.location.title')} description={t('onboarding.location.description')} primaryLabel={state.locationPermission === 'granted' ? t('onboarding.continue') : t('onboarding.location.allow')} secondaryLabel={t('onboarding.notNow')} onPrimary={state.locationPermission === 'granted' ? next : handleLocationPermission} onSecondary={() => updateState({ locationPermission: 'skipped', currentStep: 'notifications', completedSteps: [...new Set([...state.completedSteps, 'location'])] })}>
      <div className="onboarding-hero-icon"><MapPin aria-hidden="true" size={48} /></div>
      <ul className="onboarding-benefits"><li>{t('onboarding.location.mapPosition')}</li><li>{t('onboarding.location.nearby')}</li><li>{t('onboarding.location.navigation')}</li></ul>
      <button className="onboarding-text-button" onClick={back} type="button">{t('onboarding.back')}</button>
    </OnboardingLayout>
  )

  if (step === 'notifications') return (
    <OnboardingLayout {...common} title={t('onboarding.notifications.title')} description={t('onboarding.notifications.description')} primaryLabel={state.notificationPermission === 'granted' ? t('onboarding.continue') : t('onboarding.notifications.enable')} secondaryLabel={t('onboarding.notNow')} onPrimary={handleNotificationPermission} onSecondary={() => updateState({ notificationPermission: 'skipped', currentStep: 'guide', completedSteps: [...new Set([...state.completedSteps, 'notifications'])] })}>
      <div className="onboarding-hero-icon"><Bell aria-hidden="true" size={48} /></div>
      <ul className="onboarding-benefits"><li>{t('onboarding.notifications.gameUpdates')}</li><li>{t('onboarding.notifications.changes')}</li><li>{t('onboarding.notifications.reminders')}</li></ul>
      <button className="onboarding-text-button" onClick={back} type="button">{t('onboarding.back')}</button>
    </OnboardingLayout>
  )

  if (step === 'guide') return (
    <OnboardingLayout {...common} title={t('onboarding.guide.title')} description={t('onboarding.guide.description')} primaryLabel={t('onboarding.continue')} secondaryLabel={t('onboarding.skip')} onPrimary={next} onSecondary={next}>
      <div className="onboarding-guide-grid">
        <article><Search aria-hidden="true" /><h2>{t('onboarding.guide.findTitle')}</h2><p>{t('onboarding.guide.findText')}</p></article>
        <article><PlusCircle aria-hidden="true" /><h2>{t('onboarding.guide.createTitle')}</h2><p>{t('onboarding.guide.createText')}</p></article>
        <article><Users aria-hidden="true" /><h2>{t('onboarding.guide.joinTitle')}</h2><p>{t('onboarding.guide.joinText')}</p></article>
      </div>
      <button className="onboarding-text-button" onClick={back} type="button">{t('onboarding.back')}</button>
    </OnboardingLayout>
  )

  return (
    <OnboardingLayout {...common} title={t('onboarding.ready.title')} description={t('onboarding.ready.description', { city: state.city })} primaryLabel={isBusy ? t('onboarding.ready.saving') : t('onboarding.ready.openMap')} secondaryLabel={t('onboarding.back')} onPrimary={handleFinish} onSecondary={back}>
      <div className="onboarding-hero-icon"><MapPin aria-hidden="true" size={48} /></div>
    </OnboardingLayout>
  )
}

export default OnboardingPage
