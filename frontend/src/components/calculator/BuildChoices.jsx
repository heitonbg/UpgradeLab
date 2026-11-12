import { buildTrust, distinctBuilds, variantHeading, compatibilityLabel, buildMetric } from '../../lib/buildPresentation'
import { Button } from '../ui/Button'
import { targetText } from '../../lib/performance'
import { FpsEvidence } from './FpsEvidence'
import { AssemblySearchSummary, AssemblyPriceNotice, PartPriceEvidence } from './AssemblySearchSummary'

const labels = { CPU: 'Процессор', GPU: 'Видеокарта', motherboard: 'Плата', memory: 'Память', storage: 'Накопитель', psu: 'Блок питания', case: 'Корпус', cooler: 'Кулер' }
const money = value => value.toLocaleString('ru-RU') + ' ₽'

export function BuildChoices({ choices:rawChoices, targetFps, onSelect }) {
  const choices=distinctBuilds(rawChoices)
  return <div className="build-choice-content">
    <AssemblyPriceNotice draft={choices[0]?.status==='draft'||choices[0]?.purchase_ready===false} note={choices[0]?.price_note}/>
    <AssemblySearchSummary report={choices[0]?.search_report}/>
    <p className="choice-intro">Один бюджет — разные возможности. Сравните стоимость и возможности, раскройте состав и выберите подходящий вариант.</p>
    <p className="field-hint">{choices[0]?.workload==='cpu_work'?'Рабочий CPU-профиль. Скорость приложений не измерена.':`Цель: ${targetFps} FPS.`} {choices[0]?.status==='draft'?'Расчётные суммы укладываются в бюджет по полученным ценам.':'Все варианты укладываются в бюджет.'} Показатели ориентировочные; доставка не учтена.</p>
    {choices.length < 3 && <p className="choice-limited">Нашлось разных конфигураций: {choices.length}. Показываем подходящие варианты с доступными ценами и сопоставимой производительностью.</p>}
    <div className="build-choice-grid">
      {choices.map((choice, index) => <article className={`build-choice-card ${index === 0 ? 'recommended' : ''}`} key={choice.variant_key || index} style={{'--card-index': index}}>
        <div className="choice-card-top"><span className="choice-number">0{index + 1}</span><span className="choice-tag">{index === 0 ? 'Наш выбор' : 'Альтернатива'}</span></div>
        <svg className="choice-pc" width="52" height="64" viewBox="0 0 52 64" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="7" y="3" width="38" height="54" rx="5"/><path d="M15 12h22M15 48h22M14 61h6m12 0h6"/><circle cx="26" cy="29" r="10"/><circle cx="26" cy="29" r="4"/><path d="m26 19 3 6m7 4-6 3m-4 7-3-6m-7-4 6-3"/></svg>
        <p className={`build-trust is-${buildTrust(choice).kind}`}>{buildTrust(choice).label}</p><h4>{variantHeading(choice)}</h4><p className="field-hint">{buildTrust(choice).note}</p>
        <p className="choice-compatibility">{compatibilityLabel(choice)}</p><p className="choice-summary">{choice.summary || choice.recommendation}</p>
        <div className="choice-fps"><strong>{buildMetric(choice).value}</strong><span>{buildMetric(choice).label}<br/><small>{choice.workload==='cpu_work'?buildMetric(choice).note:targetText(choice.fps_outlook,targetFps,choice.target_reached)}</small></span></div>
        {choice.workload!=='cpu_work'&&<FpsEvidence outlook={choice.fps_outlook}/>}
        <div className="choice-main-parts">{choice.parts.filter(part => ['CPU','GPU','case'].includes(part.type)).map(part => <div key={part.type}><small>{labels[part.type]}</small><strong>{part.name}</strong></div>)}</div>
        <div className="choice-quality">{choice.parts.filter(part=>part.quality&&['psu','storage'].includes(part.type)).map(part=><span key={part.type}>{part.type==='psu'?'БП':'SSD'}<strong>{part.quality.label}{part.quality.condition==='used'?' · Б/у':''}</strong></span>)}</div>
        <div className="choice-price">{choice.status==='draft'&&<small>Предварительная сумма</small>}<strong>{money(choice.total_price)}</strong><small>Остаток бюджета по расчёту: {money(choice.remaining_budget)}</small></div>
        <details className="choice-details"><summary>Все {choice.parts.length} комплектующих и цены</summary><ul>{choice.parts.map(part => <li key={part.type}><span>{labels[part.type]} · {part.name}</span>{part.price_offer_name&&part.price_offer_name!==part.name&&<small className="part-ad-title">В объявлении: {part.price_offer_name}</small>}<strong>{money(part.price)}</strong>{part.price_verified_at&&<small className="verified-price">Цена сверена по странице товара</small>}<PartPriceEvidence part={part}/>{part.price_basis!=='reference'&&(part.price_date||part.price_observed_at)&&<small>Наблюдение: {new Date(part.price_observed_at||part.price_date).toLocaleString('ru-RU')}</small>}{part.purchase_warning&&<small className="part-purchase-warning">{part.purchase_warning}</small>}{part.price_url && <a href={part.price_url} target="_blank" rel="noopener noreferrer">{part.price_source}</a>}</li>)}</ul><p className="field-hint">Перед покупкой проверьте BIOS, размеры и разъёмы в карточках товаров.</p></details>
        <Button type="button" variant={index === 0 ? 'primary' : 'secondary'} onClick={() => onSelect(choice)}>Выбрать эту сборку</Button>
      </article>)}
    </div>
  </div>
}
