import { publicSourceIds } from '../../lib/publicSources'
import { Select } from '../ui/Select'
import { GeoControls } from '../GeoControls'
import { useRef, useState } from 'react'
import { Button } from '../ui/Button'
import { HardwareSearch } from '../ui/HardwareSearch'
import { Modal } from '../ui/Modal'
import { GamePicker } from './GamePicker'
import { GAMES, MODES } from '../../constants/game'
import { AutoDetectButton } from '../AutoDetectButton'
import { matchHardware, parseSystemReport } from '../../lib/hardware'
import { PriceSources } from '../StoreOffers'
import { useStepFlow, StepNavigation, StepHeading, StepFooter, ReviewSummary } from '../ui/StepFlow'
import { Icon } from '../ui/Icon'

const STEPS = [
  {title:'Ваш ПК',short:'CPU, GPU и память',heading:'Что уже установлено?',description:'Выберите процессор и видеокарту. Параметры памяти можно уточнить позже.'},
  {title:'Задача',short:'Игра и цель',heading:'Какого результата хотите?',description:'Укажите игру, графику и желаемый FPS. Бюджет можно оставить без ограничения.'},
  {title:'Источники',short:'Цены и площадки',heading:'Откуда брать предложения?',description:'Выберите площадки, на которых готовы покупать комплектующие.'},
  {title:'Проверка',short:'Перед расчётом',heading:'Посмотрим, что ограничивает ваш ПК',description:'Проверим конфигурацию и найдём подходящие варианты апгрейда.'},
]

