import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { getBusinessBranding } from '../api/businessBranding'
import { getRuntimeBrandName, setRuntimeBrandName } from '../i18n'
import { normalizeBusinessName } from './runtimeBranding'

const BusinessBrandingContext = createContext(null)

export function BusinessBrandingProvider({ children }) {
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
    setLoadError('')
    try {
      const response = await getBusinessBranding()
      applyBusinessName(response?.business_name)
      return response
    } catch (error) {
      setLoadError(error?.message || 'Failed to load business branding')
      throw error
    }
  }, [applyBusinessName])

  useEffect(() => {
    let isMounted = true

    refreshBusinessName()
      .catch(() => {
        if (isMounted) {
          applyBusinessName(getRuntimeBrandName())
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [applyBusinessName, refreshBusinessName])

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

export function useBusinessBranding() {
  const context = useContext(BusinessBrandingContext)
  if (!context) {
    throw new Error('useBusinessBranding must be used inside BusinessBrandingProvider')
  }
  return context
}
