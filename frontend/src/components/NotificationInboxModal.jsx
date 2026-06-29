import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import Modal from './Modal'

import { markAllNotificationsRead, markNotificationRead } from '../api/notifications'

function isNotificationUnread(notification) {
  // Supports both schemas until the read_at migration runs: a notification is
  // read if read_at is set OR the legacy is_read flag is true.
  if (notification.read_at) {
    return false
  }
  if (notification.is_read === true) {
    return false
  }
  return true
}

function formatNotificationTime(value, locale) {
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

function NotificationInboxModal({
  notifications = [],
  onClose,
  onNotificationsChange,
  onRefreshNotifications,
  onRefreshUnreadCount,
  onUnreadCountChange,
  onOpenTarget,
}) {
  const { i18n, t } = useTranslation()
  const [error, setError] = useState('')
  const [readingNotificationId, setReadingNotificationId] = useState('')
  const [isMarkingAllRead, setIsMarkingAllRead] = useState(false)
  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'

  const unreadCount = useMemo(
    () => notifications.filter(isNotificationUnread).length,
    [notifications],
  )

  async function handleMarkRead(notification) {
    if (!isNotificationUnread(notification) || readingNotificationId) {
      return notification
    }

    setError('')
    setReadingNotificationId(notification.id)

    try {
      const updatedNotification = await markNotificationRead(notification.id)
      const nextNotifications = notifications.map((currentNotification) =>
        currentNotification.id === notification.id
          ? { ...currentNotification, ...updatedNotification }
          : currentNotification,
      )
      onNotificationsChange?.(nextNotifications)
      onUnreadCountChange?.(nextNotifications.filter(isNotificationUnread).length)
      await onRefreshUnreadCount?.()
      return { ...notification, ...updatedNotification }
    } catch {
      setError(t('notifications.markReadFailed'))
      return notification
    } finally {
      setReadingNotificationId('')
    }
  }

  async function handleNotificationClick(notification) {
    const nextNotification = await handleMarkRead(notification)
    onOpenTarget?.(nextNotification)
  }

  async function handleMarkAllRead() {
    setError('')
    setIsMarkingAllRead(true)

    try {
      await markAllNotificationsRead()
      const readAt = new Date().toISOString()
      const nextNotifications = notifications.map((notification) => ({
        ...notification,
        read_at: notification.read_at ?? readAt,
      }))
      onNotificationsChange?.(nextNotifications)
      onUnreadCountChange?.(0)
      await onRefreshNotifications?.()
      await onRefreshUnreadCount?.()
    } catch {
      setError(t('notifications.markAllFailed'))
    } finally {
      setIsMarkingAllRead(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      className="notifications-modal"
      ariaLabelledBy="notification-inbox-title"
    >
      <h2 id="notification-inbox-title">{t('notifications.inboxTitle')}</h2>

        <section className="notifications-list-section">
          <div className="notifications-list-header">
            <p>{unreadCount ? t('notifications.unreadCount', { count: unreadCount }) : t('notifications.noUnread')}</p>
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={!unreadCount || isMarkingAllRead}
            >
              {isMarkingAllRead ? t('notifications.marking') : t('notifications.markAllRead')}
            </button>
          </div>

          {error ? <p className="modal-error" role="alert">{error}</p> : null}

          <div className="notifications-list">
            {notifications.length ? (
              notifications.map((notification) => {
                const isUnread = isNotificationUnread(notification)
                const createdTime = formatNotificationTime(notification.created_at, locale)

                return (
                  <article
                    className={`notification-list-item${isUnread ? ' unread' : ''}`}
                    key={notification.id}
                  >
                    <button
                      type="button"
                      onClick={() => handleNotificationClick(notification)}
                      disabled={readingNotificationId === notification.id}
                    >
                      <span>{notification.title}</span>
                      <small>{notification.body}</small>
                      {createdTime ? <time dateTime={notification.created_at}>{createdTime}</time> : null}
                      <strong>{isUnread ? t('notifications.unread') : t('notifications.read')}</strong>
                    </button>
                    {isUnread ? (
                      <button
                        className="notification-mark-read-button"
                        type="button"
                        onClick={() => handleMarkRead(notification)}
                        disabled={readingNotificationId === notification.id}
                      >
                        {t('notifications.markAsRead')}
                      </button>
                    ) : null}
                  </article>
                )
              })
            ) : (
              <p className="notifications-empty">{t('notifications.empty')}</p>
            )}
          </div>
        </section>
    </Modal>
  )
}

export default NotificationInboxModal