export function CalculatorForm({ cpus, gpus, onSubmit, loading, onExit, active = true }) {
  const flow = useStepFlow(STEPS.length, active)
  const [cpuId, setCpuId] = useState(null)
  const [gpuId, setGpuId] = useState(null)
  const [game, setGame] = useState(GAMES[0].value)
  const [mode, setMode] = useState(MODES[0].value)
  const [budget, setBudget] = useState('')
  const [geo,setGeo]=useState({city_id:null,geo_mode:'all',max_price:null})
  const [priceSources,setPriceSources] = useState(['regard','upgradelab'])
  const [targetFps, setTargetFps] = useState(60)
  const [aiMode, setAiMode] = useState('off')
  const [pasteOpen, setPasteOpen] = useState(false)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [importInfo, setImportInfo] = useState('')
  const fileInput = useRef(null)
  const [lastCalculation,setLastCalculation]=useState('')
  const calculationKey=JSON.stringify([cpuId,gpuId,game,mode,budget,geo,priceSources,targetFps,aiMode])

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

  async function submit(event) {
    event.preventDefault()
    if(loading)return
    if(flow.step===STEPS.length-1&&lastCalculation===calculationKey)return
    if(flow.step<STEPS.length-1){navigate(flow.step+1);return}
    if(!flow.validateAll())return
    if (!cpuId || !gpuId) { flow.go(0);setError('Выберите процессор и видеокарту из списка найденных моделей.');return }
    if(priceSources?.length===0){setError('Выберите хотя бы одну площадку.');return}
    const completed=await onSubmit({ geo, cpuId, gpuId, ramId: null, ramManual: null, game, mode, budget: budget === '' ? null : Number(budget), aiMode, sellMode:'budget_only', targetFps: Number(targetFps), priceSources:publicSourceIds(priceSources), expectedSalePrice:null })
    if(completed===true)setLastCalculation(calculationKey)
  }

  function navigate(index) {
    flow.go(index,()=>{
      if(flow.step===0&&(!cpuId||!gpuId)){setError('Выберите процессор и видеокарту из списка найденных моделей.');return false}
      if(flow.step===2&&priceSources?.length===0){setError('Выберите хотя бы одну площадку.');return false}
      setError('');return true
    })
  }

  return <div className="configuration-panel">
    <details className="flow-import"><summary><Icon name="drive" size={18}/><span>Заполнить из отчёта компьютера<small>Импорт вместо ручного выбора</small></span><Icon name="plus" size={16}/></summary>
    <div className="detect-panel"><div><h3>Заполнить из данных компьютера</h3><p>Windows-скрипт прочитает модели CPU, GPU и установленную память. Запустите его, затем загрузите полученный JSON-файл.</p></div><div className="detect-actions"><a href="/scripts/run.bat" download="UpgradeLab-detect.bat" className="secondary-btn">Скачать скрипт</a><button type="button" className="secondary-btn" onClick={()=>fileInput.current?.click()}>Загрузить отчёт</button><button type="button" className="text-btn" onClick={()=>{setError('');setPasteOpen(true)}}>Вставить текст</button></div><input ref={fileInput} type="file" accept=".json,.txt,application/json" hidden onChange={importFile}/></div>
    {importInfo && <p className="import-summary" role="status">{importInfo}</p>}
    </details>
    {error && !pasteOpen && <p className="error" role="alert">{error}</p>}
    <form ref={flow.formRef} noValidate onSubmit={submit} className="configuration-form flow-form upgrade-flow">
      <StepNavigation steps={STEPS} flow={flow} onNavigate={navigate} disabled={loading}/>
      <StepHeading flow={flow} steps={STEPS}/>
      <div className="flow-panel" data-flow-panel="0" hidden={flow.step!==0}>
      <fieldset><legend>Комплектующие</legend><p className="field-hint">Начните вводить модель: например, fx6100, rtx3060 или i5 12400f.</p><div className="form-grid"><HardwareSearch label="Процессор" items={cpus} value={cpuId} onChange={setCpuId} placeholder="Найти процессор"/><HardwareSearch label="Видеокарта" items={gpus} value={gpuId} onChange={setGpuId} placeholder="Найти видеокарту" showVram={false}/></div><AutoDetectButton onDetect={(_, id)=>setGpuId(id)}/></fieldset>
      <p className="field-hint">Оперативная память не используется для оценки FPS в этом режиме: точных игровых измерений для её объёма и частоты недостаточно.</p>
      </div><div className="flow-panel" data-flow-panel="1" hidden={flow.step!==1}>
      <fieldset><legend>Сценарий и бюджет</legend><div className="form-grid"><GamePicker value={game} onChange={setGame}/><label>Разрешение и графика<Select value={mode} onChange={e=>setMode(e.target.value)}>{MODES.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}</Select></label><label>Бюджет из собственных средств, ₽<input type="number" min="0" max="10000000" step="100" placeholder="Без ограничения" value={budget} onChange={e=>setBudget(e.target.value)}/><small>Выручку от старой детали можно учесть после результата, когда станет известен ограничивающий компонент.</small></label><label>Использование нейросетей<Select value={aiMode} onChange={e=>setAiMode(e.target.value)}><option value="off">Не планирую</option><option value="light">Генерация изображений, небольшие LLM</option><option value="heavy">SDXL, крупные модели</option></Select></label></div></fieldset>
      <label>Желаемый FPS<input required type="number" min="1" max="1000" value={targetFps} onChange={e=>setTargetFps(e.target.value)}/><small>Цель сравнивается с центральным прогнозом FPS. Диапазон неопределённости доступен в пояснении расчёта.</small></label>
      </div><div className="flow-panel" data-flow-panel="2" hidden={flow.step!==2}>
      <GeoControls value={geo} onChange={setGeo}/><PriceSources value={priceSources} onChange={setPriceSources} upgrade/>
      </div><div className="flow-panel" data-flow-panel="3" hidden={flow.step!==3}>
      <ReviewSummary onEdit={navigate} items={[
        {label:'Процессор',value:cpus.find(cpu=>cpu.id===cpuId)?.name||'Не выбран',icon:'chip',step:0},
        {label:'Видеокарта',value:gpus.find(gpu=>gpu.id===gpuId)?.name||'Не выбрана',icon:'gpu',step:0},
        {label:'Игровая задача',value:game,note:`${MODES.find(item=>item.value===mode)?.label} · цель ${targetFps} FPS`,icon:'box',step:1},
        {label:'Бюджет и источники',value:budget===''?'Без ограничения бюджета':Number(budget).toLocaleString('ru-RU')+' ₽',note:priceSources===null?'Все доступные источники':`Выбрано площадок: ${priceSources.length}`,icon:'search',step:2},
      ]}/>
      </div>
      <StepFooter flow={flow} count={STEPS.length} onNext={()=>navigate(flow.step+1)} onExit={onExit} busy={loading} submitDisabled={lastCalculation===calculationKey} submitLabel={lastCalculation===calculationKey?'Параметры не изменились':'Рассчитать производительность'}/>
    </form>
    <Modal open={pasteOpen} onClose={()=>setPasteOpen(false)} title="Импорт конфигурации"><p className="field-hint">Вставьте JSON нового скрипта или текстовый отчёт предыдущей версии.</p><textarea className="report-input" rows="10" value={text} onChange={e=>setText(e.target.value)} placeholder={'{"cpus": [{"name": "AMD FX-6100"}], ...}'}/>{error && <p className="error" role="alert">{error}</p>}<div className="detect-actions"><Button disabled={!text.trim()} onClick={()=>importReport(text)}>Заполнить конфигурацию</Button><Button variant="secondary" onClick={()=>setPasteOpen(false)}>Отмена</Button></div></Modal>
  </div>
}
