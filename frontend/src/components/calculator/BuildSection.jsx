import { compatibilityLabel, buildMetric } from '../../lib/buildPresentation'
import { publicSourceIds } from '../../lib/publicSources'
import { Select } from '../ui/Select'
import { useHardware } from '../../hooks/useHardware'
import { HardwareSearch } from '../ui/HardwareSearch'
import { BuildSummary } from './BuildSummary'
import { CategoryImage } from '../CategoryImage'
import { GeoControls } from '../GeoControls'
import { compatibilityNotice } from '../../lib/offerEvidence.js'
import { Icon } from '../ui/Icon'
import { FpsEvidence } from './FpsEvidence'
import { useEffect,useState } from 'react'
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
  { title:'Задача', short:'Бюджет и цель', heading:'Каким будет ваш ПК?', description:'Задайте бюджет и приоритет. Технические детали можно доверить подбору.' },
  { title:'Основа', short:'Дополнительные настройки', heading:'Настроим основу сборки', description:'Оставьте подбору свободу или задайте важные для вас ограничения.' },
  { title:'Получение', short:'Город и доставка', heading:'Где вам удобно получить детали?', description:'Укажите город и способ получения. География подтверждается отдельно для каждого предложения.' },
  { title:'Проверка', short:'Всё готово к поиску', heading:'Ваша сборка начинается здесь', description:'Проверьте параметры. После поиска сможете сравнить до трёх конфигураций.' },
]

function selectedBuild(choice, config) {
  const { alternatives, ...build } = choice
  return {...build, config: {...config, ...choice.actual_config, selected_cpu_id: choice.parts.find(part => part.type === 'CPU')?.id, selected_gpu_id: choice.parts.find(part => part.type === 'GPU')?.id, selected_case_offer_id: choice.parts.find(part => part.type === 'case')?.offer_id || null}}
}

