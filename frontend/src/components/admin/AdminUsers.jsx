import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { banUser, getAdminUsers, suspendUser, unbanUser, unsuspendUser } from '../../api/admin'

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
  const [actionLoading, setActionLoading] = useState(null)
  const [actionError, setActionError] = useState('')
  const [moderationModal, setModerationModal] = useState(null)
  const [moderationReason, setModerationReason] = useState('')
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

  const loadUsers = useCallback(async () => {
    try {
      setError('')
      const loadedUsers = await getAdminUsers()
      setUsers(Array.isArray(loadedUsers) ? loadedUsers : [])
    } catch {
      setError(t('admin.failedLoadUsers'))
    } finally {
      setIsLoading(false)
    }
  }, [t])

  useEffect(() => {
    let isMounted = true

    async function load() {
      const loadedUsers = await getAdminUsers().catch(() => null)
      if (isMounted) {
        if (loadedUsers) {
          setUsers(Array.isArray(loadedUsers) ? loadedUsers : [])
        } else {
          setError(t('admin.failedLoadUsers'))
        }
        setIsLoading(false)
      }
    }

    load()

    return () => {
      isMounted = false
    }
  }, [t])

  function requestModeration(userId, action) {
    if (action === 'ban' || action === 'suspend') {
      setModerationModal({ userId, action })
      setModerationReason('')
      return
    }

    executeModeration(userId, action, '')
  }

  async function executeModeration(userId, action, reason) {
    setModerationModal(null)
    setActionLoading(userId)
    setActionError('')

    try {
      if (action === 'ban') {
        await banUser(userId, reason)
      } else if (action === 'unban') {
        await unbanUser(userId)
      } else if (action === 'suspend') {
        await suspendUser(userId, reason)
      } else if (action === 'unsuspend') {
        await unsuspendUser(userId)
      }
      await loadUsers()
    } catch {
      setActionError(t('admin.moderationActionFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  function handleModerationConfirm() {
    const trimmed = moderationReason.trim()
    if (!trimmed) {
      setActionError(t('admin.moderationReasonRequired'))
      return
    }

    executeModeration(moderationModal.userId, moderationModal.action, trimmed)
  }

  function renderActions(user) {
    if (user.role === 'admin') {
      return null
    }

    const isUserLoading = actionLoading === user.id

    if (user.status === 'banned') {
      return (
        <button
          className="admin-action-button unban"
          disabled={isUserLoading}
          onClick={() => requestModeration(user.id, 'unban')}
        >
          {isUserLoading ? t('admin.moderationLoading') : t('admin.unban')}
        </button>
      )
    }

    if (user.status === 'suspended') {
      return (
        <button
          className="admin-action-button unsuspend"
          disabled={isUserLoading}
          onClick={() => requestModeration(user.id, 'unsuspend')}
        >
          {isUserLoading ? t('admin.moderationLoading') : t('admin.unsuspend')}
        </button>
      )
    }

    return (
      <>
        <button
          className="admin-action-button ban"
          disabled={isUserLoading}
          onClick={() => requestModeration(user.id, 'ban')}
        >
          {t('admin.ban')}
        </button>
        <button
          className="admin-action-button suspend"
          disabled={isUserLoading}
          onClick={() => requestModeration(user.id, 'suspend')}
        >
          {t('admin.suspend')}
        </button>
      </>
    )
  }

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
      {error ? (
        <div className="admin-error">
          <p>{error}</p>
          <button type="button" onClick={loadUsers}>{t('admin.retry')}</button>
        </div>
      ) : null}
      {actionError ? <p className="admin-error">{actionError}</p> : null}

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
                <th>{t('admin.actions')}</th>
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
                    <td className="admin-user-actions">{renderActions(user)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {moderationModal ? (
        <div className="confirm-modal-backdrop" role="presentation">
          <div className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="moderation-confirm-title">
            <h3 id="moderation-confirm-title">{t('admin.moderationConfirmTitle')}</h3>
            <p>{t('admin.moderationReasonPrompt')}</p>
            <label className="confirm-modal-label">
              <span>{t('admin.moderationReasonLabel')}</span>
              <textarea
                value={moderationReason}
                onChange={(event) => setModerationReason(event.target.value)}
                rows={3}
                autoFocus
              />
            </label>
            <div className="confirm-modal-actions">
              <button
                type="button"
                className="secondary-modal-button"
                onClick={() => setModerationModal(null)}
              >
                {t('admin.moderationCancelAction')}
              </button>
              <button
                type="button"
                className="danger-modal-button"
                onClick={handleModerationConfirm}
              >
                {t('admin.moderationConfirmAction')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default AdminUsers
