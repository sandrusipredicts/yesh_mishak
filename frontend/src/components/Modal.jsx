import { useEffect } from 'react'
import { useBodyScrollLock } from '../hooks/useBodyScrollLock'

export function Modal({
  isOpen = true,
  onClose,
  ariaLabelledBy,
  className = '',
  isConfirm = false,
  children,
}) {
  useBodyScrollLock(isOpen)

  useEffect(() => {
    if (!isOpen) return

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose?.()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const backdropClass = isConfirm ? 'confirm-modal-backdrop' : 'modal-backdrop'
  const containerClass = isConfirm ? 'confirm-modal' : className

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose?.()
    }
  }

  return (
    <div className={backdropClass} role="presentation" onClick={handleBackdropClick}>
      <section
        className={containerClass}
        role={isConfirm ? 'alertdialog' : 'dialog'}
        aria-modal="true"
        aria-labelledby={ariaLabelledBy}
      >
        {!isConfirm && onClose && (
          <div className="modal-sticky-close">
            <button className="modal-close-button" type="button" onClick={onClose} aria-label="Close">
              x
            </button>
          </div>
        )}
        {children}
      </section>
    </div>
  )
}

export default Modal
