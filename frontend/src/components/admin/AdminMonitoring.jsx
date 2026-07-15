import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCw,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { getAdminMonitoring } from '../../api/admin'

const ERROR_KEYS = {
  unauthorized: 'unauthorized',
  forbidden: 'forbidden',
  missing: 'missing',
  unavailable: 'unavailable',
}

function getErrorKey(error) {
  const responseStatus = error?.response?.status

  if (responseStatus === 401) {
    return ERROR_KEYS.unauthorized
  }

  if (responseStatus === 403) {
    return ERROR_KEYS.forbidden
  }

  if (responseStatus === 404) {
    return ERROR_KEYS.missing
  }

  return ERROR_KEYS.unavailable
}

function isCanceledRequest(error) {
  return error?.code === 'ERR_CANCELED'
    || error?.name === 'AbortError'
    || error?.name === 'CanceledError'
}

function formatNumber(value, locale, fractionDigits = 0) {
  if (value === null || value === undefined) {
    return null
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(value)
}

function formatRate(value, locale) {
  const formatted = formatNumber(value === null ? null : value * 100, locale, 1)
  return formatted === null ? null : `${formatted}%`
}

function formatTimestamp(value, locale) {
  if (!value) {
    return null
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date)
}

function MetricCard({ description, format = 'count', label, locale, unavailableLabel, value }) {
  const displayValue = format === 'rate'
    ? formatRate(value, locale)
    : format === 'milliseconds'
      ? formatNumber(value, locale, 1)
      : formatNumber(value, locale)

  return (
    <article className="admin-monitoring-metric">
      <span className="admin-monitoring-metric-label">{label}</span>
      <strong>{displayValue ?? unavailableLabel}</strong>
      <small>{description}</small>
    </article>
  )
}

function SectionNotice({ children, variant = 'empty' }) {
  return (
    <div className={`admin-monitoring-notice ${variant}`} role={variant === 'unavailable' ? 'status' : undefined}>
      {variant === 'unavailable' ? <AlertTriangle aria-hidden="true" size={18} /> : null}
      <p>{children}</p>
    </div>
  )
}

function MonitoringSection({ children, description, icon: Icon, id, title }) {
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

function sourceIsAvailable(group) {
  return Boolean(group) && group.source_available === true
}

function AdminMonitoring() {
  const { i18n, t } = useTranslation()
  const [monitoring, setMonitoring] = useState(null)
  const [errorKey, setErrorKey] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const requestRef = useRef(null)
  const nextRequestIdRef = useRef(0)

  const locale = i18n.language === 'he' ? 'he-IL' : 'en-US'

  const loadMonitoring = useCallback(async ({ background = false, initial = false } = {}) => {
    if (requestRef.current) {
      return
    }

    const requestId = nextRequestIdRef.current + 1
    nextRequestIdRef.current = requestId
    const controller = new AbortController()
    requestRef.current = { controller, requestId }

    if (background) {
      setIsRefreshing(true)
    } else if (!initial) {
      setIsLoading(true)
    }
    if (!initial) {
      setErrorKey('')
    }

    try {
      const data = await getAdminMonitoring({ signal: controller.signal })

      if (requestRef.current?.requestId !== requestId) {
        return
      }

      setMonitoring(data)
      setLastRefreshedAt(new Date().toISOString())
    } catch (error) {
      if (isCanceledRequest(error) || requestRef.current?.requestId !== requestId) {
        return
      }

      setErrorKey(getErrorKey(error))
    } finally {
      if (requestRef.current?.requestId === requestId) {
        requestRef.current = null
        setIsLoading(false)
        setIsRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    const initialLoadId = window.setTimeout(() => {
      loadMonitoring({ initial: true })
    }, 0)

    return () => {
      window.clearTimeout(initialLoadId)
      requestRef.current?.controller.abort()
      requestRef.current = null
    }
  }, [loadMonitoring])

  const errorMessage = errorKey === ERROR_KEYS.unauthorized
    ? t('admin.monitoringErrors.unauthorized')
    : errorKey === ERROR_KEYS.forbidden
      ? t('admin.monitoringErrors.forbidden')
      : errorKey === ERROR_KEYS.missing
        ? t('admin.monitoringErrors.missing')
        : t('admin.monitoringErrors.unavailable')
  const errorActionLabel = errorKey === ERROR_KEYS.unauthorized
    ? t('admin.monitoringSignInAgain')
    : t('admin.retry')

  if (isLoading && !monitoring) {
    return (
      <div className="admin-monitoring-status" aria-live="polite" aria-busy="true">
        <RefreshCw className="admin-monitoring-spin" aria-hidden="true" size={18} />
        <span>{t('admin.monitoringLoading')}</span>
      </div>
    )
  }

  if (errorKey && !monitoring) {
    return (
      <div className="admin-monitoring-error" role="alert">
        <AlertTriangle aria-hidden="true" size={20} />
        <div>
          <p>{errorMessage}</p>
          <button
            type="button"
            onClick={() => {
              if (errorKey === ERROR_KEYS.unauthorized) {
                window.location.reload()
              } else {
                loadMonitoring()
              }
            }}
          >
            {errorActionLabel}
          </button>
        </div>
      </div>
    )
  }

  const windowMinutes = monitoring?.api_errors?.window_minutes
    ?? monitoring?.response_time?.window_minutes
    ?? monitoring?.push_notifications?.window_minutes
  const generatedAt = formatTimestamp(monitoring?.generated_at, locale)
  const refreshedAt = formatTimestamp(lastRefreshedAt, locale)
  const apiErrors = monitoring?.api_errors
  const responseTime = monitoring?.response_time
  const pushNotifications = monitoring?.push_notifications
  const scheduledJobs = monitoring?.scheduled_jobs
  const recentRuns = Array.isArray(scheduledJobs?.recent_runs)
    ? scheduledJobs.recent_runs.filter((run) => run && typeof run === 'object')
    : []

  return (
    <div className="admin-monitoring" aria-busy={isRefreshing}>
      <div className="admin-monitoring-toolbar">
        <div>
          <p className="admin-monitoring-window">
            {windowMinutes !== null && windowMinutes !== undefined
              ? t('admin.monitoringWindow', { count: windowMinutes })
              : t('admin.monitoringWindowUnavailable')}
          </p>
          <div className="admin-monitoring-timestamps">
            {generatedAt ? <span>{t('admin.monitoringGeneratedAt', { value: generatedAt })}</span> : null}
            {refreshedAt ? <span>{t('admin.monitoringRefreshedAt', { value: refreshedAt })}</span> : null}
          </div>
        </div>
        <button
          className="admin-monitoring-refresh-button"
          type="button"
          onClick={() => loadMonitoring({ background: true })}
          disabled={isRefreshing || isLoading}
          aria-busy={isRefreshing}
        >
          <RefreshCw className={isRefreshing ? 'admin-monitoring-spin' : ''} aria-hidden="true" size={17} />
          {isRefreshing ? t('admin.monitoringRefreshing') : t('admin.monitoringRefresh')}
        </button>
      </div>

      {errorKey ? (
        <div className="admin-monitoring-refresh-error" role="alert">
          <AlertTriangle aria-hidden="true" size={18} />
          <span>{errorMessage}</span>
          <button type="button" onClick={() => loadMonitoring({ background: true })}>
            {t('admin.retry')}
          </button>
        </div>
      ) : null}

      <div className="admin-monitoring-summary" role="status">
        {monitoring?.status === 'ok' ? <CheckCircle2 aria-hidden="true" size={18} /> : <AlertTriangle aria-hidden="true" size={18} />}
        <span>
          {monitoring?.status === 'ok'
            ? t('admin.monitoringStatusOk')
            : t('admin.monitoringStatusDegraded')}
        </span>
      </div>

      <div className="admin-monitoring-sections">
        <MonitoringSection
          description={t('admin.monitoringOperationalDescription')}
          icon={Database}
          id="admin-monitoring-operational"
          title={t('admin.monitoringOperational')}
        >
          <div className="admin-monitoring-grid">
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.count')}
              label={t('admin.monitoringMetrics.activeGames')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.active_games?.count}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.windowedUsers')}
              label={t('admin.monitoringMetrics.activeUsers24h')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.active_users?.last_24h}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.windowedUsers')}
              label={t('admin.monitoringMetrics.activeUsers7d')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.active_users?.last_7d}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.allTime')}
              label={t('admin.monitoringMetrics.totalUsers')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.active_users?.total_registered}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.last24h')}
              label={t('admin.monitoringMetrics.notificationsCreated')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.notifications?.created_last_24h}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.currentTotal')}
              label={t('admin.monitoringMetrics.unreadNotifications')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.notifications?.unread_total}
            />
            <MetricCard
              description={t('admin.monitoringMetricDescriptions.currentTotal')}
              label={t('admin.monitoringMetrics.pendingFields')}
              locale={locale}
              unavailableLabel={t('admin.monitoringUnavailable')}
              value={monitoring?.moderation?.pending_fields}
            />
            <article className="admin-monitoring-metric">
              <span className="admin-monitoring-metric-label">{t('admin.monitoringMetrics.database')}</span>
              <strong className={monitoring?.database?.healthy === false ? 'is-degraded' : ''}>
                {monitoring?.database?.healthy === true
                  ? t('admin.monitoringHealthy')
                  : monitoring?.database?.healthy === false
                    ? t('admin.monitoringDegraded')
                    : t('admin.monitoringUnavailable')}
              </strong>
              <small>{t('admin.monitoringMetricDescriptions.connectivity')}</small>
            </article>
          </div>
        </MonitoringSection>

        <MonitoringSection
          description={t('admin.monitoringApiDescription')}
          icon={Activity}
          id="admin-monitoring-api"
          title={t('admin.monitoringApi')}
        >
          {!sourceIsAvailable(apiErrors) ? (
            <SectionNotice variant="unavailable">{t('admin.monitoringSourceUnavailable')}</SectionNotice>
          ) : (
            <div className="admin-monitoring-grid">
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.completedRequests')}
                label={t('admin.monitoringMetrics.totalRequests')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={apiErrors.total_requests}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.serverFailures')}
                label={t('admin.monitoringMetrics.failedRequests')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={apiErrors.failed_requests}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.serverFailureRate')}
                format="rate"
                label={t('admin.monitoringMetrics.errorRate')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={apiErrors.error_rate}
              />
            </div>
          )}

          <div className="admin-monitoring-subsection">
            <h4>{t('admin.monitoringResponseTime')}</h4>
            {!sourceIsAvailable(responseTime) ? (
              <SectionNotice variant="unavailable">{t('admin.monitoringSourceUnavailable')}</SectionNotice>
            ) : responseTime.sample_count === 0 ? (
              <SectionNotice>{t('admin.monitoringNoResponseSamples')}</SectionNotice>
            ) : (
              <div className="admin-monitoring-grid">
                <MetricCard
                  description={t('admin.monitoringMetricDescriptions.completedRequests')}
                  label={t('admin.monitoringMetrics.responseSamples')}
                  locale={locale}
                  unavailableLabel={t('admin.monitoringUnavailable')}
                  value={responseTime.sample_count}
                />
                <MetricCard
                  description={t('admin.monitoringMetricDescriptions.milliseconds')}
                  format="milliseconds"
                  label={t('admin.monitoringMetrics.averageResponse')}
                  locale={locale}
                  unavailableLabel={t('admin.monitoringUnavailable')}
                  value={responseTime.average_ms}
                />
                <MetricCard
                  description={t('admin.monitoringMetricDescriptions.milliseconds')}
                  format="milliseconds"
                  label={t('admin.monitoringMetrics.p50Response')}
                  locale={locale}
                  unavailableLabel={t('admin.monitoringUnavailable')}
                  value={responseTime.p50_ms}
                />
                <MetricCard
                  description={t('admin.monitoringMetricDescriptions.milliseconds')}
                  format="milliseconds"
                  label={t('admin.monitoringMetrics.p95Response')}
                  locale={locale}
                  unavailableLabel={t('admin.monitoringUnavailable')}
                  value={responseTime.p95_ms}
                />
                <MetricCard
                  description={t('admin.monitoringMetricDescriptions.milliseconds')}
                  format="milliseconds"
                  label={t('admin.monitoringMetrics.maxResponse')}
                  locale={locale}
                  unavailableLabel={t('admin.monitoringUnavailable')}
                  value={responseTime.max_ms}
                />
              </div>
            )}
          </div>
        </MonitoringSection>

        <MonitoringSection
          description={t('admin.monitoringPushDescription')}
          icon={Bell}
          id="admin-monitoring-push"
          title={t('admin.monitoringPush')}
        >
          {!sourceIsAvailable(pushNotifications) ? (
            <SectionNotice variant="unavailable">{t('admin.monitoringSourceUnavailable')}</SectionNotice>
          ) : pushNotifications.attempted_count === 0 ? (
            <SectionNotice>{t('admin.monitoringNoPushAttempts')}</SectionNotice>
          ) : (
            <div className="admin-monitoring-grid">
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.pushAttempts')}
                label={t('admin.monitoringMetrics.pushAttempts')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={pushNotifications.attempted_count}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.providerAccepted')}
                label={t('admin.monitoringMetrics.pushAccepted')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={pushNotifications.accepted_count}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.pushFailures')}
                label={t('admin.monitoringMetrics.pushFailed')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={pushNotifications.failed_count}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.invalidTokens')}
                label={t('admin.monitoringMetrics.invalidTokens')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={pushNotifications.invalid_token_count}
              />
              <MetricCard
                description={t('admin.monitoringMetricDescriptions.providerAcceptanceRate')}
                format="rate"
                label={t('admin.monitoringMetrics.pushAcceptanceRate')}
                locale={locale}
                unavailableLabel={t('admin.monitoringUnavailable')}
                value={pushNotifications.acceptance_rate}
              />
            </div>
          )}
        </MonitoringSection>

        <MonitoringSection
          description={t('admin.monitoringJobsDescription')}
          icon={Clock3}
          id="admin-monitoring-jobs"
          title={t('admin.monitoringJobs')}
        >
          {!sourceIsAvailable(scheduledJobs) ? (
            <SectionNotice variant="unavailable">{t('admin.monitoringSourceUnavailable')}</SectionNotice>
          ) : recentRuns.length === 0 ? (
            <SectionNotice>{t('admin.monitoringNoJobRuns')}</SectionNotice>
          ) : (
            <>
              <div className="admin-monitoring-job-summary">
                <div>
                  <span>{t('admin.monitoringLatestJobStatus')}</span>
                  <strong>{scheduledJobs.latest_status
                    ? t(`admin.monitoringJobStatus.${scheduledJobs.latest_status}`, scheduledJobs.latest_status)
                    : t('admin.monitoringUnavailable')}</strong>
                </div>
                <div>
                  <span>{t('admin.monitoringLatestJobStarted')}</span>
                  <strong>{formatTimestamp(scheduledJobs.latest_started_at, locale) ?? t('admin.monitoringUnavailable')}</strong>
                </div>
                <div>
                  <span>{t('admin.monitoringLatestJobFinished')}</span>
                  <strong>{formatTimestamp(scheduledJobs.latest_finished_at, locale) ?? t('admin.monitoringUnavailable')}</strong>
                </div>
              </div>
              <div className="admin-monitoring-table-wrap">
                <table className="admin-monitoring-table">
                  <caption>{t('admin.monitoringRecentRuns')}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t('admin.monitoringTable.status')}</th>
                      <th scope="col">{t('admin.monitoringTable.started')}</th>
                      <th scope="col">{t('admin.monitoringTable.duration')}</th>
                      <th scope="col">{t('admin.monitoringTable.processed')}</th>
                      <th scope="col">{t('admin.monitoringTable.failed')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentRuns.map((run, index) => (
                      <tr key={run.id ?? `${run.started_at ?? 'run'}-${index}`}>
                        <td>{run.status
                          ? t(`admin.monitoringJobStatus.${run.status}`, run.status)
                          : t('admin.monitoringUnavailable')}</td>
                        <td>{formatTimestamp(run.started_at, locale) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatNumber(run.duration_ms, locale, 1) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatNumber(run.processed_count, locale) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatNumber(run.failed_count, locale) ?? t('admin.monitoringUnavailable')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </MonitoringSection>
      </div>
    </div>
  )
}

export default AdminMonitoring
