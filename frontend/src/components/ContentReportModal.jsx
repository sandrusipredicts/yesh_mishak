import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { createContentReport } from '../api/moderation'
import Modal from './Modal'

const REPORT_REASONS = [
  'abuse',
  'harassment',
  'hate',
  'spam',
  'impersonation',
  'inappropriate',
  'other',
]

function ContentReportModal({ onClose, onSubmitted, target }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!reason || isSubmitting) return
    setIsSubmitting(true)
    setError('')
    try {
      await createContentReport({
        targetType: target.type,
        targetId: target.id,
        reason,
        description,
      })
      onSubmitted()
    } catch {
      setError(t('contentSafety.reportFailed'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen onClose={onClose} className="field-report-modal" ariaLabelledBy="content-report-title">
      <h2 id="content-report-title">{t(`contentSafety.report${target.type === 'game' ? 'Game' : 'User'}`)}</h2>
      {target.label ? <p>{target.label}</p> : null}
      <form className="field-report-form" onSubmit={handleSubmit}>
        <label htmlFor="content-report-reason">{t('contentSafety.reason')}</label>
        <select
          id="content-report-reason"
          onChange={(event) => setReason(event.target.value)}
          required
          value={reason}
        >
          <option value="">{t('contentSafety.chooseReason')}</option>
          {REPORT_REASONS.map((value) => (
            <option key={value} value={value}>{t(`contentSafety.reasons.${value}`)}</option>
          ))}
        </select>
        <label htmlFor="content-report-description">{t('contentSafety.description')}</label>
        <textarea
          id="content-report-description"
          maxLength={500}
          onChange={(event) => setDescription(event.target.value)}
          rows={4}
          value={description}
        />
        {error ? <p className="modal-error" role="alert">{error}</p> : null}
        <div className="field-report-actions">
          <button className="secondary-panel-button" disabled={isSubmitting} onClick={onClose} type="button">
            {t('contentSafety.cancel')}
          </button>
          <button className="primary-panel-button" disabled={!reason || isSubmitting} type="submit">
            {isSubmitting ? t('contentSafety.submitting') : t('contentSafety.submit')}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default ContentReportModal
