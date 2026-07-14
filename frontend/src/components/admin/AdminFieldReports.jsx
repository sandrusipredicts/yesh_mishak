import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAdminFieldReports, updateAdminFieldReportStatus } from '../../api/admin'
import { getApiErrorMessage } from '../../api/errors'
import Modal from '../Modal'

const STATUS_FILTERS = ['all', 'open', 'in_review', 'resolved', 'rejected']
const REVIEW_STATUSES = ['open', 'in_review', 'resolved', 'rejected']

const CATEGORY_LABEL_KEYS = {
  wrong_location: 'fieldReport.categories.wrongLocation',
  field_does_not_exist: 'fieldReport.categories.fieldDoesNotExist',
  field_closed: 'fieldReport.categories.fieldClosed',
  under_renovation: 'fieldReport.categories.underRenovation',
  private_field: 'fieldReport.categories.privateField',
  duplicate_field: 'fieldReport.categories.duplicateField',
  wrong_information: 'fieldReport.categories.wrongInformation',
  other: 'fieldReport.categories.other',
}

const ADMIN_NOTE_MAX = 1000

function AdminFieldReports() {
  const { i18n, t } = useTranslation()
  const [reports, setReports] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  const [managingReport, setManagingReport] = useState(null)
  const [editStatus, setEditStatus] = useState('open')
  const [editNote, setEditNote] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState('')

  useEffect(() => {
    let isMounted = true

    async function loadReports() {
      try {
        const loadedReports = await getAdminFieldReports()
        if (isMounted) {
          setReports(Array.isArray(loadedReports) ? loadedReports : [])
        }
      } catch {
        if (isMounted) {
          setError(t('admin.failedLoadFieldReports'))
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadReports()

    return () => {
      isMounted = false
    }
  }, [retryKey, t])

  const visibleReports = useMemo(() => {
    return reports
      .filter((report) => statusFilter === 'all' || report.status === statusFilter)
      .sort((left, right) => {
        const leftDate = new Date(left.created_at).getTime()
        const rightDate = new Date(right.created_at).getTime()
        return (Number.isNaN(rightDate) ? 0 : rightDate) - (Number.isNaN(leftDate) ? 0 : leftDate)
      })
  }, [reports, statusFilter])

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

  function formatValue(value, fallback = t('admin.missing')) {
    return value || fallback
  }

  function formatCategory(category) {
    return t(CATEGORY_LABEL_KEYS[category] ?? category, category)
  }

  function formatReporter(report) {
    if (report.reporter_name && report.reporter_email) {
      return `${report.reporter_name} (${report.reporter_email})`
    }

    return report.reporter_name || report.reporter_email || report.user_id || t('admin.missing')
  }

  function openManage(report) {
    setManagingReport(report)
    setEditStatus(report.status || 'open')
    setEditNote(report.admin_note || '')
    setSaveError('')
    setSaveSuccess('')
  }

  function closeManage() {
    setManagingReport(null)
    setSaveError('')
    setSaveSuccess('')
  }

  async function handleSave() {
    if (!managingReport || isSaving) return

    setIsSaving(true)
    setSaveError('')
    setSaveSuccess('')

    const trimmedNote = editNote.trim()
    const payload = { status: editStatus }

    if (trimmedNote) {
      payload.admin_note = trimmedNote
    } else if (managingReport.admin_note) {
      payload.admin_note = null
    } else if (editNote !== '' && !trimmedNote) {
      payload.admin_note = null
    }

    try {
      const result = await updateAdminFieldReportStatus(managingReport.id, payload)
      const updatedReport = result.report || result

      setReports((prev) =>
        prev.map((r) =>
          r.id === managingReport.id
            ? { ...r, ...updatedReport }
            : r,
        ),
      )

      setSaveSuccess(t('admin.fieldReportManage.saveSuccess'))

      setTimeout(() => {
        closeManage()
      }, 1200)
    } catch (err) {
      setSaveError(getApiErrorMessage(err, t('admin.fieldReportManage.saveError')))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="admin-field-reports">
      <header className="admin-field-reports-header">
        <div>
          <h3>{t('admin.fieldReportsTitle')}</h3>
          <p>{t('admin.fieldReportsDescription')}</p>
        </div>
      </header>

      <div className="admin-tabs" role="tablist" aria-label={t('admin.fieldReportsFilters')}>
        {STATUS_FILTERS.map((status) => (
          <button
            className={`admin-tab-button ${statusFilter === status ? 'active' : ''}`}
            type="button"
            role="tab"
            aria-selected={statusFilter === status}
            key={status}
            onClick={() => setStatusFilter(status)}
          >
            {t(`admin.fieldReportFilters.${status}`)}
          </button>
        ))}
      </div>

      {isLoading ? <p className="admin-loading">{t('admin.loadingFieldReports')}</p> : null}
      {error ? (
        <div className="admin-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setRetryKey((k) => k + 1)}>{t('admin.retry')}</button>
        </div>
      ) : null}

      {!isLoading && !error && reports.length === 0 ? (
        <p className="admin-empty-state">{t('admin.noFieldReports')}</p>
      ) : null}

      {!isLoading && !error && reports.length > 0 && visibleReports.length === 0 ? (
        <p className="admin-empty-state">{t('admin.noFieldReportsForFilter')}</p>
      ) : null}

      {!isLoading && !error && visibleReports.length > 0 ? (
        <div className="admin-table-wrap">
          <table className="admin-table admin-field-reports-table">
            <thead>
              <tr>
                <th>{t('admin.fieldName')}</th>
                <th>{t('admin.reportCategory')}</th>
                <th>{t('admin.reporter')}</th>
                <th>{t('admin.date')}</th>
                <th>{t('admin.status')}</th>
                <th>{t('admin.descriptionColumn')}</th>
                <th>{t('admin.fieldReportManage.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {visibleReports.map((report) => (
                <tr key={report.id}>
                  <td>{formatValue(report.field_name, report.field_id)}</td>
                  <td>{formatCategory(report.category)}</td>
                  <td>{formatReporter(report)}</td>
                  <td>{formatDate(report.created_at)}</td>
                  <td>
                    <span className={`admin-report-status ${report.status ?? 'unknown'}`}>
                      {t(`admin.fieldReportStatuses.${report.status}`, report.status)}
                    </span>
                  </td>
                  <td>{formatValue(report.description)}</td>
                  <td>
                    <button
                      type="button"
                      className="admin-manage-report-button"
                      onClick={() => openManage(report)}
                    >
                      {t('admin.fieldReportManage.manage')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <Modal
        isOpen={!!managingReport}
        onClose={isSaving ? undefined : closeManage}
        isConfirm
        ariaLabelledBy="admin-manage-report-title"
      >
        <h3 id="admin-manage-report-title">{t('admin.fieldReportManage.title')}</h3>
        <p>
          {managingReport
            ? `${formatValue(managingReport.field_name, managingReport.field_id)} — ${formatCategory(managingReport.category)}`
            : ''}
        </p>

        <label className="confirm-modal-label">
          <span>{t('admin.fieldReportManage.statusLabel')}</span>
          <select
            className="confirm-modal-input"
            value={editStatus}
            onChange={(e) => setEditStatus(e.target.value)}
            disabled={isSaving}
          >
            {REVIEW_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`admin.fieldReportStatuses.${s}`, s)}
              </option>
            ))}
          </select>
        </label>

        <label className="confirm-modal-label">
          <span>
            {t('admin.fieldReportManage.noteLabel')}
            {' '}
            <span className="admin-note-counter">
              {editNote.length}/{ADMIN_NOTE_MAX}
            </span>
          </span>
          <textarea
            className="confirm-modal-input"
            rows={3}
            maxLength={ADMIN_NOTE_MAX}
            value={editNote}
            onChange={(e) => setEditNote(e.target.value)}
            disabled={isSaving}
            placeholder={t('admin.fieldReportManage.notePlaceholder')}
          />
        </label>

        {saveError ? <p className="modal-error" role="alert">{saveError}</p> : null}
        {saveSuccess ? <p className="modal-success" role="status">{saveSuccess}</p> : null}

        <div className="confirm-modal-actions">
          <button
            type="button"
            className="secondary-modal-button"
            onClick={closeManage}
            disabled={isSaving}
          >
            {t('admin.fieldReportManage.cancel')}
          </button>
          <button
            type="button"
            className="primary-modal-button"
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? t('admin.fieldReportManage.saving') : t('admin.fieldReportManage.save')}
          </button>
        </div>
      </Modal>
    </div>
  )
}

export default AdminFieldReports
