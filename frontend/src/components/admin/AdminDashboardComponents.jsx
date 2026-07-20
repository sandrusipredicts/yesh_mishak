import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react'

import {
  formatAdminNumber,
  formatAdminRate,
  isUnauthorizedAdminDashboardError,
} from './adminDashboardShared'

export function MetricCard({
  description,
  format = 'count',
  label,
  locale,
  unavailableLabel,
  value,
}) {
  const displayValue = format === 'rate'
    ? formatAdminRate(value, locale)
    : format === 'milliseconds'
      ? formatAdminNumber(value, locale, 1)
      : formatAdminNumber(value, locale)

  return (
    <article className="admin-monitoring-metric">
      <span className="admin-monitoring-metric-label">{label}</span>
      <strong>{displayValue ?? unavailableLabel}</strong>
      <small>{description}</small>
    </article>
  )
}

export function SectionNotice({ children, variant = 'empty' }) {
  return (
    <div
      className={`admin-monitoring-notice ${variant}`}
      role={variant === 'unavailable' ? 'status' : undefined}
    >
      {variant === 'unavailable' ? <AlertTriangle aria-hidden="true" size={18} /> : null}
      <p>{children}</p>
    </div>
  )
}

export function DashboardSection({ children, description, icon: Icon, id, title }) {
  return (
    <section className="admin-monitoring-section" aria-labelledby={id}>
      <div className="admin-monitoring-section-header">
        <div className="admin-monitoring-section-title">
          <Icon aria-hidden="true" size={20} />
          <div>
            <h3 id={id}>{title}</h3>
            <p>{description}</p>
          </div>
        </div>
      </div>
      {children}
    </section>
  )
}

export function DashboardLoading({ children }) {
  return (
    <div className="admin-monitoring-status" aria-live="polite" aria-busy="true">
      <RefreshCw className="admin-monitoring-spin" aria-hidden="true" size={18} />
      <span>{children}</span>
    </div>
  )
}

export function DashboardError({
  actionLabel,
  errorKey,
  message,
  onRetry,
}) {
  return (
    <div className="admin-monitoring-error" role="alert">
      <AlertTriangle aria-hidden="true" size={20} />
      <div>
        <p>{message}</p>
        <button
          type="button"
          onClick={() => {
            if (isUnauthorizedAdminDashboardError(errorKey)) {
              window.location.reload()
            } else {
              onRetry()
            }
          }}
        >
          {actionLabel}
        </button>
      </div>
    </div>
  )
}

export function DashboardRefreshError({ children, onRetry, retryLabel }) {
  return (
    <div className="admin-monitoring-refresh-error" role="alert">
      <AlertTriangle aria-hidden="true" size={18} />
      <span>{children}</span>
      <button type="button" onClick={onRetry}>
        {retryLabel}
      </button>
    </div>
  )
}

export function DashboardToolbar({
  children,
  disabled,
  isRefreshing,
  onRefresh,
  refreshLabel,
  refreshingLabel,
}) {
  return (
    <div className="admin-monitoring-toolbar">
      <div>{children}</div>
      <button
        className="admin-monitoring-refresh-button"
        type="button"
        onClick={onRefresh}
        disabled={disabled}
        aria-busy={isRefreshing}
      >
        <RefreshCw
          className={isRefreshing ? 'admin-monitoring-spin' : ''}
          aria-hidden="true"
          size={17}
        />
        {isRefreshing ? refreshingLabel : refreshLabel}
      </button>
    </div>
  )
}

export function DashboardStatus({ isOk, okLabel, partialLabel }) {
  return (
    <div className="admin-monitoring-summary" role="status">
      {isOk
        ? <CheckCircle2 aria-hidden="true" size={18} />
        : <AlertTriangle aria-hidden="true" size={18} />}
      <span>{isOk ? okLabel : partialLabel}</span>
    </div>
  )
}
