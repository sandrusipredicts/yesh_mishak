import { useEffect, useMemo, useState } from 'react'

import { getAdminUsers } from '../../api/admin'

const ACTIVE_WINDOW_MS = 7 * 24 * 60 * 60 * 1000

function formatValue(value, fallback = '—') {
  return value || fallback
}

function formatDate(value, fallback = '—') {
  if (!value) {
    return fallback
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return fallback
  }

  return date.toLocaleString()
}

function getActivityStatus(lastActive) {
  if (!lastActive) {
    return {
      className: 'unknown',
      label: 'Unknown',
    }
  }

  const lastActiveDate = new Date(lastActive)
  if (Number.isNaN(lastActiveDate.getTime())) {
    return {
      className: 'unknown',
      label: 'Unknown',
    }
  }

  const isActive = Date.now() - lastActiveDate.getTime() <= ACTIVE_WINDOW_MS

  return {
    className: isActive ? 'active' : 'inactive',
    label: isActive ? 'Active' : 'Inactive',
  }
}

function matchesSearch(user, normalizedSearch) {
  if (!normalizedSearch) {
    return true
  }

  return [user.name, user.email, user.phone_number].some((value) =>
    String(value || '').toLowerCase().includes(normalizedSearch),
  )
}

function AdminUsers() {
  const [users, setUsers] = useState([])
  const [searchText, setSearchText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

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
          setError('Failed to load users.')
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
  }, [])

  const filteredUsers = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase()
    return users.filter((user) => matchesSearch(user, normalizedSearch))
  }, [searchText, users])

  return (
    <div className="admin-users">
      <header className="admin-users-header">
        <div>
          <h3>Users</h3>
          <p>Registered users and activity status.</p>
        </div>
      </header>

      <label className="admin-users-search">
        <span>Search users</span>
        <input
          type="search"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder="Search by name, email, or phone..."
        />
      </label>

      {isLoading ? <p className="admin-loading">Loading users...</p> : null}
      {error ? <p className="admin-error">{error}</p> : null}

      {!isLoading && !error && users.length === 0 ? (
        <p className="admin-empty-state">No users found.</p>
      ) : null}

      {!isLoading && !error && users.length > 0 && filteredUsers.length === 0 ? (
        <p className="admin-empty-state">No users match your search.</p>
      ) : null}

      {!isLoading && !error && filteredUsers.length > 0 ? (
        <div className="admin-table-wrap">
          <table className="admin-table admin-users-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Joined</th>
                <th>Last active</th>
                <th>Role</th>
                <th>Activity</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => {
                const activity = getActivityStatus(user.last_active)

                return (
                  <tr key={user.id ?? `${user.email}-${user.name}`}>
                    <td>{formatValue(user.name)}</td>
                    <td>{formatValue(user.email)}</td>
                    <td>{formatValue(user.phone_number)}</td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>{formatDate(user.last_active)}</td>
                    <td>{formatValue(user.role, 'user')}</td>
                    <td>
                      <span className={`admin-user-status ${activity.className}`}>
                        {activity.label}
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
