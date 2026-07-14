import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowRight, ArrowLeft } from 'lucide-react'
import { getMyFieldReports } from '../api/fieldReports'

const STATUS_KEYS = {
  open: 'statusOpen',
  in_review: 'statusInReview',
  resolved: 'statusResolved',
  rejected: 'statusRejected',
}

const CATEGORY_KEYS = {
  wrong_location: 'categoryWrongLocation',
  field_does_not_exist: 'categoryFieldDoesNotExist',
  field_closed: 'categoryFieldClosed',
  under_renovation: 'categoryUnderRenovation',
  private_field: 'categoryPrivateField',
  duplicate_field: 'categoryDuplicateField',
  wrong_information: 'categoryWrongInformation',
  other: 'categoryOther',
}

function formatDate(value, locale) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function ReportRow({ report, t, locale }) {
  const statusKey = STATUS_KEYS[report.status] || report.status
  const categoryKey = CATEGORY_KEYS[report.category] || report.category

  return (
    <div className="my-reports-row">
      <div className="my-reports-row-main">
        <span className="my-reports-field-name">{report.field_name || '—'}</span>
        <span className={`my-reports-status my-reports-status-${report.status}`}>
          {t(`myReports.${statusKey}`, report.status)}
        </span>
      </div>
      <div className="my-reports-row-details">
        <span className="my-reports-category">
          {t(`myReports.${categoryKey}`, report.category)}
        </span>
        {report.description && (
          <>
            <span className="my-reports-separator">·</span>
            <span className="my-reports-description">{report.description}</span>
          </>
        )}
      </div>
      {report.admin_note && (
        <div className="my-reports-admin-note">
          <strong>{t('myReports.adminNote')}:</strong> {report.admin_note}
        </div>
      )}
      <div className="my-reports-row-date">
        {formatDate(report.created_at, locale)}
      </div>
    </div>
  )
}

function MyReportsPage({ onBack }) {
  const { i18n, t } = useTranslation()
  const [reports, setReports] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const isRtl = i18n.dir() === 'rtl'
  const BackArrow = isRtl ? ArrowRight : ArrowLeft

  const loadReports = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getMyFieldReports()
      setReports(result)
    } catch {
      setError(t('myReports.loadError'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    let active = true

    getMyFieldReports()
      .then((result) => {
        if (active) {
          setReports(result)
          setError(null)
        }
      })
      .catch(() => {
        if (active) {
          setError(t('myReports.loadError'))
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })

    return () => { active = false }
  }, [t])

  return (
    <div className="my-reports-page">
      <header className="my-reports-header">
        <button type="button" className="my-reports-back-button" onClick={onBack}>
          <BackArrow size={20} />
          {t('myReports.back')}
        </button>
        <h2 className="my-reports-title">{t('myReports.title')}</h2>
      </header>

      {loading && <p className="my-reports-loading">{t('myReports.loading')}</p>}
      {error && (
        <div className="my-reports-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={loadReports}>{t('admin.retry')}</button>
        </div>
      )}

      {!loading && !error && (!reports || reports.length === 0) && (
        <p className="my-reports-empty">{t('myReports.empty')}</p>
      )}

      {!loading && !error && reports && reports.length > 0 && (
        <div className="my-reports-list">
          {reports.map((report) => (
            <ReportRow key={report.id} report={report} t={t} locale={i18n.language} />
          ))}
        </div>
      )}
    </div>
  )
}

export default MyReportsPage
