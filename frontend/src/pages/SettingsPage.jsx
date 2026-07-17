import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  getAccountMethods,
  linkGoogleAccount,
  removeAccountPassword,
  setAccountPassword,
  unlinkGoogleAccount,
} from '../api/accountLinking'
import { initNativeGoogleAuth, signInWithGoogleNative } from '../api/nativeGoogleAuth'
import { isNativeRuntime } from '../api/sessionStorage'
import Modal from '../components/Modal'
import CityAutocomplete from '../components/CityAutocomplete'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { israelCities } from '../data/israelCities'
import { resolveOnboardingState, saveOnboardingState, setAccountCity } from '../onboarding/onboardingStorage'
import { getPasswordValidationError } from '../utils/passwordValidation'

const GOOGLE_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'
let googleScriptPromise

function loadGoogleScript() {
  if (window.google?.accounts?.id) {
    return Promise.resolve()
  }

  if (googleScriptPromise) {
    return googleScriptPromise
  }

  const existingScript = document.querySelector(`script[src="${GOOGLE_SCRIPT_SRC}"]`)
  if (existingScript) {
    googleScriptPromise = new Promise((resolve, reject) => {
      existingScript.addEventListener('load', resolve, { once: true })
      existingScript.addEventListener('error', reject, { once: true })
    })
    return googleScriptPromise
  }

  googleScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GOOGLE_SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })

  return googleScriptPromise
}

function getAccountLinkingErrorKey(apiError) {
  const status = apiError?.response?.status
  const code = apiError?.response?.data?.code

  if (status === 429 || code === 'RATE_LIMITED') {
    return 'accountLinking.errorRateLimited'
  }

  const knownCodes = {
    ACCOUNT_METHOD_ALREADY_LINKED: 'accountLinking.errorAlreadyLinked',
    ACCOUNT_METHOD_NOT_LINKED: 'accountLinking.errorNotLinked',
    ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT: 'accountLinking.errorInUseByAnotherAccount',
    LAST_LOGIN_METHOD: 'accountLinking.errorLastMethod',
    REAUTHENTICATION_REQUIRED: 'accountLinking.errorReauthRequired',
    INVALID_GOOGLE_TOKEN: 'accountLinking.errorInvalidGoogleToken',
    PASSWORD_ALREADY_SET: 'accountLinking.errorPasswordAlreadySet',
    PASSWORD_NOT_SET: 'accountLinking.errorPasswordNotSet',
    VALIDATION_ERROR: 'accountLinking.errorValidation',
  }

  return knownCodes[code] || 'accountLinking.errorGeneric'
}

