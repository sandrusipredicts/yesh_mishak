import { useEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import OnboardingProgress from './OnboardingProgress'

function OnboardingLayout({
  step,
  total,
  title,
  description,
  children,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
  isBusy = false,
  primaryDisabled = false,
  error = '',
}) {
  const { i18n } = useTranslation()
  const headingRef = useRef(null)
  const isRtl = i18n.dir() === 'rtl'
  const BackIcon = isRtl ? ArrowRight : ArrowLeft

  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  return (
    <main className="onboarding-page" aria-busy={isBusy}>
      <section className="onboarding-panel onboarding-shell" aria-labelledby="onboarding-title">
        <OnboardingProgress current={step} total={total} label={title} />
        <div className="onboarding-step-content">
          <h1 id="onboarding-title" ref={headingRef} tabIndex={-1}>{title}</h1>
          {description ? <p className="onboarding-description">{description}</p> : null}
          {children}
        </div>
        {error ? <p className="onboarding-error" role="alert">{error}</p> : null}
        <div className="onboarding-navigation">
          {secondaryLabel ? (
            <button className="secondary-panel-button" disabled={isBusy} onClick={onSecondary} type="button">
              <BackIcon aria-hidden="true" size={18} />
              {secondaryLabel}
            </button>
          ) : <span />}
          <button
            className="primary-panel-button"
            disabled={isBusy || primaryDisabled}
            onClick={onPrimary}
            type="button"
          >
            {primaryLabel}
          </button>
        </div>
      </section>
    </main>
  )
}

export default OnboardingLayout
