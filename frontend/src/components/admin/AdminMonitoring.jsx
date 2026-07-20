import {
  Activity,
  Bell,
  Clock3,
  Database,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { getAdminMonitoring } from '../../api/admin'
import {
  DashboardError,
  DashboardLoading,
  DashboardRefreshError,
  DashboardSection,
  DashboardStatus,
  DashboardToolbar,
  MetricCard,
  SectionNotice,
} from './AdminDashboardComponents'
import {
  formatAdminNumber,
  formatAdminTimestamp,
  getAdminDashboardErrorCopy,
  sourceIsAvailable,
  useAdminDashboardResource,
} from './adminDashboardShared'

function AdminMonitoring() {
  const { i18n, t } = useTranslation()
  const {
    data: monitoring,
    errorKey,
    isLoading,
    isRefreshing,
    lastRefreshedAt,
    load: loadMonitoring,
  } = useAdminDashboardResource(getAdminMonitoring)

  const locale = i18n.language === 'he' ? 'he-IL' : 'en-US'
  const errorCopy = getAdminDashboardErrorCopy(
    errorKey,
    t,
    'admin.monitoringErrors',
  )

  if (isLoading && !monitoring) {
    return <DashboardLoading>{t('admin.monitoringLoading')}</DashboardLoading>
  }

  if (errorKey && !monitoring) {
    return (
      <DashboardError
        actionLabel={errorCopy.actionLabel}
        errorKey={errorKey}
        message={errorCopy.message}
        onRetry={() => loadMonitoring()}
      />
    )
  }

  const windowMinutes = monitoring?.api_errors?.window_minutes
    ?? monitoring?.response_time?.window_minutes
    ?? monitoring?.push_notifications?.window_minutes
  const generatedAt = formatAdminTimestamp(monitoring?.generated_at, locale)
  const refreshedAt = formatAdminTimestamp(lastRefreshedAt, locale)
  const apiErrors = monitoring?.api_errors
  const responseTime = monitoring?.response_time
  const pushNotifications = monitoring?.push_notifications
  const scheduledJobs = monitoring?.scheduled_jobs
  const recentRuns = Array.isArray(scheduledJobs?.recent_runs)
    ? scheduledJobs.recent_runs.filter((run) => run && typeof run === 'object')
    : []

  return (
    <div className="admin-monitoring" aria-busy={isRefreshing}>
      <DashboardToolbar
        disabled={isRefreshing || isLoading}
        isRefreshing={isRefreshing}
        onRefresh={() => loadMonitoring({ background: true })}
        refreshLabel={t('admin.monitoringRefresh')}
        refreshingLabel={t('admin.monitoringRefreshing')}
      >
        <p className="admin-monitoring-window">
          {windowMinutes !== null && windowMinutes !== undefined
            ? t('admin.monitoringWindow', { count: windowMinutes })
            : t('admin.monitoringWindowUnavailable')}
        </p>
        <div className="admin-monitoring-timestamps">
          {generatedAt ? <span>{t('admin.monitoringGeneratedAt', { value: generatedAt })}</span> : null}
          {refreshedAt ? <span>{t('admin.monitoringRefreshedAt', { value: refreshedAt })}</span> : null}
        </div>
      </DashboardToolbar>

      {errorKey ? (
        <DashboardRefreshError
          onRetry={() => loadMonitoring({ background: true })}
          retryLabel={t('admin.retry')}
        >
          {errorCopy.message}
        </DashboardRefreshError>
      ) : null}

      <DashboardStatus
        isOk={monitoring?.status === 'ok'}
        okLabel={t('admin.monitoringStatusOk')}
        partialLabel={t('admin.monitoringStatusDegraded')}
      />

      <div className="admin-monitoring-sections">
        <DashboardSection
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
        </DashboardSection>

        <DashboardSection
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
        </DashboardSection>

        <DashboardSection
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
        </DashboardSection>

        <DashboardSection
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
                  <strong>{formatAdminTimestamp(scheduledJobs.latest_started_at, locale) ?? t('admin.monitoringUnavailable')}</strong>
                </div>
                <div>
                  <span>{t('admin.monitoringLatestJobFinished')}</span>
                  <strong>{formatAdminTimestamp(scheduledJobs.latest_finished_at, locale) ?? t('admin.monitoringUnavailable')}</strong>
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
                        <td>{formatAdminTimestamp(run.started_at, locale) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatAdminNumber(run.duration_ms, locale, 1) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatAdminNumber(run.processed_count, locale) ?? t('admin.monitoringUnavailable')}</td>
                        <td>{formatAdminNumber(run.failed_count, locale) ?? t('admin.monitoringUnavailable')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </DashboardSection>
      </div>
    </div>
  )
}

export default AdminMonitoring
