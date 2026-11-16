import { useState } from 'react'
import { request } from '../api/client'

const day = value => Date.parse(`${value}T00:00:00Z`) / 86400000
const money = value => `${value.toLocaleString('ru-RU')} ₽`

export function PriceHistory({ productId }) {
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 async function load(days){setBusy(true);setError('');try{setData(await request(`/api/products/${encodeURIComponent(productId)}/price-history?days=${days}`))}catch{setError('История недоступна.')}finally{setBusy(false)}}
 if(!productId)return null
 const rows=data?.observations||[]
 const min=rows.length?Math.min(...rows.map(row=>row.price_rub)):0
 const max=rows.length?Math.max(...rows.map(row=>row.price_rub)):0
 const first=rows.length?day(rows[0].date):0
 const last=rows.length?day(rows.at(-1).date):0
 const points=rows.map(row=>({row,x:24+(day(row.date)-first)*352/Math.max(1,last-first),y:102-(row.price_rub-min)*76/Math.max(1,max-min)}))
 return <details className="price-history" onToggle={event=>{if(event.currentTarget.open&&!data&&!busy)load(14)}}><summary>График цены</summary><div className="result-actions">{[7,14].map(days=><button type="button" className="text-btn" key={days} disabled={busy} onClick={()=>load(days)}>{days} дней</button>)}</div>{busy&&<p role="status">Загружаем историю…</p>}{error&&<p role="alert">{error}</p>}{data&&<><p className="field-hint">{data.note}</p>{rows.length?<><figure className="price-history-figure"><svg viewBox="0 0 400 130" role="img" aria-label={`Наблюдения цены: от ${money(rows[0].price_rub)} до ${money(rows.at(-1).price_rub)}`}><title>История наблюдаемых цен</title><line x1="24" x2="376" y1="113" y2="113" stroke="currentColor" opacity=".3"/>{points.slice(1).map((point,index)=>{const previous=points[index];return <line key={`line-${point.row.date}`} x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke="currentColor" strokeWidth="2" strokeDasharray={day(point.row.date)-day(previous.row.date)>1?'4 4':undefined} opacity=".7"/>})}{points.map(point=><circle key={point.row.date} cx={point.x} cy={point.y} r="4.5" fill="currentColor"><title>{point.row.date}: {money(point.row.price_rub)}</title></circle>)}</svg><figcaption>{rows[0].date} · {money(rows[0].price_rub)} → {rows.at(-1).date} · {money(rows.at(-1).price_rub)}</figcaption></figure><p className="field-hint">Минимум {money(data.minimum)} · максимум {money(data.maximum)} · среднее по наблюдениям {money(Math.round(data.mean))}{data.change_rub!==null&&` · изменение ${money(data.change_rub)}`}</p><ul className="field-hint">{rows.map(row=><li key={row.date}>{row.date}: {money(row.price_rub)}</li>)}</ul><p className="field-hint">Пунктиром отмечены дни без наблюдений. Цена и наличие в магазине сейчас не подтверждены.</p></>:<p>За этот период наблюдений нет. График появится после повторного импорта прайса в другой день.</p>}</>}</details>
}
