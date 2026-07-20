import { useCallback, useState } from 'react'
import {
  Activity,
  BarChart3,
  Share2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { getAdminEngagement } from '../../api/admin'
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

const WINDOW_OPTIONS = [7, 30, 90]

function EngagementTable({ caption, columns, rows, rowKey }) {
  return (
    <div className="admin-monitoring-table-wrap">
      <table className="admin-monitoring-table admin-engagement-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th scope="col" key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CountBars({ ariaLabel, items, locale }) {
  const maximum = Math.max(1, ...items.map((item) => item.value ?? 0))

  return (
    <div className="admin-engagement-breakdown" role="img" aria-label={ariaLabel}>
      {items.map((item) => (
        <div className="admin-engagement-breakdown-row" key={item.key}>
          <span>{item.label}</span>
          <div className="admin-engagement-breakdown-track" aria-hidden="true">
            <span style={{ width: `${((item.value ?? 0) / maximum) * 100}%` }} />
          </div>
          <strong>{formatAdminNumber(item.value, locale) ?? '—'}</strong>
        </div>
      ))}
    </div>
  )
}

function DailyActivityChart({ ariaLabel, appOpensLabel, rows, screenViewsLabel }) {
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => [row.app_opens ?? 0, row.screen_views ?? 0]),
  )

  return (
    <figure className="admin-engagement-trend">
      <div className="admin-engagement-legend" aria-hidden="true">
        <span><i className="app-opens" />{appOpensLabel}</span>
        <span><i className="screen-views" />{screenViewsLabel}</span>
      </div>
      <div className="admin-engagement-trend-scroll">
        <div className="admin-engagement-trend-chart" role="img" aria-label={ariaLabel}>
          {rows.map((row) => (
            <div className="admin-engagement-day" key={row.event_day}>
              <div className="admin-engagement-day-bars" aria-hidden="true">
                <span
                  className="app-opens"
                  style={{ height: `${((row.app_opens ?? 0) / maximum) * 100}%` }}
                  title={`${appOpensLabel}: ${row.app_opens ?? 0}`}
                />
                <span
                  className="screen-views"
                  style={{ height: `${((row.screen_views ?? 0) / maximum) * 100}%` }}
                  title={`${screenViewsLabel}: ${row.screen_views ?? 0}`}
                />
              </div>
              <small>{row.event_day.slice(5)}</small>
            </div>
          ))}
        </div>
      </div>
    </figure>
  )
}

