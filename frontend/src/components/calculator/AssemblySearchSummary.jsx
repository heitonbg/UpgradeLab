import { missingPartNotice } from '../../lib/sourceDiagnostics.js'
import { STORES } from '../StoreOffers'
import { Icon } from '../ui/Icon'
import { Button } from '../ui/Button'

const storeNames = Object.fromEntries(STORES)
const slots = [
  ['CPU','Процессор','chip'], ['GPU','Видеокарта','gpu'],
  ['motherboard','Материнская плата','chip'], ['memory','Оперативная память','chip'],
  ['storage','SSD','drive'], ['psu','Блок питания','shield'],
  ['case','Корпус','box'], ['cooler','Кулер','fan'],
]
const rub = value => `${Number(value || 0).toLocaleString('ru-RU')} ₽`

export function AssemblyPriceNotice({ draft, note }) {
  if(!draft)return null
  return <div className="assembly-price-notice" role="status"><Icon name="shield" size={20}/><div><strong>Предварительная сборка · цены требуют проверки</strong><p>{note||'Площадки сейчас не подтвердили цены и наличие. Состав рассчитан по последним полученным объявлениям; итоговая сумма покупки может измениться.'}</p></div></div>
}

export function PartPriceEvidence({ part }) {
  if(part.price_basis==='reference')return <small className="part-price-unconfirmed">Справочная цена · наблюдалась {part.price_observed_at?new Date(part.price_observed_at).toLocaleDateString('ru-RU'):'дата неизвестна'}. Текущая цена и наличие не подтверждены.</small>
  if(part.price_status==='seller_declared')return <small className="part-price-unconfirmed">Цена и наличие заявлены продавцом; магазинной проверки нет.</small>
  if(part.price_status==='catalog_import')return <small className="part-price-unconfirmed">{part.price_freshness==='stale'?'Прайс старше 24 часов · предварительная цена':'Цена по прайс-листу'} · {part.source_price_at?new Date(part.source_price_at).toLocaleString('ru-RU'):'дата неизвестна'} · наличие и текущая цена не подтверждены.</small>
  if(!part.price_status)return null
  return <small className="part-price-unconfirmed">{part.price_status==='catalog_import' ? 'Цена по прайс-листу · актуальность страницы не подтверждена' : part.price_status==='previously_verified'
    ? `Проверялась ${new Date(part.price_last_verified_at).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · сейчас не подтверждена`
    : 'Цена из полученного объявления · сейчас не подтверждена'}</small>
}

export function AssemblySearchSummary({ report }) {
  if (!report) return null
  const unavailable = [...new Set((report.sources || []).filter(source => source.status === 'unavailable').map(source => source.label))]
  const preferredFailure = (report.sources||[]).find(source=>source.source===report.preferred_source&&source.status==='unavailable')
  if (!report.additional_sources?.length && !report.rejected_offers && !unavailable.length && !report.preferred_source && !report.selection_changes?.length) return null
  return <details className="assembly-search-summary">
    <summary><Icon name="exchange" size={16}/>{report.preferred_source==='avito'?`Приоритет Avito · деталей в сборке: ${report.preferred_parts_count??0} из 8`:'Как подобран состав сборки'}</summary>
    {report.preferred_source==='avito'&&<p>Сначала перебраны варианты на Avito. Остальные площадки используются при нехватке подходящих подтверждённых объявлений.</p>}
    {preferredFailure&&<p>Ответ Avito: {preferredFailure.message}</p>}
    {report.selection_changes?.map(change=><p key={change}>{change}</p>)}
    {report.additional_sources?.length>0 && <p>Дополнительно подключены: {report.additional_sources.map(source=>storeNames[source]||source).join(', ')}.</p>}
    {report.rejected_offers>0 && <p>Не прошли сверку цены и были заменены или исключены: {report.rejected_offers}.</p>}
    {unavailable.length>0 && <p>Не удалось получить часть данных: {unavailable.join(', ')}. Использованы доступные предложения других площадок.</p>}
  </details>
}