// Shared by every "prove you still control this Google account" flow (link,
// unlink reauth precursor via password instead, set-password, remove-password):
// mounted only while its owning section/modal is open so at most one GIS
// button/native call is live at a time (ISSUE-240 native path, LoginPage.jsx
// pattern mirrored here so Settings never swaps the *logged-in* session).
function GoogleCredentialButton({ disabled = false, label, onCredential, onError }) {
  const { t } = useTranslation()
  const buttonRef = useRef(null)
  const [nativeStatus, setNativeStatus] = useState('pending')
  const [isBusy, setIsBusy] = useState(false)
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    let isMounted = true

    async function initNative() {
      if (!googleClientId) {
        setNativeStatus('unavailable')
        return
      }
      try {
        await initNativeGoogleAuth(googleClientId)
        if (isMounted) setNativeStatus('ready')
      } catch {
        if (isMounted) setNativeStatus('unavailable')
      }
    }

    async function initWeb() {
      if (!googleClientId) {
        onError?.(t('accountLinking.googleMissingClient'))
        return
      }
      try {
        await loadGoogleScript()
        if (!isMounted || !window.google?.accounts?.id || !buttonRef.current) {
          return
        }

        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            if (!response.credential) {
              onError?.(t('accountLinking.googleNoCredential'))
              return
            }
            await onCredential(response.credential)
          },
        })

        const container = buttonRef.current
        container.replaceChildren()
        window.google.accounts.id.renderButton(container, {
          theme: 'outline',
          size: 'large',
          width: 280,
        })
      } catch {
        onError?.(t('accountLinking.googleLoadFailed'))
      }
    }

    if (isNativeRuntime()) {
      initNative()
    } else {
      initWeb()
    }

    return () => {
      isMounted = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleClientId])

  async function handleNativeClick() {
    if (isBusy) return
    setIsBusy(true)
    try {
      const idToken = await signInWithGoogleNative(googleClientId)
      await onCredential(idToken)
    } catch (nativeError) {
      if (nativeError?.code !== 'USER_CANCELLED') {
        onError?.(t('accountLinking.googleSignInFailed'))
      }
    } finally {
      setIsBusy(false)
    }
  }

  if (isNativeRuntime()) {
    if (nativeStatus === 'unavailable') {
      return <p className="google-native-unavailable">{t('auth.googleNativeUnavailable')}</p>
    }
    return (
      <button
        className="google-native-button"
        disabled={disabled || isBusy || nativeStatus !== 'ready'}
        onClick={handleNativeClick}
        type="button"
      >
        {label}
      </button>
    )
  }

  return (
    <div className="google-credential-action">
      <p className="google-credential-label">{label}</p>
      <div ref={buttonRef} className="google-login-button" aria-disabled={disabled} />
    </div>
  )
}

