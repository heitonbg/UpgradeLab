import { useState } from 'react'
import { buildMetric, buildTrust } from '../../lib/buildPresentation'
import { saveAndShareBuild } from '../../lib/share'
import { Button } from '../ui/Button'

const labels={CPU:'Процессор',GPU:'Видеокарта',motherboard:'Материнская плата',memory:'Оперативная память',storage:'Накопитель',psu:'Блок питания',case:'Корпус',cooler:'Кулер'}
export function BuildSummary({result,onSave,saving}) {
 const [shareMessage,setShareMessage]=useState('')
 const final=buildTrust(result).kind==='verified',metric=buildMetric(result)
 async function share(){
  const parts=(result.parts||[]).map(part=>({category:labels[part.type]||part.type,name:part.name,price:Number.isFinite(part.price)?part.price:null,url:part.price_url||'',image_url:''}))
  try{await saveAndShareBuild({v:1,parts,game:result.game||result.config?.game||null,fps:result.fps??null});setShareMessage('Сборка сохранена. Ссылка скопирована.')}catch(error){setShareMessage(error.message||'Не удалось сохранить и скопировать сборку.')}

 }
 return <aside className="build-summary" aria-label="Итоговая сборка"><div className="summary-title"><h3>Ваша сборка</h3><span>{final?'Сверена':'Предварительная'}</span></div><p className="summary-count">{result.parts.length} компонентов</p><div className="summary-total"><small>{final?'Стоимость по проверенным предложениям':'Предварительная стоимость'}</small><strong>{result.total_price.toLocaleString('ru-RU')} ₽</strong></div>{result.delivery_cost_unknown&&<p className="field-hint">Доставка не рассчитана. Итог покупки неизвестен.</p>}<dl><div><dt>Остаток бюджета</dt><dd>{result.remaining_budget.toLocaleString('ru-RU')} ₽</dd></div><div><dt>{metric.kind==='cpu'?'Ориентир CPU Mark':'Прогноз FPS'}</dt><dd>{metric.value}</dd></div></dl><p className="field-hint">{metric.note} {final?'Цена и наличие могут измениться.':'Цены, наличие и технические ограничения требуют проверки.'}</p><Button type="button" variant="secondary" onClick={share}>Поделиться сборкой</Button>{shareMessage&&<p role="status" className="field-hint">{shareMessage}</p>}{onSave&&<Button type="button" loading={saving} onClick={onSave}>{saving?'Сохраняем…':'Сохранить сборку'}</Button>}</aside>
}
