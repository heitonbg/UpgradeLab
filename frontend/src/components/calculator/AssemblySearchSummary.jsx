import { STORES } from '../StoreOffers'
import { Icon } from '../ui/Icon'
import { Button } from '../ui/Button'

const storeNames = Object.fromEntries(STORES)

export function AssemblyPriceNotice({ draft, note }) {
  if(!draft)return null
  return <div className="assembly-price-notice" role="status"><Icon name="shield" size={20}/><div><strong>Предварительная сборка · цены требуют проверки</strong><p>{note||'Площадки сейчас не подтвердили цены и наличие. Состав рассчитан по последним полученным объявлениям; итоговая сумма покупки может измениться.'}</p></div></div>
}

export function PartPriceEvidence({ part }) {
  if(!part.price_status)return null
  return <small className="part-price-unconfirmed">{part.price_status==='previously_verified'
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
  return <section className="panel assembly-partial result-reveal" aria-labelledby="partial-build-title">
    <header><span className="section-icon"><Icon name="search" size={23}/></span><div><p className="eyebrow">Результаты поиска</p><h2 id="partial-build-title">{data.parts?.length?'Найденные предложения':'Площадки не дали получить объявления'}</h2></div></header>
    <p>{data.message}</p>
    <AssemblySearchSummary report={data.search_report}/>
    {data.parts?.length>0&&<><h3>Найдены предложения: {data.parts.length} из 8 категорий</h3><p className="field-hint">{data.note}</p><div className="partial-offers">{data.parts.map(part=><article key={part.type}><strong>{part.name}</strong><span>{part.price.toLocaleString('ru-RU')} ₽ · {part.price_source}</span><PartPriceEvidence part={part}/><a href={part.price_url} target="_blank" rel="noopener noreferrer">Открыть товар ↗</a></article>)}</div></>}
    <h3>{data.parts?.length===8?'Для завершения нужно уточнить совместимость или бюджет':'Что осталось найти'}</h3>
    <div className="partial-missing">{data.missing_parts?.map(item=><details key={item.type}><summary>{item.label}<small>Найти на площадках</small></summary><p>{item.query}</p><div>{item.links.map(link=><a key={link.source} href={link.url} target="_blank" rel="noopener noreferrer">{link.label} ↗</a>)}</div></details>)}</div>
    <details className="field-hint"><summary>Что помешало завершить подбор</summary><p>{data.reason}</p></details>
    <div className="result-actions"><Button type="button" onClick={onRetry}>Повторить подбор</Button><Button type="button" variant="secondary" onClick={onEdit}>Изменить параметры</Button></div>
  </section>
}
