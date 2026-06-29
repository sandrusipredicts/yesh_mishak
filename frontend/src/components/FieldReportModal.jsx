import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import Modal from './Modal'

import { createFieldReport } from '../api/fieldReports'

const FIELD_REPORT_CATEGORIES = [
  { key: 'field_closed', labelKey: 'fieldReport.categories.fieldClosed' },
  { key: 'under_renovation', labelKey: 'fieldReport.categories.underRenovation' },
  { key: 'wrong_location', labelKey: 'fieldReport.categories.wrongLocation' },
  { key: 'field_does_not_exist', labelKey: 'fieldReport.categories.fieldDoesNotExist' },
  { key: 'private_field', labelKey: 'fieldReport.categories.privateField' },
  { key: 'duplicate_field', labelKey: 'fieldReport.categories.duplicateField' },
  { key: 'wrong_information', labelKey: 'fieldReport.categories.wrongInformation' },
  { key: 'other', labelKey: 'fieldReport.categories.other' },
]

function getApiErrorMessage(apiError, fallback) {
  const detail = apiError?.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || fallback
  }

  if (detail?.message) {
    return detail.message
  }

  return fallback
}

function FieldReportModal({ field, onClose }) {
  const { t } = useTranslation()
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()

    if (isSubmitting) {
      return
    }

    const trimmedDescription = description.trim()
    if (!category) {
      setError(t('fieldReport.categoryRequired'))
      return
    }

    if (!trimmedDescription) {
      setError(t('fieldReport.descriptionRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')
    setSuccessMessage('')

    try {
      await createFieldReport({
        field_id: field.id,
        category,
        description: trimmedDescription,
      })
      setSuccessMessage(t('fieldReport.success'))
      setCategory('')
      setDescription('')
      window.setTimeout(() => {
        onClose()
      }, 700)
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, t('fieldReport.submitFailed')))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      className="field-report-modal"
      ariaLabelledBy="field-report-title"
    >
      <h2 id="field-report-title">{t('fieldReport.title')}</h2>
        <p className="field-report-field-name">{field.name}</p>

        <form className="field-report-form" onSubmit={handleSubmit}>
          <label>
            <span>{t('fieldReport.category')}</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              disabled={isSubmitting}
              required
            >
              <option value="">{t('fieldReport.chooseCategory')}</option>
              {FIELD_REPORT_CATEGORIES.map((option) => (
                <option key={option.key} value={option.key}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>{t('fieldReport.description')}</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t('fieldReport.descriptionPlaceholder')}
              rows={4}
              disabled={isSubmitting}
              required
            />
          </label>

          {error ? <p className="modal-error" role="alert">{error}</p> : null}
          {successMessage ? <p className="modal-success">{successMessage}</p> : null}

          <div className="field-report-actions">
            <button className="secondary-modal-button" type="button" onClick={onClose} disabled={isSubmitting}>
              {t('fieldReport.cancel')}
            </button>
            <button className="primary-modal-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('fieldReport.submitting') : t('fieldReport.submit')}
            </button>
          </div>
        </form>
    </Modal>
  )
}

export default FieldReportModal
