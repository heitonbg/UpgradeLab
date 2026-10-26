import { useState } from 'react'

export function AutoDetectButton({ onDetect }) {
  const [detecting, setDetecting] = useState(false)
  const [message, setMessage] = useState('')

  async function detect() {
    setDetecting(true)
    setMessage('')
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl')
      const extension = gl?.getExtension('WEBGL_debug_renderer_info')
      const renderer = extension && gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)
      if (!renderer) { setMessage('Браузер не открыл модель видеокарты. Выберите её из списка.'); return }
      const response = await fetch('/api/detect-gpu', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ renderer_string: renderer }) })
      if (!response.ok) throw new Error('Сервер не ответил')
      const data = await response.json()
      if (data.gpu_id) { onDetect(null, data.gpu_id); setMessage(`Похоже на ${data.gpu_name}. Проверьте выбор видеокарты и укажите процессор.`) }
      else setMessage('Модель видеокарты не найдена в каталоге. Выберите её вручную.')
    } catch { setMessage('Автоопределение недоступно. Выберите комплектующие вручную.') }
    finally { setDetecting(false) }
  }

  return <div className="browser-detect"><button type="button" onClick={detect} disabled={detecting}>{detecting ? 'Определяем GPU…' : 'Определить GPU через браузер'}</button>{message && <p role="status">{message}</p>}</div>
}
