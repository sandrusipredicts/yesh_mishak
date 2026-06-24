import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAdminFieldReports } from '../../api/admin'

const STATUS_FILTERS = ['all', 'open', 'in_review', 'resolved', 'rejected']

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

function AdminFieldReports() {
  const { i18n, t } = useTranslation()
  const [reports, setReports] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

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
        <div className="admin-error">
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export default AdminFieldReports
