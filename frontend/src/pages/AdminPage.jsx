import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { updateAdminBusinessBranding } from '../api/businessBranding'
import useBusinessBranding from '../branding/useBusinessBranding'
import AdminEngagement from '../components/admin/AdminEngagement'
import AdminFields from '../components/admin/AdminFields'
import AdminFieldReports from '../components/admin/AdminFieldReports'
import AdminGames from '../components/admin/AdminGames'
import AdminMonitoring from '../components/admin/AdminMonitoring'
import AdminStats from '../components/admin/AdminStats'
import AdminUsers from '../components/admin/AdminUsers'

function AdminPage() {
  const { t } = useTranslation()
  const { businessName, applyBusinessName } = useBusinessBranding()
  const [activeSectionId, setActiveSectionId] = useState('stats')
  const [brandDraft, setBrandDraft] = useState('')
  const [hasBrandDraft, setHasBrandDraft] = useState(false)
  const [isSavingBrand, setIsSavingBrand] = useState(false)
  const [brandSaveMessage, setBrandSaveMessage] = useState('')
  const [brandSaveError, setBrandSaveError] = useState('')
  const adminSections = useMemo(() => [
    {
      id: 'stats',
      label: t('admin.stats'),
      title: t('admin.stats'),
      placeholder: t('admin.statsPlaceholder'),
    },
    {
      id: 'monitoring',
      label: t('admin.monitoring'),
      title: t('admin.monitoring'),
      placeholder: t('admin.monitoringPlaceholder'),
    },
    {
      id: 'engagement',
      label: t('admin.engagement'),
      title: t('admin.engagement'),
      placeholder: t('admin.engagementPlaceholder'),
    },
    {
      id: 'fields',
      label: t('admin.fields'),
      title: t('admin.fields'),
      placeholder: t('admin.fieldsPlaceholder'),
    },
    {
      id: 'games',
      label: t('admin.games'),
      title: t('admin.games'),
      placeholder: t('admin.gamesPlaceholder'),
    },
    {
      id: 'users',
      label: t('admin.users'),
      title: t('admin.users'),
      placeholder: t('admin.usersPlaceholder'),
    },
    {
      id: 'fieldReports',
      label: t('admin.fieldReports'),
      title: t('admin.fieldReports'),
      placeholder: t('admin.fieldReportsPlaceholder'),
    },
  ], [t])
  const activeSection =
    adminSections.find((section) => section.id === activeSectionId) ?? adminSections[0]
  const brandingInputValue = hasBrandDraft ? brandDraft : businessName
  const isBrandDirty = hasBrandDraft && brandDraft.trim() !== businessName

  async function handleSaveBranding(event) {
    event.preventDefault()
    const nextBusinessName = brandingInputValue.trim()
    if (!nextBusinessName || isSavingBrand) {
      return
    }

    setIsSavingBrand(true)
    setBrandSaveError('')
    setBrandSaveMessage('')

    try {
      const result = await updateAdminBusinessBranding(nextBusinessName)
      applyBusinessName(result.business_name)
      setBrandDraft(result.business_name)
      setHasBrandDraft(false)
      setBrandSaveMessage(t('admin.businessNameSaved'))
    } catch {
      setBrandSaveError(t('admin.businessNameSaveFailed'))
    } finally {
      setIsSavingBrand(false)
    }
  }

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <h1>{businessName}</h1>
          <p>{t('admin.description')}</p>
        </div>
        <div className="admin-header-actions">
          <form className="admin-branding-form" onSubmit={handleSaveBranding}>
            <label htmlFor="admin-business-name">{t('admin.businessNameLabel')}</label>
            <input
              id="admin-business-name"
              type="text"
              value={brandingInputValue}
              maxLength={120}
              onChange={(event) => {
                setBrandDraft(event.target.value)
                setHasBrandDraft(true)
                setBrandSaveError('')
                setBrandSaveMessage('')
              }}
            />
            <button type="submit" disabled={isSavingBrand || !brandingInputValue.trim() || !isBrandDirty}>
              {isSavingBrand ? t('admin.businessNameSaving') : t('admin.businessNameSave')}
            </button>
            {brandSaveMessage ? <p role="status">{brandSaveMessage}</p> : null}
            {brandSaveError ? <p role="alert">{brandSaveError}</p> : null}
          </form>
          <a className="admin-back-link" href="/">
            {t('admin.backToMap')}
          </a>
        </div>
      </header>

      <div className="admin-shell">
        <nav className="admin-sidebar" aria-label={t('admin.sections')}>
          {adminSections.map((section) => (
            <button
              className={`admin-sidebar-button ${
                section.id === activeSectionId ? 'active' : ''
              }`}
              type="button"
              key={section.id}
              onClick={() => setActiveSectionId(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>

        <section className="admin-content" aria-labelledby="admin-section-title">
          <h2 id="admin-section-title">{activeSection.title}</h2>
          {activeSection.id === 'stats' ? <AdminStats /> : null}
          {activeSection.id === 'monitoring' ? <AdminMonitoring /> : null}
          {activeSection.id === 'engagement' ? <AdminEngagement /> : null}
          {activeSection.id === 'fields' ? <AdminFields /> : null}
          {activeSection.id === 'games' ? <AdminGames /> : null}
          {activeSection.id === 'users' ? <AdminUsers /> : null}
          {activeSection.id === 'fieldReports' ? <AdminFieldReports /> : null}
          {activeSection.id !== 'stats' &&
          activeSection.id !== 'monitoring' &&
          activeSection.id !== 'engagement' &&
          activeSection.id !== 'fields' &&
          activeSection.id !== 'games' &&
          activeSection.id !== 'users' &&
          activeSection.id !== 'fieldReports' ? (
            <div className="admin-section-placeholder">
              <p>{activeSection.placeholder}</p>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  )
}

export default AdminPage
