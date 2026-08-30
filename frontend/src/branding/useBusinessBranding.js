import { useContext } from 'react'

import { BusinessBrandingContext } from './businessBrandingContext'

export default function useBusinessBranding() {
  const context = useContext(BusinessBrandingContext)
  if (!context) {
    throw new Error('useBusinessBranding must be used inside BusinessBrandingProvider')
  }
  return context
}
