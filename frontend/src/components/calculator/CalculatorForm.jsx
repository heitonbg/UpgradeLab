import { useRef, useState } from 'react'
import { Button } from '../ui/Button'
import { HardwareSearch } from '../ui/HardwareSearch'
import { Modal } from '../ui/Modal'
import { GAMES, MODES } from '../../constants/game'
import { AutoDetectButton } from '../AutoDetectButton'
import { matchHardware, parseSystemReport } from '../../lib/hardware'

export function CalculatorForm({ cpus, gpus, onSubmit, loading }) {
  const [cpuId, setCpuId] = useState(null)
  const [gpuId, setGpuId] = useState(null)
  const [memory, setMemory] = useState({ capacity_gb: '', type: '', channels: '' })
  const [game, setGame] = useState(GAMES[0].value)
  const [mode, setMode] = useState(MODES[0].value)
  const [budget, setBudget] = useState('')
  const [aiMode, setAiMode] = useState('off')
  const [sellMode, setSellMode] = useState('budget_only')
  const [pasteOpen, setPasteOpen] = useState(false)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [importInfo, setImportInfo] = useState('')
  const fileInput = useRef(null)

  function importReport(raw) {
    try {
      const report = parseSystemReport(raw)
      const cpu = report.cpus.map(c=>matchHardware(cpus, c.name)).find(Boolean)
      const gpu = report.gpus.map(g=>matchHardware(gpus, g.name)).find(Boolean)
      // Clear prior values: an unrecognized model must not leave an old choice.
      setCpuId(cpu?.id ?? null)
      setGpuId(gpu?.id ?? null)
      const mem = report.memory || {}
      const capacity = Number(mem.capacity_gb)
      setMemory({ capacity_gb: Number.isFinite(capacity) && capacity >= 2 && capacity <= 512 ? capacity : '', type: ['DDR3','DDR4','DDR5'].includes(mem.type) ? mem.type : '', channels: [1,2].includes(Number(mem.channels)) ? Number(mem.channels) : '' })
      const parts = [cpu ? `CPU: ${cpu.name}` : `CPU: ${report.cpus[0]?.name || 'не определён'} — выберите модель`, gpu ? `GPU: ${gpu.name}` : `GPU: ${report.gpus.map(g=>g.name).join(', ') || 'не определён'} — выберите модель`]
      if (capacity >= 2) parts.push(`RAM: ${capacity} ГБ${mem.type ? ` ${mem.type}` : ''}. Канальный режим проверьте самостоятельно.`)
      setImportInfo(parts.join('\n'))
      setError('');setPasteOpen(false);setText('')
    } catch (e) { setError(e.message || 'Не удалось прочитать отчёт.') }
  }

  async function importFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    if (file.size > 100000) { setError('Слишком большой файл. Выберите отчёт UpgradeLab до 100 КБ.'); return }
    try { importReport(await file.text()) } catch { setError('Не удалось прочитать файл.') }
    event.target.value = ''
  }

  function submit(event) {
    event.preventDefault()
    if (!cpuId || !gpuId || loading) return
    onSubmit({ cpuId, gpuId, ramId: null, ramManual: memory.capacity_gb ? { capacity_gb: Number(memory.capacity_gb), type: memory.type || null, channels: memory.channels ? Number(memory.channels) : null } : null, game, mode, budget: budget === '' ? null : Number(budget), aiMode, sellMode })
  }

  return <div className="configuration-panel">
    <div className="detect-panel"><div><h3>Заполнить из данных компьютера</h3><p>Windows-скрипт прочитает модели CPU, GPU и установленную память. Запустите его, затем загрузите полученный JSON-файл.</p></div><div className="detect-actions"><a href="/scripts/run.bat" download="UpgradeLab-detect.bat" className="secondary-btn">Скачать скрипт</a><button type="button" className="secondary-btn" onClick={()=>fileInput.current?.click()}>Загрузить отчёт</button><button type="button" className="text-btn" onClick={()=>{setError('');setPasteOpen(true)}}>Вставить текст</button></div><input ref={fileInput} type="file" accept=".json,.txt,application/json" hidden onChange={importFile}/></div>
    {importInfo && <p className="import-summary" role="status">{importInfo}</p>}
    {error && !pasteOpen && <p className="error" role="alert">{error}</p>}
    <form onSubmit={submit} className="configuration-form">
      <fieldset><legend>Комплектующие</legend><p className="field-hint">Начните вводить модель: например, fx6100, rtx3060 или i5 12400f.</p><div className="form-grid"><HardwareSearch label="Процессор" items={cpus} value={cpuId} onChange={setCpuId} placeholder="Найти процессор"/><HardwareSearch label="Видеокарта" items={gpus} value={gpuId} onChange={setGpuId} placeholder="Найти видеокарту"/></div><AutoDetectButton onDetect={(_, id)=>setGpuId(id)}/></fieldset>
      <fieldset><legend>Оперативная память</legend><p className="field-hint">Укажите параметры памяти. Неизвестные значения можно оставить пустыми.</p><div className="form-grid three-columns"><label>Общий объём, ГБ<input type="number" min="2" max="512" step="1" placeholder="Например, 8" value={memory.capacity_gb} onChange={e=>setMemory({...memory,capacity_gb:e.target.value})}/></label><label>Тип памяти<select value={memory.type} onChange={e=>setMemory({...memory,type:e.target.value})}><option value="">Неизвестен</option>{['DDR3','DDR4','DDR5'].map(t=><option key={t}>{t}</option>)}</select></label><label>Канальный режим<select value={memory.channels} onChange={e=>setMemory({...memory,channels:e.target.value})}><option value="">Неизвестен</option><option value="1">Один канал</option><option value="2">Два канала</option></select></label></div></fieldset>
      <fieldset><legend>Сценарий и бюджет</legend><div className="form-grid"><label>Игра<select value={game} onChange={e=>setGame(e.target.value)}>{GAMES.map(g=><option key={g.value} value={g.value}>{g.label}</option>)}</select></label><label>Разрешение и графика<select value={mode} onChange={e=>setMode(e.target.value)}>{MODES.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}</select></label><label>Бюджет на апгрейд, ₽<input type="number" min="0" max="10000000" step="100" placeholder="Без ограничения" value={budget} onChange={e=>setBudget(e.target.value)}/></label><label>Использование нейросетей<select value={aiMode} onChange={e=>setAiMode(e.target.value)}><option value="off">Не планирую</option><option value="light">Генерация изображений, небольшие LLM</option><option value="heavy">SDXL, крупные модели</option></select></label></div><label className="checkbox-label"><input type="checkbox" checked={sellMode==='budget_plus_sell'} onChange={e=>setSellMode(e.target.checked?'budget_plus_sell':'budget_only')}/><span>Добавить к бюджету цену продажи старого компонента<small>При наличии свежей цены на вторичном рынке.</small></span></label></fieldset>
      <div className="form-submit"><p>Выберите CPU и GPU из найденных моделей.</p><Button type="submit" disabled={!cpuId || !gpuId || loading}>{loading ? 'Рассчитываем…' : 'Рассчитать производительность'}</Button></div>
    </form>
    <Modal open={pasteOpen} onClose={()=>setPasteOpen(false)} title="Импорт конфигурации"><p className="field-hint">Вставьте JSON нового скрипта или текстовый отчёт предыдущей версии.</p><textarea className="report-input" rows="10" value={text} onChange={e=>setText(e.target.value)} placeholder={'{"cpus": [{"name": "AMD FX-6100"}], ...}'}/>{error && <p className="error" role="alert">{error}</p>}<div className="detect-actions"><Button disabled={!text.trim()} onClick={()=>importReport(text)}>Заполнить конфигурацию</Button><Button variant="secondary" onClick={()=>setPasteOpen(false)}>Отмена</Button></div></Modal>
  </div>
}
