import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAdminUsers } from '../../api/admin'

function matchesSearch(user, normalizedSearch) {
  if (!normalizedSearch) {
    return true
  }

  return [user.id, user.username, user.name, user.email, user.phone_number, user.status].some((value) =>
    String(value || '').toLowerCase().includes(normalizedSearch),
  )
}

function AdminUsers() {
  const { i18n, t } = useTranslation()
  const [users, setUsers] = useState([])
  const [searchText, setSearchText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  function formatValue(value, fallback = t('admin.missing')) {
    return value || fallback
  }

  function formatDate(value, fallback = t('admin.missing')) {
    if (!value) {
      return fallback
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return fallback
    }

    return date.toLocaleString(locale)
  }

  function getAccountStatus(user) {
    return {
      className: user.status || 'active',
      label: user.status ? t(`admin.userStatuses.${user.status}`, user.status) : t('admin.active'),
    }
  }

  useEffect(() => {
    let isMounted = true

    async function loadUsers() {
      try {
        const loadedUsers = await getAdminUsers()
        if (isMounted) {
          setUsers(Array.isArray(loadedUsers) ? loadedUsers : [])
        }
      } catch {
        if (isMounted) {
          setError(t('admin.failedLoadUsers'))
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadUsers()

    return () => {
      isMounted = false
    }
  }, [t])

  const filteredUsers = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase()
    return users.filter((user) => matchesSearch(user, normalizedSearch))
  }, [searchText, users])

  return (
    <div className="admin-users">
      <header className="admin-users-header">
        <div>
          <h3>{t('admin.usersTitle')}</h3>
          <p>{t('admin.usersDescription')}</p>
        </div>
      </header>

      <label className="admin-users-search">
        <span>{t('admin.searchUsers')}</span>
        <input
          type="search"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder={t('admin.searchPlaceholder')}
        />
      </label>

      {isLoading ? <p className="admin-loading">{t('admin.loadingUsers')}</p> : null}
      {error ? <p className="admin-error">{error}</p> : null}

      {!isLoading && !error && users.length === 0 ? (
        <p className="admin-empty-state">{t('admin.noUsers')}</p>
      ) : null}

      {!isLoading && !error && users.length > 0 && filteredUsers.length === 0 ? (
        <p className="admin-empty-state">{t('admin.noUsersMatch')}</p>
      ) : null}

      {!isLoading && !error && filteredUsers.length > 0 ? (
        <div className="admin-table-wrap">
          <table className="admin-table admin-users-table">
            <thead>
              <tr>
                <th>{t('admin.userId')}</th>
                <th>{t('admin.username')}</th>
                <th>{t('admin.email')}</th>
                <th>{t('admin.phone')}</th>
                <th>{t('admin.createdDate')}</th>
                <th>{t('admin.status')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => {
                const accountStatus = getAccountStatus(user)

                return (
                  <tr key={user.id ?? `${user.email}-${user.name}`}>
                    <td>{formatValue(user.id)}</td>
                    <td>{formatValue(user.username)}</td>
                    <td>{formatValue(user.email)}</td>
                    <td>{formatValue(user.phone_number)}</td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>
                      <span className={`admin-user-status ${accountStatus.className}`}>
                        {accountStatus.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export default AdminUsers
