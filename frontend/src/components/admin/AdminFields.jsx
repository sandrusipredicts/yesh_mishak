import { useEffect, useState } from 'react'

import {
  approveField,
  getAdminFields,
  getPendingFields,
  rejectField,
  updateAdminFieldStatus,
} from '../../api/admin'

const FIELD_STATUSES = ['open', 'closed', 'renovation']

function formatValue(value, fallback = '—') {
  return value || fallback
}

function formatNotes(notes) {
  return notes || 'No notes'
}

function formatDate(value) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return date.toLocaleString()
}

function formatCoordinates(field) {
  if (field.lat === null || field.lat === undefined || field.lng === null || field.lng === undefined) {
    return '—'
  }

  const lat = Number(field.lat)
  const lng = Number(field.lng)
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    return '—'
  }

  return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
}

function AdminFields() {
  const [activeTab, setActiveTab] = useState('pending')
  const [pendingFields, setPendingFields] = useState([])
  const [allFields, setAllFields] = useState([])
  const [isPendingLoading, setIsPendingLoading] = useState(true)
  const [isAllFieldsLoading, setIsAllFieldsLoading] = useState(false)
  const [pendingError, setPendingError] = useState('')
  const [allFieldsError, setAllFieldsError] = useState('')
  const [actionError, setActionError] = useState('')
  const [workingFieldId, setWorkingFieldId] = useState('')

  async function loadAllFields() {
    setIsAllFieldsLoading(true)
    setAllFieldsError('')

    try {
      const fields = await getAdminFields()
      setAllFields(Array.isArray(fields) ? fields : [])
    } catch {
      setAllFieldsError('Failed to load fields.')
    } finally {
      setIsAllFieldsLoading(false)
    }
  }

  useEffect(() => {
    let isMounted = true

    async function loadInitialPendingFields() {
      try {
        const fields = await getPendingFields()
        if (isMounted) {
          setPendingFields(Array.isArray(fields) ? fields : [])
        }
      } catch {
        if (isMounted) {
          setPendingError('Failed to load fields.')
        }
      } finally {
        if (isMounted) {
          setIsPendingLoading(false)
        }
      }
    }

    loadInitialPendingFields()

    return () => {
      isMounted = false
    }
  }, [])

  function handleTabChange(tabId) {
    setActiveTab(tabId)

    if (tabId === 'pending') {
      return
    }

    if (allFields.length === 0) {
      loadAllFields()
    }
  }

  async function handleApprove(fieldId) {
    setWorkingFieldId(fieldId)
    setActionError('')

    try {
      const updatedField = await approveField(fieldId)
      setPendingFields((currentFields) => currentFields.filter((field) => field.id !== fieldId))
      setAllFields((currentFields) =>
        currentFields.map((field) => (field.id === fieldId ? updatedField : field)),
      )
    } catch {
      setActionError('Failed to approve field.')
    } finally {
      setWorkingFieldId('')
    }
  }

  async function handleReject(fieldId) {
    setWorkingFieldId(fieldId)
    setActionError('')

    try {
      const updatedField = await rejectField(fieldId)
      setPendingFields((currentFields) => currentFields.filter((field) => field.id !== fieldId))
      setAllFields((currentFields) =>
        currentFields.map((field) => (field.id === fieldId ? updatedField : field)),
      )
    } catch {
      setActionError('Failed to reject field.')
    } finally {
      setWorkingFieldId('')
    }
  }

  async function handleStatusChange(field, nextStatus) {
    if (field.status === nextStatus) {
      return
    }

    setWorkingFieldId(field.id)
    setActionError('')

    try {
      const response = await updateAdminFieldStatus(field.id, nextStatus)
      const updatedField = response.field ?? response
      setAllFields((currentFields) =>
        currentFields.map((currentField) =>
          currentField.id === field.id ? { ...currentField, ...updatedField } : currentField,
        ),
      )
    } catch {
      setActionError('Failed to update field.')
    } finally {
      setWorkingFieldId('')
    }
  }

  return (
    <div className="admin-fields">
      <div className="admin-tabs" role="tablist" aria-label="Field management tabs">
        <button
          className={`admin-tab-button ${activeTab === 'pending' ? 'active' : ''}`}
          type="button"
          role="tab"
          aria-selected={activeTab === 'pending'}
          onClick={() => handleTabChange('pending')}
        >
          Pending
        </button>
        <button
          className={`admin-tab-button ${activeTab === 'all' ? 'active' : ''}`}
          type="button"
          role="tab"
          aria-selected={activeTab === 'all'}
          onClick={() => handleTabChange('all')}
        >
          All Fields
        </button>
      </div>

      {actionError ? <p className="admin-error">{actionError}</p> : null}

      {activeTab === 'pending' ? (
        <section className="admin-fields-panel" aria-label="Pending fields">
          {isPendingLoading ? <p className="admin-loading">Loading pending fields...</p> : null}
          {pendingError ? <p className="admin-error">{pendingError}</p> : null}
          {!isPendingLoading && !pendingError && pendingFields.length === 0 ? (
            <p className="admin-empty-state">No pending fields.</p>
          ) : null}
          {!isPendingLoading && !pendingError && pendingFields.length > 0 ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>City</th>
                    <th>Location</th>
                    <th>Sport</th>
                    <th>Surface</th>
                    <th>Notes</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingFields.map((field) => (
                    <tr key={field.id}>
                      <td>{formatValue(field.name)}</td>
                      <td>{formatValue(field.city)}</td>
                      <td>{formatCoordinates(field)}</td>
                      <td>{formatValue(field.sport_type)}</td>
                      <td>{formatValue(field.surface_type)}</td>
                      <td>{formatNotes(field.notes)}</td>
                      <td>{formatDate(field.created_at)}</td>
                      <td>
                        <div className="admin-actions">
                          <button
                            type="button"
                            onClick={() => handleApprove(field.id)}
                            disabled={workingFieldId === field.id}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => handleReject(field.id)}
                            disabled={workingFieldId === field.id}
                          >
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="admin-fields-panel" aria-label="All fields">
          {isAllFieldsLoading ? <p className="admin-loading">Loading fields...</p> : null}
          {allFieldsError ? <p className="admin-error">{allFieldsError}</p> : null}
          {!isAllFieldsLoading && !allFieldsError && allFields.length === 0 ? (
            <p className="admin-empty-state">No fields found.</p>
          ) : null}
          {!isAllFieldsLoading && !allFieldsError && allFields.length > 0 ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>City</th>
                    <th>Status</th>
                    <th>Approval</th>
                    <th>Verified</th>
                    <th>Sport</th>
                    <th>Surface</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {allFields.map((field) => (
                    <tr key={field.id}>
                      <td>{formatValue(field.name)}</td>
                      <td>{formatValue(field.city)}</td>
                      <td>
                        <select
                          className="admin-status-select"
                          value={field.status ?? 'open'}
                          onChange={(event) => handleStatusChange(field, event.target.value)}
                          disabled={workingFieldId === field.id}
                        >
                          {FIELD_STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {status}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>{formatValue(field.approval_status)}</td>
                      <td>{field.verified ? 'Yes' : 'No'}</td>
                      <td>{formatValue(field.sport_type)}</td>
                      <td>{formatValue(field.surface_type)}</td>
                      <td>{formatDate(field.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      )}
    </div>
  )
}

export default AdminFields
