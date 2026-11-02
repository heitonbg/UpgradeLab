import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

let openModals = 0
let originalOverflow = ''

export function Modal({ open, onClose, title, children, size = 'md' }) {
  const titleId = useId()
  const dialog = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement
    if (openModals++ === 0) { originalOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden' }
    dialog.current?.focus()
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close.current(); return }
      if (e.key !== 'Tab') return
      const elements = [...dialog.current.querySelectorAll('button, a[href], input, select, textarea, summary, [tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length)
      const first = elements[0], last = elements[elements.length - 1]
      if (!first) { e.preventDefault(); return }
      if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { e.preventDefault(); first.focus() }
    }
    const node = dialog.current
    node.addEventListener('keydown', onKey)
    return () => {
      node.removeEventListener('keydown', onKey)
      if (--openModals === 0) document.body.style.overflow = originalOverflow
      if (previous?.isConnected) previous.focus()
    }
  }, [open])

  if (!open) return null

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    wide: 'modal-wide',
  }

  return createPortal(
    <div
      className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`modal-dialog w-full ${sizeClasses[size] || sizeClasses.md} bg-card border border-border rounded-lg p-6 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between mb-4">
          <h3 id={titleId} className="text-lg font-medium text-accent">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Закрыть окно" className="text-gray-400 hover:text-white text-xl leading-none">×</button>
        </div>
        {children}
      </div>
    </div>, document.body
  )
}