export function AssemblyPartialResult({ data, onRetry, onEdit }) {
  const parts = Object.fromEntries((data.parts || []).map(part => [part.type, part]))
  const missing = Object.fromEntries((data.missing_parts || []).map(part => [part.type, part]))
  const count = data.parts?.length || 0
  const plan = data.budget_plan
  return <section className="panel assembly-partial result-reveal" aria-labelledby="partial-build-title">
    <header><span className="section-icon"><Icon name="box" size={23}/></span><div><p className="eyebrow">Ваш план сборки</p><h2 id="partial-build-title">{count?'Нашли часть комплектующих':'Пока недостаточно предложений'}</h2></div><span className="assembly-count"><strong>{count}</strong> / 8 категорий</span></header>
    <div className="assembly-progress" role="progressbar" aria-label="Категории с найденными предложениями" aria-valuemin={0} aria-valuemax={8} aria-valuenow={count}><span style={{width:`${count / 8 * 100}%`}}/></div>
    {plan&&<div className="assembly-budget-overview"><div><span>На весь системный блок</span><strong>{rub(plan.budget)}</strong></div><div><span>Найденные детали</span><strong>{rub(plan.known_parts_subtotal)}</strong></div><div><span>Остаётся на поиск</span><strong>{rub(plan.budget_remaining)}</strong></div></div>}
    <p>Полная совместимая сборка пока не подтверждена. Найденные предложения сохранены ниже; недостающие детали можно поискать в Regard или на бирже. Справочные цены вместо предложений не подставляются.</p>
    {plan&&<p className="field-hint">Бюджеты пустых категорий — план расходов, а не цены товаров. Их сумма вместе с найденными деталями учитывается в общем бюджете. Доставка оплачивается отдельно; доступность товара в вашем городе и возможность доставки не подтверждены.</p>}
    <div className="assembly-slot-grid">{slots.map(([type,label,icon],index)=>{
      const part = parts[type]
      const gap = missing[type]
      return <article className={`assembly-slot ${part?'has-offer':'needs-offer'}`} key={type}>
        <header><span className="slot-icon"><Icon name={icon} size={19}/></span><div><small>{String(index+1).padStart(2,'0')}</small><h3>{label}</h3></div><span className="slot-state">{part?'Предложение':'Нужно найти'}</span></header>
        {part?<><strong className="slot-model">{part.name}</strong><div className="slot-price">{rub(part.price)}<small>{part.price_source}</small></div><PartPriceEvidence part={part}/><a className="slot-primary-link" href={part.price_url} target="_blank" rel="noopener noreferrer">Открыть предложение <Icon name="arrow" size={14}/></a></>:<><strong className="slot-model">{gap?.query || 'Подходящая модель ещё не найдена'}</strong>{gap?.budget_limit!=null&&<div className="slot-price">{rub(gap.budget_limit)}<small>Плановый бюджет категории</small></div>}<p className="slot-hint">{gap?.observed_min_price ? `Есть наблюдения от ${rub(gap.observed_min_price)}. ` : ''}{missingPartNotice(gap)}</p>{Boolean(gap?.links?.length)&&<details className="slot-store-links"><summary>Где можно поискать</summary><div>{gap.links.filter(link=>STORES.some(([id])=>id===link.source)).map(link=><a key={link.source} href={link.url} target="_blank" rel="noopener noreferrer">{link.label} ↗</a>)}</div></details>}</>}
      </article>
    })}</div>
    <AssemblySearchSummary report={data.search_report}/>
    <details className="field-hint assembly-reason"><summary>Что осталось проверить</summary><p>{data.reason}</p><p>{data.note}</p></details>
    <div className="result-actions"><Button type="button" onClick={onRetry}><Icon name="refresh" size={16}/>Повторить поиск</Button><Button type="button" variant="secondary" onClick={onEdit}>Изменить параметры</Button></div>
  </section>
}
