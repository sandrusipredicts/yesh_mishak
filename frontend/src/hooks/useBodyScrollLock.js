import { useEffect } from 'react'

export function useBodyScrollLock(isActive = true) {
  useEffect(() => {
    if (!isActive) return

    const activeModals = Number(document.body.getAttribute('data-active-modals') || '0')
    document.body.setAttribute('data-active-modals', String(activeModals + 1))
    document.body.style.overflow = 'hidden'

    return () => {
      const currentActive = Number(document.body.getAttribute('data-active-modals') || '0')
      const newActive = Math.max(0, currentActive - 1)
      if (newActive === 0) {
        document.body.removeAttribute('data-active-modals')
        document.body.style.overflow = ''
      } else {
        document.body.setAttribute('data-active-modals', String(newActive))
      }
    }
  }, [isActive])
}
