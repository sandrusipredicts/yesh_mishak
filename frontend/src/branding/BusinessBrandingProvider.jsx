import { useCallback, useEffect, useMemo, useState } from 'react'

import { getBusinessBranding } from '../api/businessBranding'
import { getRuntimeBrandName, setRuntimeBrandName } from '../i18n'
import { BusinessBrandingContext } from './businessBrandingContext'
import { normalizeBusinessName } from './runtimeBranding'

export default function BusinessBrandingProvider({ children }) {
  const [businessName, setBusinessName] = useState(() => normalizeBusinessName(getRuntimeBrandName()))
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const applyBusinessName = useCallback((nextBusinessName) => {
    const normalized = normalizeBusinessName(nextBusinessName)
    setBusinessName(normalized)
    setRuntimeBrandName(normalized)
    return normalized
  }, [])

  const refreshBusinessName = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await getBusinessBranding()
      applyBusinessName(response?.business_name)
      setLoadError('')
      return response
    } catch (error) {
      setLoadError(error?.message || 'Failed to load business branding')
      throw error
    } finally {
      setIsLoading(false)
    }
  }, [applyBusinessName])

  useEffect(() => {
    let isMounted = true

    queueMicrotask(async () => {
      try {
        const response = await getBusinessBranding()
        if (isMounted) {
          applyBusinessName(response?.business_name)
          setLoadError('')
        }
      } catch (error) {
        if (isMounted) {
          setLoadError(error?.message || 'Failed to load business branding')
          applyBusinessName(getRuntimeBrandName())
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    })

    return () => {
      isMounted = false
    }
  }, [applyBusinessName])

  const value = useMemo(
    () => ({
      businessName,
      isLoading,
      loadError,
      applyBusinessName,
      refreshBusinessName,
    }),
    [applyBusinessName, businessName, isLoading, loadError, refreshBusinessName],
  )

  return (
    <BusinessBrandingContext.Provider value={value}>
      {children}
    </BusinessBrandingContext.Provider>
  )
}
