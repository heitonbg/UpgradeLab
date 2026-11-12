import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

let openModals = 0
let originalOverflow = ''

export function Modal({ open, onClose, title, children, size = 'md' }) {
  const titleId = useId()
  const dialog = useRef(null)
  const keyboard = useRef(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement
    if (openModals++ === 0) { originalOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden' }
    const covered=[...document.querySelectorAll('.modal-dialog')].filter(node=>node!==dialog.current).map(node=>({node,inert:node.inert,hidden:node.getAttribute('aria-hidden')}))
    covered.forEach(({node})=>{node.inert=true;node.setAttribute('aria-hidden','true')})
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
    keyboard.current = onKey
    return () => {
      keyboard.current = null
      covered.forEach(({node,inert,hidden})=>{node.inert=inert;if(hidden===null)node.removeAttribute('aria-hidden');else node.setAttribute('aria-hidden',hidden)})
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
    <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}>
      <div ref={dialog} onKeyDown={e=>keyboard.current?.(e)} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`modal-dialog ${sizeClasses[size]||sizeClasses.md} ${size==='wide'?'modal-wide':''} ${size==='lg'?'modal-editor':''}`}>
        <header className="modal-heading"><h3 id={titleId}>{title}</h3><button type="button" onClick={onClose} aria-label="Закрыть окно" className="modal-close">×</button></header>
        <div className="modal-content">{children}</div>
      </div>
    </div>,document.body
  )
}
