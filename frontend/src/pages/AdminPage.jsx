import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import AdminFields from '../components/admin/AdminFields'
import AdminGames from '../components/admin/AdminGames'
import AdminStats from '../components/admin/AdminStats'
import AdminUsers from '../components/admin/AdminUsers'
import LanguageSwitcher from '../components/LanguageSwitcher'

function AdminPage() {
  const { t } = useTranslation()
  const [activeSectionId, setActiveSectionId] = useState('stats')
  const adminSections = useMemo(() => [
    {
      id: 'stats',
      label: t('admin.stats'),
      title: t('admin.stats'),
      placeholder: t('admin.statsPlaceholder'),
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
  ], [t])
  const activeSection =
    adminSections.find((section) => section.id === activeSectionId) ?? adminSections[0]

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <h1>{t('admin.panel')}</h1>
          <p>{t('admin.description')}</p>
        </div>
        <div className="admin-header-actions">
          <LanguageSwitcher />
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
          {activeSection.id === 'fields' ? <AdminFields /> : null}
          {activeSection.id === 'games' ? <AdminGames /> : null}
          {activeSection.id === 'users' ? <AdminUsers /> : null}
          {activeSection.id !== 'stats' &&
          activeSection.id !== 'fields' &&
          activeSection.id !== 'games' &&
          activeSection.id !== 'users' ? (
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