export function BuildSection({ onSave, onFind, active = true, offerIntent, onOfferConsumed }) {
  const flow = useStepFlow(STEPS.length)
  const { cpus, gpus } = useHardware()
  const [form,setForm] = useState({condition:'any',workload:'gaming',objective:'performance',selected_cpu_id:null,selected_gpu_id:null,pricing_mode:'offers',city_id:null,geo_mode:'all',max_price:null,budget:'',target_fps:60,game:GAMES[0].value,mode:MODES[0].value,socket:'AM4',ram_type:'DDR4',ram_capacity_gb:16,price_sources:STORES.filter(([id])=>id!=='avito').map(([id])=>id),allow_store_fallback:false,allow_platform_change:true,auto_parts:true,case_style:'gaming',...emptyParts})
  useEffect(()=>{if(!offerIntent||!PARTS.some(([key])=>key===offerIntent.category))return;setForm(current=>({...current,...(offerIntent.selection_scope||{}),price_sources:current.price_sources&&!current.price_sources.includes(offerIntent.source)?[...current.price_sources,offerIntent.source]:current.price_sources,auto_parts:false,[offerIntent.category]:{name:offerIntent.name,price:offerIntent.price_rub,offer_id:offerIntent.id}}));onOfferConsumed?.()},[offerIntent,onOfferConsumed])
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
    if(publicSourceIds(form.price_sources).length===0){flow.go(2);setError('Выберите хотя бы одну площадку.');return}setBusy(true);setError('');setResult(null);setPartial(null);setChoices([]);setChoicesOpen(true)
    const config = {...form,objective:'performance',pricing_mode:'offers',allow_store_fallback:false,price_sources:publicSourceIds(form.price_sources),scenario:'build',budget:Number(form.budget),target_fps:Number(form.target_fps),ram_capacity_gb:Number(form.ram_capacity_gb),...Object.fromEntries(PARTS.map(([key])=>[key,form.auto_parts?null:{name:form[key].name,price:Number(form[key].price),offer_id:form[key].offer_id||null}]))}
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
      if(flow.step===2&&form.pricing_mode!=='reference'&&form.price_sources?.length===0){setError('Выберите хотя бы одну площадку.');return false}
      setError('');return true
    })
  }
  return <section className="build-section space-y-6">
    <div className="builder-layout">
      <form ref={flow.formRef} noValidate id="assembly-form" className="configuration-form panel builder-form flow-form" onSubmit={submit}>
        <div className="builder-form-heading"><span className="section-icon"><Icon name="box" size={23}/></span><div><h2>Параметры будущего ПК</h2><p>Бюджет, задачи и предложения — с проверкой совместимости.</p></div></div>
        <StepNavigation steps={STEPS} flow={flow} onNavigate={navigate} disabled={busy}/>
        <StepHeading flow={flow} steps={STEPS}/>
        <div className="flow-panel" data-flow-panel="0" hidden={flow.step!==0}>
          <fieldset className="builder-step"><legend>Главное о вашем ПК</legend><div className="form-grid">
            <label className="budget-field">Бюджет на весь ПК, ₽<input required name="build_budget" type="number" placeholder="80 000" min="1" max="10000000" value={form.budget} onChange={set('budget')}/><small>Восемь комплектующих, без периферии и доставки</small></label>
            <label>Назначение<Select value={form.workload} onChange={e=>setForm({...form,workload:e.target.value,game:form.game||GAMES[0].value})}><option value="gaming">Игры</option><option value="cpu_work">Работа с нагрузкой на CPU</option></Select></label>

            <label>Состояние деталей<Select value={form.condition} onChange={set('condition')}><option value="any">Новые и б/у</option><option value="new">Только новые</option><option value="used">Только б/у</option></Select></label>
          </div><PriceSources value={form.price_sources} onChange={price_sources=>setForm({...form,price_sources})}/></fieldset>
          {form.workload==='gaming'?<fieldset className="builder-step game-settings"><legend>Во что будем играть</legend><div className="form-grid"><GamePicker value={form.game} onChange={game=>setForm({...form,game})}/><div className="game-performance"><label>Разрешение и графика<Select value={form.mode} onChange={set('mode')}>{MODES.map(m=><option key={m.value} value={m.value}>{m.label}</option>)}</Select></label><label>Целевой FPS<input required type="number" min="1" max="1000" value={form.target_fps} onChange={set('target_fps')}/></label></div></div></fieldset>:<p className="field-hint">Рабочий профиль оценивает CPU Mark и заданный объём RAM. Скорость конкретных приложений не измерена.</p>}
          <p className="constraint-summary">Минимум {form.ram_capacity_gb} ГБ RAM{form.selected_cpu_id&&' · CPU зафиксирован'}{form.selected_gpu_id&&' · GPU зафиксирована'}{!form.allow_platform_change&&` · ${form.socket}/${form.ram_type}`} · <button type="button" className="text-btn" onClick={()=>navigate(1)}>Настроить ограничения</button></p>
        </div>
        <div className="flow-panel" data-flow-panel="1" hidden={flow.step!==1}>
          <div className="foundation-intro"><Icon name="chip"/><div><h4>Доверьте основу подбору</h4><p>Проверим совместимость CPU, платы и памяти. Точные требования можно задать ниже.</p></div></div>
          <div className="constraint-summary" aria-label="Действующие ограничения"><span>От {form.ram_capacity_gb} ГБ RAM</span>{form.selected_cpu_id&&<span>CPU: {cpus.find(c=>c.id===form.selected_cpu_id)?.name}</span>}{form.selected_gpu_id&&<span>GPU: {gpus.find(c=>c.id===form.selected_gpu_id)?.name}</span>}{!form.allow_platform_change&&<span>{form.socket} · {form.ram_type}</span>}<button type="button" className="text-btn" onClick={()=>setForm({...form,selected_cpu_id:null,selected_gpu_id:null,socket:'AM4',ram_type:'DDR4',ram_capacity_gb:16,case_style:'gaming',allow_platform_change:true})}>Сбросить ограничения</button></div>
          <details className="advanced-settings"><summary>Расширенные настройки <span>CPU, GPU, платформа и память</span></summary><div className="form-grid">
            <HardwareSearch label="Фиксированный CPU" items={cpus.filter(cpu=>['AM4','AM5','LGA1151','LGA1200','LGA1700'].includes(cpu.socket))} value={form.selected_cpu_id} onChange={id=>setForm({...form,selected_cpu_id:id,...(id?{socket:cpus.find(c=>c.id===id)?.socket||form.socket,ram_type:cpus.find(c=>c.id===id)?.socket==='AM5'?'DDR5':'DDR4',allow_platform_change:false}:{})})}/>
            <HardwareSearch label="Фиксированный GPU" items={gpus} value={form.selected_gpu_id} onChange={id=>setForm({...form,selected_gpu_id:id})}/>
            <label>Платформа<Select disabled={Boolean(form.selected_cpu_id)} value={form.socket} onChange={e=>setForm({...form,socket:e.target.value,ram_type:e.target.value==='AM5'?'DDR5':'DDR4',allow_platform_change:false})}>{['AM4','AM5','LGA1151','LGA1200','LGA1700'].map(socket=><option key={socket}>{socket}</option>)}</Select></label>
            <label>Тип памяти<Select value={form.ram_type} onChange={set('ram_type')}>{(form.socket==='AM5'?['DDR5']:form.socket==='LGA1700'?['DDR4','DDR5']:['DDR4']).map(type=><option key={type}>{type}</option>)}</Select></label>
            <label>Минимальный объём RAM, ГБ<input required type="number" min="8" max="512" value={form.ram_capacity_gb} onChange={set('ram_capacity_gb')}/></label>
          </div><label className="compact-setting"><input type="checkbox" disabled={Boolean(form.selected_cpu_id)} checked={form.allow_platform_change&&!form.selected_cpu_id} onChange={e=>setForm({...form,allow_platform_change:e.target.checked})}/><span>Разрешить другую совместимую платформу<small>{form.selected_cpu_id?'Чтобы менять платформу, снимите фиксацию CPU.':'При нехватке деталей пересмотрим CPU, плату и память; бюджет и объём RAM сохраняются.'}</small></span></label>
          <label className="compact-setting"><input type="checkbox" checked={form.auto_parts} onChange={e=>setForm({...form,auto_parts:e.target.checked})}/><span>Автоматически подобрать все комплектующие<small>Выключите, чтобы указать уже имеющиеся детали.</small></span></label></details>
          <fieldset className="case-preference"><legend>Предпочтение корпуса</legend><div className="source-segments" role="group" aria-label="Стиль корпуса">{[['minimal','Сдержанный'],['gaming','Игровой'],['budget','Экономный']].map(([id,label])=><button type="button" key={id} aria-pressed={form.case_style===id} onClick={()=>setForm({...form,case_style:id})}>{label}</button>)}</div><p className="field-hint">Используем существующие признаки корпуса. Компактность и точные размеры требуют проверки; неподтверждённый стиль не обещается.</p></fieldset>
          {!form.auto_parts&&<div className="manual-parts"><p className="field-hint">Уже имеющиеся детали можно указать с ценой 0 ₽.</p>{PARTS.map(([key,label])=><div className="manual-part-row" key={key}><label>{label}<input required minLength="2" maxLength="200" value={form[key].name} onChange={e=>setForm({...form,[key]:{...form[key],name:e.target.value,offer_id:null}})}/></label><label>Цена, ₽<input required type="number" min="0" value={form[key].price} onChange={e=>setForm({...form,[key]:{...form[key],price:e.target.value,offer_id:null}})}/></label><Button type="button" variant="secondary" onClick={()=>setOfferPart(key)}>Найти</Button></div>)}</div>}
        </div>
        <div className="flow-panel" data-flow-panel="2" hidden={flow.step!==2}><GeoControls value={form} onChange={setForm}/><p className="field-hint">Ищем в {form.price_sources.length===2?'обоих источниках':form.price_sources[0]==='regard'?'Regard':'бирже UpgradeLab'}. Неизвестная доставка не считается бесплатной. Закрытые данные каталога не показываются.</p></div>
        <div className="flow-panel" data-flow-panel="3" hidden={flow.step!==3}><ReviewSummary onEdit={navigate} items={[
          {label:form.workload==='gaming'?'Игра и графика':'Назначение',value:form.workload==='gaming'?form.game:'Работа с нагрузкой на CPU',note:form.workload==='gaming'?`${MODES.find(mode=>mode.value===form.mode)?.label} · цель ${form.target_fps} FPS`:`CPU Mark · минимум ${form.ram_capacity_gb} ГБ RAM`,icon:'gpu',step:0},
          {label:'Бюджет на весь ПК',value:form.budget?Number(form.budget).toLocaleString('ru-RU')+' ₽':'Не указан',note:'8 комплектующих · без периферии и доставки',icon:'box',step:0},
          {label:'Платформа',value:`${form.socket} · ${form.ram_type} · ${form.ram_capacity_gb} ГБ`,note:form.auto_parts?'Автоматический подбор деталей':'Детали выбраны вручную',icon:'chip',step:1},
          {label:'Источники предложений',value:form.price_sources.length===2?'Regard + Биржа UpgradeLab':form.price_sources[0]==='regard'?'Regard':'Биржа UpgradeLab',note:'Только разрешённые к показу предложения',icon:'search',step:2},
        ]}/><div className="flow-callout"><Icon name="exchange"/><p>Сравните цену, состав и диапазон FPS в карточках. Вы сможете изменить параметры и повторить поиск.</p></div></div>
        {error&&<div className="flow-error error" role="alert">{error}</div>}
        <StepFooter flow={flow} count={STEPS.length} onNext={()=>navigate(flow.step+1)} busy={busy} submitLabel="Подобрать сборки"/>
      </form>
      <aside className="builder-sidebar"><div className="budget-card"><p className="eyebrow">Ваш ориентир</p><strong>{form.budget?Number(form.budget).toLocaleString('ru-RU')+' ₽':'Ваш бюджет'}</strong><span>На все 8 комплектующих</span><div><Icon name="chip"/><Icon name="gpu"/><Icon name="drive"/><Icon name="box"/></div><p>{form.workload==='cpu_work'?'Ориентируемся на CPU Mark и заданный объём RAM. Скорость приложений не измерена.':'Сравнивайте цену, состав и диапазон игрового FPS.'}</p></div><details className="quality-standard"><summary className="quality-heading"><Icon name="shield"/><h3>Что мы проверяем</h3></summary><ul><li><strong>Блок питания</strong><span>Модель, мощность и класс эффективности по спецификации производителя.</span></li><li><strong>Внутренний SSD</strong><span>M.2 NVMe при подтверждённом слоте платы; иначе SATA 2,5″. Проверенные серии, включая Netac и KingSpec. Б/у накопители требуют отдельной проверки состояния и ресурса.</span></li><li><strong>Полноценное охлаждение</strong><span>Кулер под ваш сокет. Крепления и вентиляторы отдельно не подставляются.</span></li></ul><p>Для автоматического подбора. Цены на качество могут потребовать большего бюджета.</p></details></aside>
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
  return <section className="panel build-result result-reveal"><header className="build-result-heading"><div><p className="eyebrow">Ваша конфигурация</p><h2>{result.title||'Подобранная сборка'}</h2></div><div className="build-fps"><strong>{buildMetric(result).value}</strong><span>{buildMetric(result).label} · ориентир</span></div></header><p className="choice-compatibility">{compatibilityLabel(result)}</p><AssemblyPriceNotice draft={result.status==='draft'||result.purchase_ready===false} note={result.price_note}/><p className="result-note">{result.recommendation}</p>{result.hardware_metrics&&<dl className="build-hardware-facts"><div><dt>Сценарий</dt><dd>{result.game} · {result.mode?.replace('_',' ')}</dd></div><div><dt>Выбор CPU/GPU</dt><dd>По слабейшему аппаратному показателю; игровой FPS не подтверждён</dd></div><div><dt>Память</dt><dd>{result.hardware_metrics.ram_modules} мод. · {result.hardware_metrics.ram_capacity_gb} ГБ{result.hardware_metrics.ram_factory_kit?' · KIT':''}</dd></div><div><dt>SSD</dt><dd>{result.hardware_metrics.storage_capacity_gb} ГБ · {result.hardware_metrics.storage_interface}</dd></div></dl>}{result.workload!=='cpu_work'&&<FpsEvidence outlook={result.fps_outlook}/>}<div className="build-parts">{result.parts.map(part=><div className="build-part-card account-item" key={part.type}><span className="part-symbol"><CategoryImage category={part.type}/></span><div className="part-information"><small>{partLabels[part.type]}</small><strong>{part.name}</strong>{part.price_offer_name&&part.price_offer_name!==part.name&&<small className="part-ad-title">В объявлении: {part.price_offer_name}</small>}<span>{part.price_source}{part.price_date&&' · '+new Date(part.price_date).toLocaleDateString('ru-RU')}{part.price_market==='used_ru'&&' · Б/у'}</span>{part.price_verified_at&&<small className="verified-price">Цена сверена по странице товара · {new Date(part.price_verified_at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</small>}<PartPriceEvidence part={part}/>{part.compatibility&&<small className="field-hint">{compatibilityNotice(part.compatibility)}</small>}{part.purchase_warning&&<small className="part-purchase-warning">{part.purchase_warning}</small>}<QualityDetails quality={part.quality}/></div><div className="part-price-actions"><strong>{part.price.toLocaleString('ru-RU')} ₽</strong>{part.price_url&&<a href={part.price_url} target="_blank" rel="noopener noreferrer">Предложение<Icon name="arrow" size={12}/></a>}<button type="button" onClick={()=>setCompare(part)}>Сравнить цены</button>{part.id&&onFind&&<button type="button" onClick={()=>onFind({search:part.name})}>Найти на бирже</button>}</div></div>)}</div><BuildSummary result={result} onSave={onSave?save:undefined} saving={saving}/><details className="compatibility-details"><summary>Что проверить перед покупкой</summary><ul className="field-hint">{result.compatibility_notes.map(note=><li key={note}>{note}</li>)}</ul></details><Modal open={Boolean(compare)} onClose={()=>setCompare(null)} title="Предложения на площадках" size="lg">{compare&&<StoreOffers key={compare.name} initialQuery={compare.name} category={compare.type} hardwareId={compare.id}/>}</Modal></section>
}
