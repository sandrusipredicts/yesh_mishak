import { useCallback, useEffect, useRef, useState } from 'react'

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

export function formatAdminNumber(value, locale, fractionDigits = 0) {
  if (
    value === null
    || value === undefined
    || typeof value !== 'number'
    || !Number.isFinite(value)
  ) {
    return null
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(value)
}

export function formatAdminRate(value, locale) {
  const formatted = formatAdminNumber(
    typeof value === 'number' ? value * 100 : null,
    locale,
    1,
  )
  return formatted === null ? null : `${formatted}%`
}

export function formatAdminTimestamp(value, locale) {
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

export function sourceIsAvailable(group) {
  return Boolean(group) && group.source_available === true
}

export function useAdminDashboardResource(loadData) {
  const [data, setData] = useState(null)
  const [errorKey, setErrorKey] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const requestRef = useRef(null)
  const nextRequestIdRef = useRef(0)

  const load = useCallback(async ({ background = false } = {}) => {
    if (requestRef.current) {
      return
    }

    const requestId = nextRequestIdRef.current + 1
    nextRequestIdRef.current = requestId
    const controller = new AbortController()
    requestRef.current = { controller, requestId }

    if (background) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }
    setErrorKey('')

    try {
      const result = await loadData({ signal: controller.signal })

      if (requestRef.current?.requestId !== requestId) {
        return
      }

      setData(result)
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
  }, [loadData])

  useEffect(() => {
    const initialLoadId = window.setTimeout(() => {
      load()
    }, 0)

    return () => {
      window.clearTimeout(initialLoadId)
      requestRef.current?.controller.abort()
      requestRef.current = null
    }
  }, [load])

  return {
    data,
    errorKey,
    isLoading,
    isRefreshing,
    lastRefreshedAt,
    load,
  }
}

export function getAdminDashboardErrorCopy(errorKey, t, namespace) {
  return {
    message: t(`${namespace}.${errorKey || ERROR_KEYS.unavailable}`),
    actionLabel: errorKey === ERROR_KEYS.unauthorized
      ? t('admin.monitoringSignInAgain')
      : t('admin.retry'),
  }
}

export function isUnauthorizedAdminDashboardError(errorKey) {
  return errorKey === ERROR_KEYS.unauthorized
}
