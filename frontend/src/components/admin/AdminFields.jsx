import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  approveField,
  deleteAdminField,
  getAdminFields,
  getPendingFields,
  rejectField,
  updateAdminFieldStatus,
} from '../../api/admin'
import { getApiErrorMessage } from '../../api/errors'
import EditFieldModal from '../EditFieldModal'
import Modal from '../Modal'

const FIELD_STATUSES = ['open', 'closed', 'renovation']
const FIELD_REMOVAL_REASONS = [
  'field_does_not_exist',
  'duplicate_field',
  'private_field',
  'school_property',
  'wrong_location',
  'invalid_field',
  'safety_issue',
  'other',
]
const NOTE_MAX_LENGTH = 500

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
  const [editingField, setEditingField] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteReason, setDeleteReason] = useState('')
  const [deleteNote, setDeleteNote] = useState('')
  const [deleteFormError, setDeleteFormError] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
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

  function handleFieldSaved(updatedField) {
    setAllFields((currentFields) =>
      currentFields.map((currentField) =>
        currentField.id === updatedField.id ? { ...currentField, ...updatedField } : currentField,
      ),
    )
    setPendingFields((currentFields) =>
      currentFields.map((currentField) =>
        currentField.id === updatedField.id ? { ...currentField, ...updatedField } : currentField,
      ),
    )
  }

  function openDeleteConfirm(field) {
    setActionError('')
    setActionMessage('')
    setDeleteFormError('')
    setDeleteReason('')
    setDeleteNote('')
    setDeleteTarget(field)
  }

  function closeDeleteConfirm() {
    if (isDeleting) {
      return
    }

    setDeleteTarget(null)
    setDeleteReason('')
    setDeleteNote('')
    setDeleteFormError('')
  }

  function removeFieldFromLists(fieldId) {
    setAllFields((currentFields) => currentFields.filter((field) => field.id !== fieldId))
    setPendingFields((currentFields) => currentFields.filter((field) => field.id !== fieldId))
  }

  async function handleDeleteConfirm() {
    if (isDeleting || !deleteTarget) {
      return
    }

    if (!deleteReason) {
      setDeleteFormError(t('admin.deleteFieldReasonRequired'))
      return
    }

    const trimmedNote = deleteNote.trim()
    if (trimmedNote.length > NOTE_MAX_LENGTH) {
      setDeleteFormError(t('admin.deleteFieldNoteTooLong'))
      return
    }

    const fieldId = deleteTarget.id
    setIsDeleting(true)
    setDeleteFormError('')

    try {
      await deleteAdminField(fieldId, { reason: deleteReason, note: trimmedNote || undefined })
      removeFieldFromLists(fieldId)
      setActionMessage(t('admin.deleteFieldSuccess'))
      setDeleteTarget(null)
      setDeleteReason('')
      setDeleteNote('')
    } catch (submitError) {
      const statusCode = submitError?.response?.status

      if (statusCode === 404 || statusCode === 409) {
        // The backend confirms the field is already gone or already
        // removed — trust that over our stale local copy.
        removeFieldFromLists(fieldId)
        setDeleteTarget(null)
        setActionError(
          statusCode === 409 ? t('admin.deleteFieldAlreadyRemoved') : t('admin.deleteFieldNotFound'),
        )
      } else if (statusCode === 403) {
        setDeleteFormError(t('admin.deleteFieldForbidden'))
      } else {
        setDeleteFormError(getApiErrorMessage(submitError, t('admin.failedDeleteField')))
      }
    } finally {
      setIsDeleting(false)
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
      {actionMessage ? <p className="admin-success" role="status">{actionMessage}</p> : null}

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
                    <th>{t('admin.photo')}</th>
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
                      <td>
                        {field.photo_url ? (
                          <a
                            className="admin-field-photo-link"
                            href={field.photo_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img
                              src={field.photo_url}
                              alt={t('admin.fieldPhotoAlt', { name: field.name || field.id })}
                            />
                          </a>
                        ) : (
                          t('admin.missing')
                        )}
                      </td>
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
                    <th>{t('admin.actions')}</th>
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
                      <td>
                        <div className="admin-actions">
                          <button
                            type="button"
                            onClick={() => setEditingField(field)}
                            aria-label={t('admin.editFieldLabel', { name: field.name || field.id })}
                          >
                            {t('admin.edit')}
                          </button>
                          <button
                            type="button"
                            onClick={() => openDeleteConfirm(field)}
                            aria-label={t('admin.deleteFieldLabel', { name: field.name || field.id })}
                          >
                            {t('admin.deleteField')}
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
      )}

      {editingField ? (
        <EditFieldModal
          field={editingField}
          onClose={() => setEditingField(null)}
          onSaved={handleFieldSaved}
        />
      ) : null}

      <Modal
        isOpen={!!deleteTarget}
        onClose={closeDeleteConfirm}
        isConfirm={true}
        ariaLabelledBy="admin-delete-field-title"
      >
        <h3 id="admin-delete-field-title">{t('admin.deleteFieldConfirmTitle')}</h3>
        <p>
          {t('admin.deleteFieldConfirmDescription', {
            name: deleteTarget?.name || deleteTarget?.id,
          })}
        </p>

        <label htmlFor="delete-field-reason">
          {t('admin.deleteFieldReasonLabel')}
          <select
            id="delete-field-reason"
            value={deleteReason}
            onChange={(event) => setDeleteReason(event.target.value)}
            disabled={isDeleting}
          >
            <option value="">{t('admin.deleteFieldReasonPlaceholder')}</option>
            {FIELD_REMOVAL_REASONS.map((reason) => (
              <option key={reason} value={reason}>
                {t(`admin.deleteReason.${reason}`)}
              </option>
            ))}
          </select>
        </label>

        <label htmlFor="delete-field-note">
          {t('admin.deleteFieldNoteLabel')}
          <textarea
            id="delete-field-note"
            value={deleteNote}
            onChange={(event) => setDeleteNote(event.target.value)}
            rows="2"
            maxLength={NOTE_MAX_LENGTH}
            disabled={isDeleting}
          />
        </label>

        {deleteFormError ? <p className="modal-error" role="alert">{deleteFormError}</p> : null}

        <div className="confirm-modal-actions">
          <button
            type="button"
            className="secondary-modal-button"
            onClick={closeDeleteConfirm}
            disabled={isDeleting}
          >
            {t('admin.moderationCancelAction')}
          </button>
          <button
            type="button"
            className="danger-modal-button"
            onClick={handleDeleteConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? t('admin.deleteFieldDeleting') : t('admin.deleteFieldConfirmAction')}
          </button>
        </div>
      </Modal>
    </div>
  )
}

export default AdminFields
