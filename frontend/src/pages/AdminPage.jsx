import { useState } from 'react'

const ADMIN_SECTIONS = [
  {
    id: 'stats',
    label: 'Stats',
    title: 'Stats',
    placeholder: 'Stats dashboard will appear here',
  },
  {
    id: 'fields',
    label: 'Fields',
    title: 'Fields',
    placeholder: 'Fields management will appear here',
  },
  {
    id: 'games',
    label: 'Games',
    title: 'Games',
    placeholder: 'Games management will appear here',
  },
  {
    id: 'users',
    label: 'Users',
    title: 'Users',
    placeholder: 'Users list will appear here',
  },
]

function AdminPage() {
  const [activeSectionId, setActiveSectionId] = useState('stats')
  const activeSection =
    ADMIN_SECTIONS.find((section) => section.id === activeSectionId) ?? ADMIN_SECTIONS[0]

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <h1>Admin Panel</h1>
          <p>Manage fields, games, users and system stats.</p>
        </div>
        <a className="admin-back-link" href="/">
          Back to map
        </a>
      </header>

      <div className="admin-shell">
        <nav className="admin-sidebar" aria-label="Admin sections">
          {ADMIN_SECTIONS.map((section) => (
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
          <div className="admin-section-placeholder">
            <p>{activeSection.placeholder}</p>
          </div>
        </section>
      </div>
    </main>
  )
}

export default AdminPage