function UnlinkGoogleModal({ onClose, onUnlinked }) {
  const { t } = useTranslation()
  const [currentPassword, setCurrentPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const submittingRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (submittingRef.current) return
    submittingRef.current = true
    setIsSubmitting(true)
    setError('')

    try {
      const result = await unlinkGoogleAccount(currentPassword)
      onUnlinked(result.account_methods)
    } catch (apiError) {
      setError(t(getAccountLinkingErrorKey(apiError)))
    } finally {
      submittingRef.current = false
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen onClose={onClose} isConfirm ariaLabelledBy="unlink-google-title">
      <h3 id="unlink-google-title">{t('accountLinking.unlinkGoogleTitle')}</h3>
      <p>{t('accountLinking.unlinkGoogleDescription')}</p>
      <form onSubmit={handleSubmit}>
        <label className="confirm-modal-label">
          <span>{t('auth.password')}</span>
          <input
            autoComplete="current-password"
            autoFocus
            className="confirm-modal-input"
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
            type="password"
            value={currentPassword}
          />
        </label>
        {error ? <p className="modal-error" role="alert">{error}</p> : null}
        <div className="confirm-modal-actions">
          <button className="secondary-panel-button" disabled={isSubmitting} onClick={onClose} type="button">
            {t('accountLinking.cancel')}
          </button>
          <button className="danger-modal-button" disabled={isSubmitting || !currentPassword} type="submit">
            {isSubmitting ? t('accountLinking.unlinking') : t('accountLinking.unlinkGoogleConfirm')}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function SetPasswordModal({ onClose, onPasswordSet }) {
  const { t } = useTranslation()
  const [googleToken, setGoogleToken] = useState('')
  const [form, setForm] = useState({ password: '', password_confirm: '' })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const submittingRef = useRef(false)

  const passwordError = form.password ? getPasswordValidationError(form.password, t) : ''
  const passwordMismatch = form.password_confirm.length > 0 && form.password !== form.password_confirm

  async function handleSubmit(event) {
    event.preventDefault()
    if (submittingRef.current || passwordError || passwordMismatch) return
    submittingRef.current = true
    setIsSubmitting(true)
    setError('')

    try {
      const result = await setAccountPassword({
        googleToken,
        password: form.password,
        passwordConfirm: form.password_confirm,
      })
      onPasswordSet(result.account_methods)
    } catch (apiError) {
      setError(t(getAccountLinkingErrorKey(apiError)))
    } finally {
      submittingRef.current = false
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen onClose={onClose} className="account-linking-modal" ariaLabelledBy="set-password-title">
      <h2 id="set-password-title">{t('accountLinking.setPasswordTitle')}</h2>
      {!googleToken ? (
        <>
          <p>{t('accountLinking.reauthDescription')}</p>
          <GoogleCredentialButton
            label={t('accountLinking.reauthWithGoogle')}
            onCredential={async (idToken) => setGoogleToken(idToken)}
            onError={setError}
          />
          {error ? <p className="modal-error" role="alert">{error}</p> : null}
        </>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>{t('auth.newPassword')}</span>
            <input
              autoComplete="new-password"
              autoFocus
              onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
              required
              type="password"
              value={form.password}
            />
          </label>
          <span className="form-hint">{t('auth.passwordHint')}</span>
          {form.password && passwordError ? (
            <span className="form-field-error" role="alert">{passwordError}</span>
          ) : null}
          <label>
            <span>{t('auth.confirmPassword')}</span>
            <input
              autoComplete="new-password"
              onChange={(event) => setForm((current) => ({ ...current, password_confirm: event.target.value }))}
              required
              type="password"
              value={form.password_confirm}
            />
          </label>
          {passwordMismatch ? (
            <span className="form-field-error" role="alert">{t('auth.passwordMismatch')}</span>
          ) : null}
          {error ? <p className="modal-error" role="alert">{error}</p> : null}
          <div className="confirm-modal-actions">
            <button className="secondary-panel-button" disabled={isSubmitting} onClick={onClose} type="button">
              {t('accountLinking.cancel')}
            </button>
            <button
              className="primary-panel-button"
              disabled={isSubmitting || Boolean(passwordError) || passwordMismatch || !form.password}
              type="submit"
            >
              {isSubmitting ? t('accountLinking.settingPassword') : t('accountLinking.setPasswordConfirm')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

function RemovePasswordModal({ onClose, onPasswordRemoved }) {
  const { t } = useTranslation()
  const [googleToken, setGoogleToken] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const submittingRef = useRef(false)

  async function handleConfirm() {
    if (submittingRef.current) return
    submittingRef.current = true
    setIsSubmitting(true)
    setError('')

    try {
      const result = await removeAccountPassword(googleToken)
      onPasswordRemoved(result.account_methods)
    } catch (apiError) {
      setError(t(getAccountLinkingErrorKey(apiError)))
    } finally {
      submittingRef.current = false
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen onClose={onClose} isConfirm ariaLabelledBy="remove-password-title">
      <h3 id="remove-password-title">{t('accountLinking.removePasswordTitle')}</h3>
      {!googleToken ? (
        <>
          <p>{t('accountLinking.reauthDescription')}</p>
          <GoogleCredentialButton
            label={t('accountLinking.reauthWithGoogle')}
            onCredential={async (idToken) => setGoogleToken(idToken)}
            onError={setError}
          />
        </>
      ) : (
        <p>{t('accountLinking.removePasswordDescription')}</p>
      )}
      {error ? <p className="modal-error" role="alert">{error}</p> : null}
      <div className="confirm-modal-actions">
        <button className="secondary-panel-button" disabled={isSubmitting} onClick={onClose} type="button">
          {t('accountLinking.cancel')}
        </button>
        {googleToken ? (
          <button className="danger-modal-button" disabled={isSubmitting} onClick={handleConfirm} type="button">
            {isSubmitting ? t('accountLinking.removingPassword') : t('accountLinking.removePasswordConfirm')}
          </button>
        ) : null}
      </div>
    </Modal>
  )
}

function SettingsPage({ onBack, userId }) {
  const { i18n, t } = useTranslation()
  const isRtl = i18n.dir() === 'rtl'
  const BackArrow = isRtl ? ArrowRight : ArrowLeft

  const [methods, setMethods] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [linkError, setLinkError] = useState('')
  const [isLinkingGoogle, setIsLinkingGoogle] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [activeModal, setActiveModal] = useState(null)
  const [startingCity, setStartingCity] = useState(() => resolveOnboardingState().state.city)
  const [preferenceMessage, setPreferenceMessage] = useState('')
  const linkingRef = useRef(false)

  // Retry-button path: setIsLoading(true) runs from a click handler, not an
  // effect, so it is safe to call synchronously here.
  const loadMethods = useCallback(async () => {
    setIsLoading(true)
    setLoadError('')
    try {
      const data = await getAccountMethods()
      setMethods(data)
    } catch {
      setLoadError(t('accountLinking.loadFailed'))
    } finally {
      setIsLoading(false)
    }
  }, [t])

  // Initial mount fetch: isLoading already starts true, so state updates are
  // deferred to the promise callbacks instead of being set synchronously
  // inside the effect body.
  useEffect(() => {
    let isMounted = true

    getAccountMethods()
      .then((data) => {
        if (isMounted) {
          setMethods(data)
          setLoadError('')
        }
      })
      .catch(() => {
        if (isMounted) {
          setLoadError(t('accountLinking.loadFailed'))
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [t])

  const handleLinkGoogleCredential = useCallback(
    async (idToken) => {
      if (linkingRef.current) return
      linkingRef.current = true
      setIsLinkingGoogle(true)
      setLinkError('')
      setStatusMessage('')

      try {
        const result = await linkGoogleAccount(idToken)
        setMethods(result.account_methods)
        setStatusMessage(t('accountLinking.googleLinked'))
      } catch (apiError) {
        setLinkError(t(getAccountLinkingErrorKey(apiError)))
      } finally {
        linkingRef.current = false
        setIsLinkingGoogle(false)
      }
    },
    [t],
  )

  function closeModal() {
    setActiveModal(null)
  }

  function handleStartingCityChange(city) {
    setStartingCity(city)
    setPreferenceMessage('')
    if (!israelCities.includes(city)) return
    const current = resolveOnboardingState().state
    const result = saveOnboardingState({ ...current, city })
    setAccountCity(userId, city)
    setPreferenceMessage(result.ok ? t('accountLinking.preferencesSaved') : t('accountLinking.preferencesSaveFailed'))
  }

  function handleUnlinked(updatedMethods) {
    setMethods(updatedMethods)
    setStatusMessage(t('accountLinking.googleUnlinked'))
    setActiveModal(null)
  }

  function handlePasswordSet(updatedMethods) {
    setMethods(updatedMethods)
    setStatusMessage(t('accountLinking.passwordSet'))
    setActiveModal(null)
  }

  function handlePasswordRemoved(updatedMethods) {
    setMethods(updatedMethods)
    setStatusMessage(t('accountLinking.passwordRemoved'))
    setActiveModal(null)
  }

  return (
    <div className="my-games-page settings-page">
      <header className="my-games-header">
        <button type="button" className="my-games-back-button" onClick={onBack}>
          <BackArrow size={20} />
          {t('accountLinking.back')}
        </button>
        <h2 className="my-games-title">{t('accountLinking.title')}</h2>
      </header>

      <section className="settings-section settings-preferences" aria-labelledby="app-preferences-title">
        <h3 id="app-preferences-title">{t('accountLinking.appPreferences')}</h3>
        <div className="language-settings-section">
          <div><strong>{t('language.label')}</strong></div>
          <LanguageSwitcher />
        </div>
        <label htmlFor="settings-starting-city">{t('accountLinking.startingCity')}</label>
        <CityAutocomplete
          id="settings-starting-city"
          value={startingCity}
          onChange={handleStartingCityChange}
          cities={israelCities}
          placeholder={t('onboarding.cityPlaceholder')}
        />
        {preferenceMessage ? <p role="status">{preferenceMessage}</p> : null}
      </section>

      {isLoading ? <p className="my-games-loading">{t('accountLinking.loading')}</p> : null}

      {!isLoading && loadError ? (
        <div className="my-games-error" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={loadMethods}>{t('admin.retry')}</button>
        </div>
      ) : null}

      {!isLoading && !loadError && methods ? (
        <div className="account-linking-sections">
          {statusMessage ? <p className="modal-success" role="status">{statusMessage}</p> : null}

          <section className="settings-section account-method-card" aria-labelledby="method-email-title">
            <div className="account-method-header">
              <h3 id="method-email-title">{t('accountLinking.emailPassword')}</h3>
              <span
                className={`account-method-status ${methods.email.linked ? 'is-linked' : 'is-unlinked'}`}
              >
                {methods.email.linked ? t('accountLinking.connected') : t('accountLinking.notConfigured')}
              </span>
            </div>
            {methods.email.linked && methods.email.address ? (
              <p className="account-method-detail">{methods.email.address}</p>
            ) : null}
            {methods.email.linked && !methods.email.verified ? (
              <p className="account-method-warning">{t('accountLinking.emailUnverified')}</p>
            ) : null}
            <div className="account-method-actions">
              {!methods.email.linked ? (
                <button
                  className="primary-panel-button"
                  type="button"
                  onClick={() => setActiveModal('set-password')}
                >
                  {t('accountLinking.setPassword')}
                </button>
              ) : (
                <>
                  <button
                    className="secondary-panel-button"
                    disabled={!methods.email.can_unlink}
                    type="button"
                    onClick={() => setActiveModal('remove-password')}
                  >
                    {t('accountLinking.removePassword')}
                  </button>
                  {!methods.email.can_unlink ? (
                    <p className="account-method-reason">{t('accountLinking.cannotRemovePasswordReason')}</p>
                  ) : null}
                </>
              )}
            </div>
          </section>

          <section className="settings-section account-method-card" aria-labelledby="method-google-title">
            <div className="account-method-header">
              <h3 id="method-google-title">{t('accountLinking.google')}</h3>
              <span
                className={`account-method-status ${methods.google.linked ? 'is-linked' : 'is-unlinked'}`}
              >
                {methods.google.linked ? t('accountLinking.connected') : t('accountLinking.notConnected')}
              </span>
            </div>
            {methods.google.linked && methods.google.email ? (
              <p className="account-method-detail">{methods.google.email}</p>
            ) : null}
            <div className="account-method-actions">
              {!methods.google.linked ? (
                <GoogleCredentialButton
                  disabled={isLinkingGoogle}
                  label={t('accountLinking.linkGoogle')}
                  onCredential={handleLinkGoogleCredential}
                  onError={setLinkError}
                />
              ) : (
                <>
                  <button
                    className="secondary-panel-button"
                    disabled={!methods.google.can_unlink}
                    type="button"
                    onClick={() => setActiveModal('unlink-google')}
                  >
                    {t('accountLinking.unlinkGoogle')}
                  </button>
                  {!methods.google.can_unlink ? (
                    <p className="account-method-reason">{t('accountLinking.cannotUnlinkGoogleReason')}</p>
                  ) : null}
                </>
              )}
            </div>
            {linkError ? <p className="modal-error" role="alert">{linkError}</p> : null}
          </section>
        </div>
      ) : null}

      {activeModal === 'unlink-google' ? (
        <UnlinkGoogleModal onClose={closeModal} onUnlinked={handleUnlinked} />
      ) : null}
      {activeModal === 'set-password' ? (
        <SetPasswordModal onClose={closeModal} onPasswordSet={handlePasswordSet} />
      ) : null}
      {activeModal === 'remove-password' ? (
        <RemovePasswordModal onClose={closeModal} onPasswordRemoved={handlePasswordRemoved} />
      ) : null}
    </div>
  )
}

export default SettingsPage