function AdminEngagement() {
  const { i18n, t } = useTranslation()
  const [windowDays, setWindowDays] = useState(30)
  const loadEngagementRequest = useCallback(
    ({ signal }) => getAdminEngagement({ signal, windowDays }),
    [windowDays],
  )
  const {
    data: engagement,
    errorKey,
    isLoading,
    isRefreshing,
    lastRefreshedAt,
    load: loadEngagement,
  } = useAdminDashboardResource(loadEngagementRequest)

  const locale = i18n.language === 'he' ? 'he-IL' : 'en-US'
  const errorCopy = getAdminDashboardErrorCopy(
    errorKey,
    t,
    'admin.engagementErrors',
  )

  if (isLoading && !engagement) {
    return <DashboardLoading>{t('admin.engagementLoading')}</DashboardLoading>
  }

  if (errorKey && !engagement) {
    return (
      <DashboardError
        actionLabel={errorCopy.actionLabel}
        errorKey={errorKey}
        message={errorCopy.message}
        onRetry={() => loadEngagement()}
      />
    )
  }

  const generatedAt = formatAdminTimestamp(engagement?.generated_at, locale)
  const refreshedAt = formatAdminTimestamp(lastRefreshedAt, locale)
  const analyticsEvents = engagement?.analytics_events
  const shareEvents = engagement?.share_events
  const analyticsAvailable = sourceIsAvailable(analyticsEvents)
  const sharesAvailable = sourceIsAvailable(shareEvents)
  const daily = analyticsAvailable && Array.isArray(analyticsEvents.daily)
    ? analyticsEvents.daily
    : []
  const platforms = analyticsAvailable && Array.isArray(analyticsEvents.platform_breakdown)
    ? analyticsEvents.platform_breakdown
    : []
  const outcomes = sharesAvailable && Array.isArray(shareEvents.outcome_breakdown)
    ? shareEvents.outcome_breakdown
    : []

  const platformItems = platforms.map((row) => ({
    key: row.platform,
    label: t(`admin.engagementPlatforms.${row.platform}`, row.platform),
    value: row.total_events,
  }))
  const outcomeItems = outcomes.map((row) => ({
    key: row.outcome,
    label: t(`admin.engagementOutcomes.${row.outcome}`, row.outcome),
    value: row.event_count,
  }))

  return (
    <div className="admin-monitoring admin-engagement" aria-busy={isRefreshing || isLoading}>
      <DashboardToolbar
        disabled={isRefreshing || isLoading}
        isRefreshing={isRefreshing}
        onRefresh={() => loadEngagement({ background: true })}
        refreshLabel={t('admin.engagementRefresh')}
        refreshingLabel={t('admin.monitoringRefreshing')}
      >
        <fieldset className="admin-engagement-range">
          <legend>{t('admin.engagementRange')}</legend>
          <div>
            {WINDOW_OPTIONS.map((days) => (
              <button
                className={windowDays === days ? 'active' : ''}
                type="button"
                key={days}
                onClick={() => setWindowDays(days)}
                aria-pressed={windowDays === days}
              >
                {t('admin.engagementDays', { count: days })}
              </button>
            ))}
          </div>
        </fieldset>
        <p className="admin-monitoring-window">
          {t('admin.engagementWindow', {
            count: engagement?.window_days ?? windowDays,
          })}
        </p>
        <div className="admin-monitoring-timestamps">
          {generatedAt
            ? <span>{t('admin.engagementGeneratedAt', { value: generatedAt })}</span>
            : null}
          {refreshedAt
            ? <span>{t('admin.monitoringRefreshedAt', { value: refreshedAt })}</span>
            : null}
        </div>
      </DashboardToolbar>

      {errorKey ? (
        <DashboardRefreshError
          onRetry={() => loadEngagement({ background: true })}
          retryLabel={t('admin.retry')}
        >
          {errorCopy.message}
        </DashboardRefreshError>
      ) : null}

      <DashboardStatus
        isOk={engagement?.status === 'ok'}
        okLabel={t('admin.engagementStatusOk')}
        partialLabel={t('admin.engagementStatusPartial')}
      />

      <div className="admin-monitoring-grid admin-engagement-summary">
        <MetricCard
          description={t('admin.engagementMetricDescriptions.eventVolume')}
          label={t('admin.engagementMetrics.appOpens')}
          locale={locale}
          unavailableLabel={t('admin.monitoringUnavailable')}
          value={analyticsAvailable ? analyticsEvents.app_opens : null}
        />
        <MetricCard
          description={t('admin.engagementMetricDescriptions.eventVolume')}
          label={t('admin.engagementMetrics.screenViews')}
          locale={locale}
          unavailableLabel={t('admin.monitoringUnavailable')}
          value={analyticsAvailable ? analyticsEvents.screen_views : null}
        />
        <MetricCard
          description={t('admin.engagementMetricDescriptions.shareActions')}
          label={t('admin.engagementMetrics.shareTotals')}
          locale={locale}
          unavailableLabel={t('admin.monitoringUnavailable')}
          value={sharesAvailable ? shareEvents.total_actions : null}
        />
        <MetricCard
          description={t('admin.engagementMetricDescriptions.shareSuccess')}
          format="rate"
          label={t('admin.engagementMetrics.shareSuccessRate')}
          locale={locale}
          unavailableLabel={t('admin.monitoringUnavailable')}
          value={sharesAvailable ? shareEvents.success_rate : null}
        />
      </div>

      <div className="admin-monitoring-sections">
        <DashboardSection
          description={t('admin.engagementActivityDescription')}
          icon={Activity}
          id="admin-engagement-activity"
          title={t('admin.engagementActivity')}
        >
          {!analyticsAvailable ? (
            <SectionNotice variant="unavailable">
              {t('admin.engagementAnalyticsUnavailable')}
            </SectionNotice>
          ) : daily.length === 0 ? (
            <SectionNotice>{t('admin.engagementNoAnalytics')}</SectionNotice>
          ) : (
            <>
              <DailyActivityChart
                ariaLabel={t('admin.engagementTrendAria')}
                appOpensLabel={t('admin.engagementMetrics.appOpens')}
                rows={daily}
                screenViewsLabel={t('admin.engagementMetrics.screenViews')}
              />
              <EngagementTable
                caption={t('admin.engagementDailyTable')}
                columns={[
                  {
                    key: 'event_day',
                    label: t('admin.engagementTable.date'),
                    render: (row) => row.event_day,
                  },
                  {
                    key: 'app_opens',
                    label: t('admin.engagementMetrics.appOpens'),
                    render: (row) => formatAdminNumber(row.app_opens, locale),
                  },
                  {
                    key: 'screen_views',
                    label: t('admin.engagementMetrics.screenViews'),
                    render: (row) => formatAdminNumber(row.screen_views, locale),
                  },
                ]}
                rows={daily}
                rowKey={(row) => row.event_day}
              />
            </>
          )}
        </DashboardSection>

        <DashboardSection
          description={t('admin.engagementPlatformDescription')}
          icon={BarChart3}
          id="admin-engagement-platforms"
          title={t('admin.engagementPlatform')}
        >
          {!analyticsAvailable ? (
            <SectionNotice variant="unavailable">
              {t('admin.engagementAnalyticsUnavailable')}
            </SectionNotice>
          ) : (
            <>
              <CountBars
                ariaLabel={t('admin.engagementPlatformAria')}
                items={platformItems}
                locale={locale}
              />
              <EngagementTable
                caption={t('admin.engagementPlatformTable')}
                columns={[
                  {
                    key: 'platform',
                    label: t('admin.engagementTable.platform'),
                    render: (row) => t(
                      `admin.engagementPlatforms.${row.platform}`,
                      row.platform,
                    ),
                  },
                  {
                    key: 'app_opens',
                    label: t('admin.engagementMetrics.appOpens'),
                    render: (row) => formatAdminNumber(row.app_opens, locale),
                  },
                  {
                    key: 'screen_views',
                    label: t('admin.engagementMetrics.screenViews'),
                    render: (row) => formatAdminNumber(row.screen_views, locale),
                  },
                  {
                    key: 'total_events',
                    label: t('admin.engagementTable.total'),
                    render: (row) => formatAdminNumber(row.total_events, locale),
                  },
                ]}
                rows={platforms}
                rowKey={(row) => row.platform}
              />
            </>
          )}
        </DashboardSection>

        <DashboardSection
          description={t('admin.engagementSharingDescription')}
          icon={Share2}
          id="admin-engagement-sharing"
          title={t('admin.engagementSharing')}
        >
          {!sharesAvailable ? (
            <SectionNotice variant="unavailable">
              {t('admin.engagementSharesUnavailable')}
            </SectionNotice>
          ) : outcomes.length === 0 ? (
            <SectionNotice>{t('admin.engagementNoShares')}</SectionNotice>
          ) : (
            <>
              <CountBars
                ariaLabel={t('admin.engagementShareOutcomeAria')}
                items={outcomeItems}
                locale={locale}
              />
              <EngagementTable
                caption={t('admin.engagementShareTable')}
                columns={[
                  {
                    key: 'outcome',
                    label: t('admin.engagementTable.outcome'),
                    render: (row) => t(
                      `admin.engagementOutcomes.${row.outcome}`,
                      row.outcome,
                    ),
                  },
                  {
                    key: 'event_count',
                    label: t('admin.engagementTable.total'),
                    render: (row) => formatAdminNumber(row.event_count, locale),
                  },
                ]}
                rows={outcomes}
                rowKey={(row) => row.outcome}
              />
            </>
          )}
        </DashboardSection>
      </div>
    </div>
  )
}

export default AdminEngagement
