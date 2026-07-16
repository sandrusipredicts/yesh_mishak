import { useTranslation } from 'react-i18next'

function OnboardingProgress({ current, total, label }) {
  const { t } = useTranslation()
  return (
    <div className="onboarding-progress-wrap">
      <div
        className="onboarding-progress"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={current}
        aria-valuetext={t('onboarding.progress', { current, total, label })}
      >
        <span style={{ inlineSize: `${(current / total) * 100}%` }} />
      </div>
      <p className="onboarding-progress-label">
        {t('onboarding.progress', { current, total, label })}
      </p>
    </div>
  )
}

export default OnboardingProgress
