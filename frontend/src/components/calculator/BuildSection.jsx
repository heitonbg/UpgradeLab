import { Icon } from '../ui/Icon'
import { fpsText } from '../../lib/performance'
import { FpsEvidence } from './FpsEvidence'
import { useState } from 'react'
import { runSearch } from '../../api/searchJobs'
import { GamePicker } from './GamePicker'
import { GAMES, MODES } from '../../constants/game'
import { PriceSources, StoreOffers, STORES } from '../StoreOffers'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { LoadingPanel } from '../ui/LoadingPanel'
import { BuildChoices } from './BuildChoices'
import { useStepFlow, StepNavigation, StepHeading, StepFooter, ReviewSummary } from '../ui/StepFlow'
import { AssemblyPartialResult, AssemblySearchSummary, AssemblyPriceNotice, PartPriceEvidence } from './AssemblySearchSummary'

const PARTS = [['motherboard','Материнская плата'],['memory','Комплект RAM (два модуля)'],['storage','SSD / накопитель'],['psu','Блок питания'],['case','Корпус'],['cooler','Кулер CPU']]
const emptyParts = Object.fromEntries(PARTS.map(([key])=>[key,{name:'',price:''}]))
const STEPS = [
  { title:'Задача', short:'Игра и бюджет', heading:'Во что будем играть?', description:'Выберите игру, настройки и сумму на весь системный блок.' },
  { title:'Основа', short:'Платформа и детали', heading:'Настроим основу сборки', description:'Выберите платформу и память. Остальные детали можем найти за вас.' },
  { title:'Магазины', short:'Где искать', heading:'Выберите площадки', description:'Сравним предложения выбранных магазинов и Avito.' },
  { title:'Проверка', short:'Всё готово к поиску', heading:'Ваша сборка начинается здесь', description:'Проверьте параметры. После поиска сможете сравнить до трёх конфигураций.' },
]

function selectedBuild(choice, config) {
  const { alternatives, ...build } = choice
  return {...build, config: {...config, ...choice.actual_config, selected_cpu_id: choice.parts.find(part => part.type === 'CPU')?.id, selected_gpu_id: choice.parts.find(part => part.type === 'GPU')?.id, selected_case_offer_id: choice.parts.find(part => part.type === 'case')?.offer_id || null}}
}

