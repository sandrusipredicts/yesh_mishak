import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { startPhoneVerification, verifyPhoneOtp } from '../api/auth'

function apiMessage(error, fallback) {
  const detail = error?.response?.data
  if (detail?.code === 'RATE_LIMITED') {
    return fallback.rateLimited
  }
  if (detail?.code === 'PHONE_INVALID') {
    return fallback.invalidPhone
  }
  if (detail?.code === 'PHONE_OTP_INVALID') {
    return fallback.invalidOtp
  }
  if (detail?.code === 'PHONE_PROVIDER_UNAVAILABLE') {
    return fallback.providerUnavailable
  }
  if (
    detail?.code === 'PHONE_VERIFICATION_UNAVAILABLE' ||
    detail?.code === 'PHONE_CHANGE_NOT_SUPPORTED'
  ) {
    return fallback.conflict
  }
  if (detail?.code === 'PHONE_ALREADY_VERIFIED') {
    return fallback.alreadyVerified
  }
  return fallback.generic
}

function PhoneVerificationModal({ onClose, onVerified }) {
  const { t } = useTranslation()
  const [phoneNumber, setPhoneNumber] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState('phone')
  const [cooldown, setCooldown] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    if (cooldown <= 0) {
      return undefined
    }
    const timer = window.setInterval(() => {
      setCooldown((current) => Math.max(0, current - 1))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [cooldown])

  const fallbacks = {
    invalidPhone: t('phoneVerification.invalidPhone'),
    invalidOtp: t('phoneVerification.invalidOtp'),
    providerUnavailable: t('phoneVerification.providerUnavailable'),
    rateLimited: t('phoneVerification.rateLimited'),
    conflict: t('phoneVerification.conflict'),
    alreadyVerified: t('phoneVerification.alreadyVerified'),
    generic: t('phoneVerification.genericError'),
  }

  async function handleStart(event) {
    event.preventDefault()
    setIsLoading(true)
    setError('')
    setStatus('')

    try {
      const result = await startPhoneVerification({ phone_number: phoneNumber })
      setStep('otp')
      setCooldown(result.cooldown_seconds || 60)
      setStatus(t('phoneVerification.codeSent'))
    } catch (startError) {
      setError(apiMessage(startError, fallbacks))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleResend() {
    setIsLoading(true)
    setError('')
    setStatus('')

    try {
      const result = await startPhoneVerification({ phone_number: phoneNumber })
      setCooldown(result.cooldown_seconds || 60)
      setStatus(t('phoneVerification.codeSent'))
    } catch (resendError) {
      setError(apiMessage(resendError, fallbacks))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleVerify(event) {
    event.preventDefault()
    setIsLoading(true)
    setError('')
    setStatus('')

    try {
      const result = await verifyPhoneOtp({ phone_number: phoneNumber, otp })
      setStatus(t('phoneVerification.success'))
      setOtp('')
      onVerified?.(result.phone_number)
    } catch (verifyError) {
      setError(apiMessage(verifyError, fallbacks))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="phone-verification-backdrop" role="presentation">
      <section
        className="phone-verification-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="phone-verification-title"
      >
        <header>
          <h2 id="phone-verification-title">{t('phoneVerification.title')}</h2>
          <button type="button" className="modal-icon-button" onClick={onClose} aria-label={t('field.close')}>
            ×
          </button>
        </header>

        {step === 'phone' ? (
          <form className="phone-verification-form" onSubmit={handleStart}>
            <label>
              <span>{t('phoneVerification.phoneLabel')}</span>
              <input
                autoComplete="tel"
                inputMode="tel"
                name="phone_number"
                onChange={(event) => setPhoneNumber(event.target.value)}
                required
                type="tel"
                value={phoneNumber}
              />
            </label>
            <button className="auth-submit" disabled={isLoading} type="submit">
              {isLoading ? t('phoneVerification.sending') : t('phoneVerification.sendCode')}
            </button>
          </form>
        ) : (
          <form className="phone-verification-form" onSubmit={handleVerify}>
            <label>
              <span>{t('phoneVerification.codeLabel')}</span>
              <input
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={10}
                name="otp"
                onChange={(event) => setOtp(event.target.value)}
                pattern="[0-9]*"
                required
                type="text"
                value={otp}
              />
            </label>
            <button className="auth-submit" disabled={isLoading} type="submit">
              {isLoading ? t('phoneVerification.verifying') : t('phoneVerification.verify')}
            </button>
            <button
              className="auth-link-button"
              disabled={isLoading || cooldown > 0}
              onClick={handleResend}
              type="button"
            >
              {cooldown > 0
                ? t('phoneVerification.resendIn', { count: cooldown })
                : t('phoneVerification.resend')}
            </button>
          </form>
        )}

        {error ? <p className="login-error" role="alert">{error}</p> : null}
        {status ? <p className="login-info" role="status">{status}</p> : null}
      </section>
    </div>
  )
}

export default PhoneVerificationModal
