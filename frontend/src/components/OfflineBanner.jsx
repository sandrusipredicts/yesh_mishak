import { WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useOnlineStatus } from '../hooks/useOnlineStatus'

function OfflineBanner() {
  const { t } = useTranslation()
  const isOnline = useOnlineStatus()

  if (isOnline) {
    return null
  }

  return (
    <div className="offline-banner" role="status" aria-live="polite">
      <WifiOff aria-hidden="true" size={18} />
      <span>{t('app.offlineMessage')}</span>
    </div>
  )
}

export default OfflineBanner