export function BuildSection({ onSave, onFind, active = true }) {
  const flow = useStepFlow(STEPS.length)
  const [form,setForm] = useState({budget:'',target_fps:60,game:GAMES[0].value,mode:MODES[0].value,socket:'AM4',ram_type:'DDR4',ram_capacity_gb:16,price_sources:STORES.map(([id])=>id),allow_store_fallback:true,allow_platform_change:true,auto_parts:true,case_style:'gaming',...emptyParts})
  const [offerPart,setOfferPart] = useState(null)
  const [result,setResult] = useState(null)
  const [searchProgress,setSearchProgress] = useState('Проверяем доступные площадки')
  const [partial,setPartial] = useState(null)
  const [busy,setBusy] = useState(false)
  const [searchStartedAt,setSearchStartedAt] = useState(null)
  const [error,setError] = useState('')
  const [choices,setChoices] = useState([])
  const [choiceConfig,setChoiceConfig] = useState(null)
  const [choicesOpen,setChoicesOpen] = useState(false)
  const set = key=>event=>setForm({...form,[key]:event.target.value})
  async function submit(event, retry=false) {
    event.preventDefault();if(busy)return
    if(!retry&&flow.step<STEPS.length-1){navigate(flow.step+1);return}
    if(!flow.validateAll())return
    setSearchStartedAt(Date.now())
    if(form.price_sources?.length===0){flow.go(2);setError('Выберите хотя бы одну площадку.');return}setBusy(true);setError('');setResult(null);setPartial(null);setChoices([]);setChoicesOpen(true)
    const config = {...form,scenario:'build',budget:Number(form.budget),target_fps:Number(form.target_fps),ram_capacity_gb:Number(form.ram_capacity_gb),...Object.fromEntries(PARTS.map(([key])=>[key,form.auto_parts?null:{name:form[key].name,price:Number(form[key].price),offer_id:form[key].offer_id||null}]))}
    setChoiceConfig(config)
    try {
      const data = await runSearch('assemble', config, {onProgress:setSearchProgress})
      if(data.status==='partial'){setPartial(data);setChoicesOpen(false);return}
      setChoices(data.alternatives?.length ? data.alternatives : [data])
      setResult(selectedBuild(data, config));setChoicesOpen(true)
    }
    catch(e){setError(e.message);setChoicesOpen(false)} finally{setBusy(false)}
  }
  function navigate(index) {
    flow.go(index,()=>{
      if(flow.step===2&&form.price_sources?.length===0){setError('Выберите хотя бы одну площадку.');return false}
      setError('');return true
    })
  }
  return <section className="build-section space-y-6">
    <div className="builder-layout">
      <form ref={flow.formRef} noValidate id="assembly-form" className="configuration-form panel builder-form flow-form" onSubmit={submit}>
        <div className="builder-form-heading"><span className="section-icon"><Icon name="box" size={23}/></span><div><h2>Параметры будущего ПК</h2><p>Выберите игру и бюджет — сравним подходящие конфигурации.</p></div></div>
        <StepNavigation steps={STEPS} flow={flow} onNavigate={navigate} disabled={busy}/>
        <StepHeading flow={flow} steps={STEPS}/>
        <div className="flow-panel" data-flow-panel="0" hidden={flow.step!==0}><fieldset className="builder-step"><legend><span>01</span>Игра и производительность</legend><div className="form-grid">
          <GamePicker value={form.game} onChange={game=>setForm({...form,game})}/>
          <label>Разрешение и настройки<select value={form.mode} onChange={set('mode')}>{MODES.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}</select></label>
          <label>Бюджет на весь ПК, ₽<input required name="build_budget" type="number" placeholder="Например, 90 000" min="1" max="10000000" value={form.budget} onChange={set('budget')}/></label>
          <label>Целевой FPS<input required type="number" min="1" max="1000" value={form.target_fps} onChange={set('target_fps')}/></label>
        </div></fieldset></div>
        <div className="flow-panel" data-flow-panel="1" hidden={flow.step!==1}><fieldset className="builder-step"><legend><span>02</span>Платформа и комплектующие</legend>
          <label className="auto-parts-toggle"><input name="auto_parts" type="checkbox" checked={form.auto_parts} onChange={e=>setForm({...form,auto_parts:e.target.checked})}/><span><strong>Подобрать комплектующие автоматически</strong><small>Сами найдём CPU, GPU и остальные детали на выбранных площадках.</small></span></label>
          <div className="form-grid">
            <label>Платформа<select value={form.socket} onChange={e=>setForm({...form,socket:e.target.value,ram_type:e.target.value==='AM5'?'DDR5':'DDR4'})}>{['AM4','AM5','LGA1151','LGA1200','LGA1700'].map(socket=><option key={socket}>{socket}</option>)}</select></label>
            <label>Тип памяти<select value={form.ram_type} onChange={set('ram_type')}>{(form.socket==='AM5'?['DDR5']:form.socket==='LGA1700'?['DDR4','DDR5']:['DDR4']).map(type=><option key={type}>{type}</option>)}</select></label>
            <label>Объём RAM, ГБ<input required type="number" min="8" max="512" value={form.ram_capacity_gb} onChange={set('ram_capacity_gb')}/></label>
            {form.auto_parts&&<label>Стиль корпуса<select value={form.case_style} onChange={set('case_style')}><option value="gaming">Игровой: стекло и подсветка</option><option value="minimal">Сдержанный: лаконичный дизайн</option><option value="budget">Экономный: простой или б/у</option></select></label>}
          </div>
          {form.auto_parts&&<label className="auto-parts-toggle"><input type="checkbox" checked={form.allow_platform_change} onChange={event=>setForm({...form,allow_platform_change:event.target.checked})}/><span><strong>Можно подобрать другую совместимую платформу</strong><small>При нехватке деталей пересмотрим CPU, плату и тип памяти. Бюджет и минимальный объём RAM сохраняются.</small></span></label>}
          {!form.auto_parts&&<div className="manual-parts"><p className="field-hint">Можно указать имеющиеся детали. Стоимость 0 ₽ допустима; характеристики введённых вручную моделей не подтверждаются автоматически.</p>{PARTS.map(([key,label])=><div className="manual-part-row" key={key}><label>{label}<input required minLength="2" maxLength="200" placeholder="Модель" value={form[key].name} onChange={e=>setForm({...form,[key]:{...form[key],name:e.target.value,offer_id:null}})}/></label><label>Цена, ₽<input required type="number" min="0" max="10000000" value={form[key].price} onChange={e=>setForm({...form,[key]:{...form[key],price:e.target.value,offer_id:null}})}/></label><Button type="button" variant="secondary" onClick={()=>setOfferPart(key)}>Найти</Button></div>)}</div>}
        </fieldset></div>
        <div className="flow-panel" data-flow-panel="2" hidden={flow.step!==2}><fieldset className="builder-step source-step"><legend><span>03</span>Где искать предложения</legend><PriceSources value={form.price_sources} onChange={value=>setForm({...form,price_sources:value})}/>{form.auto_parts&&<label className="auto-parts-toggle"><input type="checkbox" checked={form.allow_store_fallback||form.price_sources?.includes('avito')} disabled={form.price_sources?.includes('avito')} onChange={event=>setForm({...form,allow_store_fallback:event.target.checked})}/><span><strong>Если не хватает предложений — искать в других магазинах</strong><small>{form.price_sources?.includes('avito')?'Avito выбран: резервный поиск включён автоматически, если площадка ограничит доступ.':'Сначала проверим выбранные площадки, затем автоматически подключим остальные.'}</small></span></label>}<div className="flow-callout"><Icon name="shield"/><p>Сверим цены выбранных товаров. Если магазин не отвечает, поищем замену. Доставка и персональные скидки не включены.</p></div></fieldset></div>
        <div className="flow-panel" data-flow-panel="3" hidden={flow.step!==3}><ReviewSummary onEdit={navigate} items={[
          {label:'Игра и графика',value:form.game, note:`${MODES.find(mode=>mode.value===form.mode)?.label} · цель ${form.target_fps} FPS`,icon:'gpu',step:0},
          {label:'Бюджет на весь ПК',value:form.budget?Number(form.budget).toLocaleString('ru-RU')+' ₽':'Не указан',note:'8 комплектующих · без периферии и доставки',icon:'box',step:0},
          {label:'Платформа',value:`${form.socket} · ${form.ram_type} · ${form.ram_capacity_gb} ГБ`,note:form.auto_parts?'Автоматический подбор деталей':'Детали выбраны вручную',icon:'chip',step:1},
          {label:'Источники предложений',value:form.price_sources===null?'Все доступные':`Площадок: ${form.price_sources.length}`,note:form.price_sources===null||form.price_sources.includes('avito')?'Приоритет Avito: сначала пересоберём варианты на этой площадке':'Поиск может занять несколько минут',icon:'search',step:2},
        ]}/><div className="flow-callout"><Icon name="exchange"/><p>Сравните цену, состав и диапазон FPS в карточках. Вы сможете изменить параметры и повторить поиск.</p></div></div>
        {error&&<div className="flow-error error" role="alert">{error}</div>}
        <StepFooter flow={flow} count={STEPS.length} onNext={()=>navigate(flow.step+1)} busy={busy} submitLabel="Подобрать сборки"/>
      </form>
      <aside className="builder-sidebar"><div className="budget-card"><p className="eyebrow">Ваш ориентир</p><strong>{form.budget?Number(form.budget).toLocaleString('ru-RU')+' ₽':'Ваш бюджет'}</strong><span>На все 8 комплектующих</span><div><Icon name="chip"/><Icon name="gpu"/><Icon name="drive"/><Icon name="box"/></div><p>Сравнивайте варианты по цене, возможностям и составу. FPS показываем диапазоном.</p></div><div className="quality-standard"><div className="quality-heading"><Icon name="shield"/><h3>Качество — часть подбора</h3></div><ul><li><strong>Блок питания</strong><span>Модель, мощность и класс эффективности по спецификации производителя.</span></li><li><strong>Внутренний SSD</strong><span>M.2 NVMe при подтверждённом слоте платы; иначе SATA 2,5″. Проверенные серии, включая Netac и KingSpec. При выбранном Avito доступны б/у SSD с отдельной проверкой состояния.</span></li><li><strong>Полноценное охлаждение</strong><span>Кулер под ваш сокет. Крепления и вентиляторы отдельно не подставляются.</span></li></ul><p>Для автоматического подбора. Цены на качество могут потребовать большего бюджета.</p></div></aside>
    </div>
    {busy&&!choicesOpen&&<LoadingPanel title="Подбираем варианты сборки" description={searchProgress} startedAt={searchStartedAt} cards/>}
    <Modal open={active&&choicesOpen} onClose={()=>setChoicesOpen(false)} title={busy?'Собираем варианты для вас':'Выберите свою сборку'} size="wide">{busy?<LoadingPanel title="Ищем детали и сверяем цены товаров" description={searchProgress} startedAt={searchStartedAt} cards/>:<BuildChoices choices={choices} targetFps={choiceConfig?.target_fps} onSelect={choice=>{setResult(selectedBuild(choice,choiceConfig));setChoicesOpen(false)}}/>}</Modal>
    {choices.length>0&&!busy&&<div className="build-ready result-reveal"><div><strong>Варианты готовы</strong><p className="field-hint">Сравните состав и выберите подходящий вариант.</p></div><Button type="button" variant="secondary" onClick={()=>setChoicesOpen(true)}>Сравнить варианты ({choices.length})</Button></div>}
    <Modal open={active&&Boolean(offerPart)} onClose={()=>setOfferPart(null)} title="Выбрать предложение" size="lg">{offerPart&&<StoreOffers key={offerPart} category={offerPart} initialQuery={form[offerPart].name} onSelect={offer=>{setForm({...form,[offerPart]:{name:offer.name,price:offer.price_rub,offer_id:offer.id}});setOfferPart(null)}}/>}</Modal>
    {partial&&!busy&&<AssemblyPartialResult data={partial} onRetry={()=>submit({preventDefault(){}},true)} onEdit={()=>navigate(0)}/>}
    {result&&<AssemblySearchSummary report={result.search_report}/>}
    {result&&<BuildResult result={result} onSave={()=>onSave(result)} onFind={onFind}/>}
  </section>
}

