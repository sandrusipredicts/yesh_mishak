export const FOREGROUND_PUSH_REFRESH_RETRY_MS = 750

export function createNotificationSync({
  loadNotifications,
  loadUnreadCount,
  onNotifications,
  onUnreadCount,
  onError,
  retryDelayMs = FOREGROUND_PUSH_REFRESH_RETRY_MS,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout,
} = {}) {
  let generation = 0
  let retryId = null
  let disposed = false

  function clearRetry() {
    if (retryId !== null) {
      clearTimeoutFn(retryId)
      retryId = null
    }
  }

  async function refresh() {
    const requestGeneration = generation + 1
    generation = requestGeneration

    try {
      const [notifications, unreadCountResult] = await Promise.all([
        loadNotifications(),
        loadUnreadCount(),
      ])

      if (disposed || requestGeneration !== generation) {
        return { applied: false }
      }

      onNotifications(Array.isArray(notifications) ? notifications : [])
      onUnreadCount(Number(unreadCountResult?.unread_count ?? 0))
      return { applied: true }
    } catch (error) {
      if (!disposed && requestGeneration === generation) {
        onError?.(error)
      }
      return { applied: false, error }
    }
  }

  function handleForegroundPush() {
    clearRetry()
    void refresh()

    retryId = setTimeoutFn(() => {
      retryId = null
      void refresh()
    }, retryDelayMs)
  }

  function dispose() {
    disposed = true
    generation += 1
    clearRetry()
  }

  return {
    refresh,
    handleForegroundPush,
    dispose,
  }
}
