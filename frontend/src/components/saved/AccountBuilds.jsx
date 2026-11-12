import { useEffect, useRef, useState } from 'react'
import { request } from '../../api/client'
import { fpsText } from '../../lib/performance'
import { currentItemPrice, currentSavedTotal, savedItemState, money, reviewTime } from '../../lib/savedPrices'

const date = value => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('ru-RU') : 'Дата неизвестна'

function SavedEntry({ build, onRemove, onRecalculate, now }) {
  const [review, setReview] = useState(build.price_review)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [redoing,setRedoing]=useState(false)
  useEffect(() => setReview(build.price_review), [build])
  const result = build.result || {}
  const config = build.config || {}
  const assembly = config.scenario === 'build'
  const historical = review?.historical_total ?? result.total_price ?? result.avg_price
  const received = useRef({review, at: performance.now()})
  if (received.current.review !== review) received.current = {review, at: performance.now()}
  const priceNow = reviewTime(review, performance.now() - received.current.at)
  const current = currentSavedTotal(review, priceNow)
  const latest=review?.items?.length&&review.items.every(item=>typeof item.latest_price==='number'&&Number.isFinite(item.latest_price)&&item.latest_price>=0&&item.latest_observed_at)?review.items.reduce((sum,item)=>sum+item.latest_price,0):null
  async function redo(){setRedoing(true);setError('');try{await onRecalculate(build)}catch(e){setError(e.message)}finally{setRedoing(false)}}
  async function check() {
    setBusy(true); setError('')
    try {
      const checked = await request(`/api/builds/${build.id}/prices`, {method:'POST'})
      setReview(checked.price_review)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  return <details className="saved-account-build">
    <summary>{assembly ? 'Сборка с нуля' : 'Апгрейд'} · {config.game} · {assembly
      ? fpsText(result.fps,result.fps_outlook)
      : `~${result.current_fps} → ~${result.upgraded_fps}`} FPS на момент расчёта</summary>
    <p className="field-hint">Сохранено {date(build.created_at)} · {config.mode}</p>
    <div className="saved-price-ledger"><div><span>При сохранении</span><strong>{money(historical)}</strong><small>Историческая стоимость</small></div><div><span>Последнее наблюдение</span><strong>{money(latest)}</strong><small>Не подтверждает текущую цену</small></div><div><span>Подтверждено сейчас</span><strong>{money(current)}</strong><small>По действующим правилам свежести</small></div></div>
    <p className="field-hint">Статус сохранённого расчёта: {result.status || 'не указан'}. Он относится к моменту расчёта и не подтверждает сегодняшние цены. Доставка и персональные скидки не учтены.</p>
    <p className="field-hint">{review?.note || 'Это исторический снимок. Свежесть цен неизвестна.'}</p>
    {review?.items?.map((item,index) => <div className="account-item" key={index}>
      <div><strong>{item.name}</strong>
        <p>При сохранении: {money(item.historical_price)} · наблюдение {date(item.observed_at)}</p>
        {item.verified_at && <p className="field-hint">Подтверждение в снимке: {date(item.verified_at)} (история)</p>}
        <p>Последнее наблюдение: {money(item.latest_price)} · {date(item.latest_observed_at)}</p>
        <p>Актуальная цена: {money(currentItemPrice(item,priceNow))}. {savedItemState(item,priceNow)}</p>
        {item.changed && <p className="field-hint">Цена изменилась. Историческая сумма сохранена.</p>}
        {item.url && <a href={item.url} target="_blank" rel="noopener noreferrer">Открыть сохранённое предложение</a>}
      </div>
    </div>)}
    {!review?.items?.length && <p className="field-hint">В старом снимке нет достаточных данных для проверки отдельных цен.</p>}
    {result.current_component_price != null && <p className="field-hint">Историческая оценка продажи своей детали: {money(result.current_component_price)}. Это не подтверждённая выручка и не часть цены покупки.</p>}
    {result.compatibility_notes?.length > 0 && <details><summary>Примечания сохранённого расчёта</summary><ul className="field-hint">{result.compatibility_notes.map((note,index)=><li key={index}>{note}</li>)}</ul></details>}
    <p className="field-hint">Проверено по серверным данным: {date(review?.evaluated_at)}. Эта проверка не обращается к магазинам. Ссылку можно проверить вручную; ручная проверка не меняет статус на сервере.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="result-actions">{onRecalculate&&build.config&&<button className="primary-btn" disabled={redoing} onClick={redo}>{redoing?'Рассчитываем…':'Создать новый расчёт'}</button>}
      <button className="secondary-btn" disabled={busy} onClick={check}>{busy ? 'Проверяем…' : 'Проверить по серверным предложениям'}</button>
      <button className="secondary-btn" onClick={()=>onRemove(build.id)}>Удалить сохранённый результат</button>
    </div>
  </details>
}

export function AccountBuilds({ builds, onRemove, onRecalculate }) {
  const [now,setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()),1000)
    return () => clearInterval(timer)
  },[])
  return <section className="panel"><h2>Сохранённые сборки и расчёты</h2>
    {builds.length ? builds.map(build=><SavedEntry key={build.id} build={build} onRemove={onRemove} onRecalculate={onRecalculate} now={now}/>)
      : <p className="empty-copy">Сохраните результат расчёта — он будет доступен в аккаунте с другого устройства.</p>}
  </section>
}
