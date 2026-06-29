import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  approveField,
  getAdminFields,
  getPendingFields,
  rejectField,
  updateAdminFieldStatus,
} from '../../api/admin'

const FIELD_STATUSES = ['open', 'closed', 'renovation']

function AdminFields() {
  const { i18n, t } = useTranslation()
  const [activeTab, setActiveTab] = useState('pending')
  const [pendingFields, setPendingFields] = useState([])
  const [allFields, setAllFields] = useState([])
  const [isPendingLoading, setIsPendingLoading] = useState(true)
  const [isAllFieldsLoading, setIsAllFieldsLoading] = useState(false)
  const [pendingError, setPendingError] = useState('')
  const [allFieldsError, setAllFieldsError] = useState('')
  const [actionError, setActionError] = useState('')
  const [workingFieldId, setWorkingFieldId] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  function formatValue(value, fallback = t('admin.missing')) {
    return value ? t(`values.${value}`, value) : fallback
  }

  function formatNotes(notes) {
    return notes || t('field.noNotes')
  }

  function formatDate(value) {
    if (!value) {
      return t('admin.missing')
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return t('admin.missing')
    }

    return date.toLocaleString(locale)
  }

  function formatCoordinates(field) {
    if (field.lat === null || field.lat === undefined || field.lng === null || field.lng === undefined) {
      return t('admin.missing')
    }

    const lat = Number(field.lat)
    const lng = Number(field.lng)
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      return t('admin.missing')
    }

    return `${lat.toFixed(4)}, ${lng.toFixed(4)}`
  }

  async function loadAllFields() {
    setIsAllFieldsLoading(true)
    setAllFieldsError('')

    try {
      const fields = await getAdminFields()
      setAllFields(Array.isArray(fields) ? fields : [])
    } catch {
      setAllFieldsError(t('admin.failedLoadFields'))
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
          setPendingError(t('admin.failedLoadFields'))
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
  }, [retryKey, t])

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
      setActionError(t('admin.failedApproveField'))
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
      setActionError(t('admin.failedRejectField'))
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
      setActionError(t('admin.failedUpdateField'))
    } finally {
      setWorkingFieldId('')
    }
  }

  return (
    <div className="admin-fields">
      <div className="admin-tabs" role="tablist" aria-label={t('admin.fieldTabs')}>
        <button
          className={`admin-tab-button ${activeTab === 'pending' ? 'active' : ''}`}
          type="button"
          role="tab"
          aria-selected={activeTab === 'pending'}
          onClick={() => handleTabChange('pending')}
        >
          {t('admin.pending')}
        </button>
        <button
          className={`admin-tab-button ${activeTab === 'all' ? 'active' : ''}`}
          type="button"
          role="tab"
          aria-selected={activeTab === 'all'}
          onClick={() => handleTabChange('all')}
        >
          {t('admin.allFields')}
        </button>
      </div>

      {actionError ? <p className="admin-error" role="alert">{actionError}</p> : null}

      {activeTab === 'pending' ? (
        <section className="admin-fields-panel" aria-label={t('admin.pendingFields')}>
          {isPendingLoading ? <p className="admin-loading">{t('admin.loadingPendingFields')}</p> : null}
          {pendingError ? (
            <div className="admin-error" role="alert">
              <p>{pendingError}</p>
              <button type="button" onClick={() => setRetryKey((k) => k + 1)}>{t('admin.retry')}</button>
            </div>
          ) : null}
          {!isPendingLoading && !pendingError && pendingFields.length === 0 ? (
            <p className="admin-empty-state">{t('admin.noPendingFields')}</p>
          ) : null}
          {!isPendingLoading && !pendingError && pendingFields.length > 0 ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>{t('admin.name')}</th>
                    <th>{t('admin.city')}</th>
                    <th>{t('admin.location')}</th>
                    <th>{t('admin.sport')}</th>
                    <th>{t('admin.surface')}</th>
                    <th>{t('admin.notes')}</th>
                    <th>{t('admin.created')}</th>
                    <th>{t('admin.actions')}</th>
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
                            {t('admin.approve')}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleReject(field.id)}
                            disabled={workingFieldId === field.id}
                          >
                            {t('admin.reject')}
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
        <section className="admin-fields-panel" aria-label={t('admin.allFieldsLabel')}>
          {isAllFieldsLoading ? <p className="admin-loading">{t('admin.loadingFields')}</p> : null}
          {allFieldsError ? (
            <div className="admin-error" role="alert">
              <p>{allFieldsError}</p>
              <button type="button" onClick={loadAllFields}>{t('admin.retry')}</button>
            </div>
          ) : null}
          {!isAllFieldsLoading && !allFieldsError && allFields.length === 0 ? (
            <p className="admin-empty-state">{t('admin.noFieldsFound')}</p>
          ) : null}
          {!isAllFieldsLoading && !allFieldsError && allFields.length > 0 ? (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>{t('admin.name')}</th>
                    <th>{t('admin.city')}</th>
                    <th>{t('admin.status')}</th>
                    <th>{t('admin.approval')}</th>
                    <th>{t('admin.verified')}</th>
                    <th>{t('admin.sport')}</th>
                    <th>{t('admin.surface')}</th>
                    <th>{t('admin.created')}</th>
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
                          aria-label={t('admin.fieldStatusLabel', { name: field.name || field.id })}
                        >
                          {FIELD_STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {t(`values.${status}`, status)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>{formatValue(field.approval_status)}</td>
                      <td>{field.verified ? t('admin.yes') : t('admin.no')}</td>
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