function QualityDetails({ quality }) {
  if(!quality)return null
  return <details className="part-quality"><summary><Icon name="shield" size={13}/>{quality.label}</summary><ul>{quality.claims.map(claim=><li key={claim}>{claim}</li>)}</ul><a href={quality.source_url} target="_blank" rel="noopener noreferrer">Характеристики производителя</a><p>{quality.basis}</p>{quality.board_compatibility&&<p>{quality.board_compatibility.basis} <a href={quality.board_compatibility.source_url} target="_blank" rel="noopener noreferrer">Проверка слота платы</a></p>}</details>
}

const partLabels = {CPU:'Процессор',GPU:'Видеокарта',motherboard:'Материнская плата',memory:'Оперативная память',storage:'Накопитель',psu:'Блок питания',case:'Корпус',cooler:'Кулер CPU'}
const partIcons = {CPU:'chip',GPU:'gpu',motherboard:'chip',memory:'chip',storage:'drive',psu:'shield',case:'box',cooler:'fan'}

export function BuildResult({ result, onSave, onFind }) {
  const [compare,setCompare]=useState(null)
  const [saving,setSaving]=useState(false)
  async function save(){setSaving(true);try{await onSave?.()}finally{setSaving(false)}}
  return <section className="panel build-result result-reveal"><header className="build-result-heading"><div><p className="eyebrow">Ваша конфигурация</p><h2>{result.title||'Подобранная сборка'}</h2></div><div className="build-fps"><strong>{fpsText(result.fps,result.fps_outlook)}</strong><span>FPS · оценка</span></div></header><AssemblyPriceNotice draft={result.status==='draft'} note={result.price_note}/><p className="result-note">{result.recommendation}</p><FpsEvidence outlook={result.fps_outlook}/><div className="build-parts">{result.parts.map(part=><div className="build-part-card account-item" key={part.type}><span className="part-symbol"><Icon name={partIcons[part.type]}/></span><div className="part-information"><small>{partLabels[part.type]}</small><strong>{part.name}</strong>{part.price_offer_name&&part.price_offer_name!==part.name&&<small className="part-ad-title">В объявлении: {part.price_offer_name}</small>}<span>{part.price_source}{part.price_date&&' · '+new Date(part.price_date).toLocaleDateString('ru-RU')}{part.price_market==='used_ru'&&' · Б/у'}</span>{part.price_verified_at&&<small className="verified-price">Цена сверена по странице товара · {new Date(part.price_verified_at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</small>}<PartPriceEvidence part={part}/>{part.purchase_warning&&<small className="part-purchase-warning">{part.purchase_warning}</small>}<QualityDetails quality={part.quality}/></div><div className="part-price-actions"><strong>{part.price.toLocaleString('ru-RU')} ₽</strong>{part.price_url&&<a href={part.price_url} target="_blank" rel="noopener noreferrer">Предложение<Icon name="arrow" size={12}/></a>}<button type="button" onClick={()=>setCompare(part)}>Сравнить цены</button>{part.id&&onFind&&<button type="button" onClick={()=>onFind({search:part.name})}>Найти на бирже</button>}</div></div>)}</div><div className="build-total"><div><span>{result.status==='draft'?'Предварительная стоимость ПК':'Итого за весь ПК'}</span><strong>{result.total_price.toLocaleString('ru-RU')} ₽</strong><small>Остаток бюджета: {result.remaining_budget.toLocaleString('ru-RU')} ₽</small></div>{onSave&&<Button type="button" loading={saving} onClick={save}>{saving?'Сохраняем…':'Сохранить сборку'}</Button>}</div><details className="compatibility-details"><summary>Что проверить перед покупкой</summary><ul className="field-hint">{result.compatibility_notes.map(note=><li key={note}>{note}</li>)}</ul></details><Modal open={Boolean(compare)} onClose={()=>setCompare(null)} title="Предложения на площадках" size="lg">{compare&&<StoreOffers key={compare.name} initialQuery={compare.name} category={compare.type} hardwareId={compare.id}/>}</Modal></section>
}
