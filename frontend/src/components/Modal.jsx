import { useEffect, useRef } from 'react'
import { useBodyScrollLock } from '../hooks/useBodyScrollLock'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({
  isOpen = true,
  onClose,
  ariaLabelledBy,
  className = '',
  isConfirm = false,
  children,
}) {
  const dialogRef = useRef(null)
  const previousFocusRef = useRef(null)

  useBodyScrollLock(isOpen)

  useEffect(() => {
    if (!isOpen) return

    previousFocusRef.current = document.activeElement

    const timer = window.setTimeout(() => {
      const dialog = dialogRef.current
      if (!dialog) return
      const first = dialog.querySelector(FOCUSABLE_SELECTOR)
      if (first) {
        first.focus()
      } else {
        dialog.focus()
      }
    }, 0)

    return () => {
      window.clearTimeout(timer)
      previousFocusRef.current?.focus()
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose?.()
        return
      }

      if (event.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return

      const focusable = [...dialog.querySelectorAll(FOCUSABLE_SELECTOR)]
      if (focusable.length === 0) {
        event.preventDefault()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
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
        ref={dialogRef}
        className={containerClass}
        role={isConfirm ? 'alertdialog' : 'dialog'}
        aria-modal="true"
        aria-labelledby={ariaLabelledBy}
        tabIndex={-1}
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
