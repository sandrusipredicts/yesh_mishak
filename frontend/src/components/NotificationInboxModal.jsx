import { useMemo, useState } from 'react'

import { markAllNotificationsRead, markNotificationRead } from '../api/notifications'

function isNotificationUnread(notification) {
  return !notification.read_at
}

function formatNotificationTime(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function NotificationInboxModal({
  notifications = [],
  onClose,
  onNotificationsChange,
  onRefreshNotifications,
  onUnreadCountChange,
  onOpenTarget,
}) {
  const [error, setError] = useState('')
  const [readingNotificationId, setReadingNotificationId] = useState('')
  const [isMarkingAllRead, setIsMarkingAllRead] = useState(false)

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
      return { ...notification, ...updatedNotification }
    } catch {
      setError('Could not mark notification as read.')
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
    } catch {
      setError('Could not mark notifications as read.')
    } finally {
      setIsMarkingAllRead(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="notifications-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-inbox-title"
      >
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
          x
        </button>

        <h2 id="notification-inbox-title">Notifications</h2>

        <section className="notifications-list-section">
          <div className="notifications-list-header">
            <p>{unreadCount ? `${unreadCount} unread` : 'No unread notifications'}</p>
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={!unreadCount || isMarkingAllRead}
            >
              {isMarkingAllRead ? 'Marking...' : 'Mark all as read'}
            </button>
          </div>

          {error ? <p className="modal-error">{error}</p> : null}

          <div className="notifications-list">
            {notifications.length ? (
              notifications.map((notification) => {
                const isUnread = isNotificationUnread(notification)
                const createdTime = formatNotificationTime(notification.created_at)

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
                      <strong>{isUnread ? 'Unread' : 'Read'}</strong>
                    </button>
                    {isUnread ? (
                      <button
                        className="notification-mark-read-button"
                        type="button"
                        onClick={() => handleMarkRead(notification)}
                        disabled={readingNotificationId === notification.id}
                      >
                        Mark as read
                      </button>
                    ) : null}
                  </article>
                )
              })
            ) : (
              <p className="notifications-empty">No notifications yet.</p>
            )}
          </div>
        </section>
      </section>
    </div>
  )
}

export default NotificationInboxModal
