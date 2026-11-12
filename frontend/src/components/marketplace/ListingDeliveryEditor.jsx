import { Select } from '../ui/Select'
import { request } from '../../api/client'
import { useState,useEffect } from 'react'
import { CityPicker } from '../CityPicker'
export function ListingDeliveryEditor({value,onChange}) {
 const [candidate,setCandidate]=useState(null)
 const v=value||{mode:'unknown',city_ids:[],cost_rub:null,cost_mode:'unknown',terms:'',city_labels:{}}
 const change=patch=>onChange({...v,...patch})
 useEffect(()=>{
  const unknown=(v.city_ids||[]).filter(id=>!v.city_labels?.[id]);if(!unknown.length)return
  let alive=true
  Promise.all(unknown.map(id=>request('/api/cities?q='+encodeURIComponent(id)))).then(groups=>{if(alive){const labels={...v.city_labels};groups.flat().forEach(c=>labels[c.city_id]=c.name+' · '+c.region);change({city_labels:labels})}}).catch(()=>{})
  return()=>{alive=false}
 },[JSON.stringify(v.city_ids)])
 return <fieldset className="delivery-fields" aria-label="Условия передачи"><label>Способ получения<Select aria-label="Способ получения" value={v.mode} onChange={e=>change({mode:e.target.value,cost_rub:null,cost_mode:'unknown'})}><option value="unknown">Пока не указано</option><option value="meetup">Только личная встреча</option><option value="pickup">Самовывоз в моём городе</option><option value="cities">Отправка в выбранные города</option><option value="russia">Отправка по России</option></Select></label>
 {v.mode==='cities'&&<><CityPicker label="Город доставки" value={candidate} onChange={setCandidate}/><button type="button" className="text-btn" disabled={!candidate||(v.city_ids||[]).includes(candidate)} onClick={()=>change({city_ids:[...(v.city_ids||[]),candidate]})}>Добавить город</button><ul>{(v.city_ids||[]).map(city=><li key={city}>{v.city_labels?.[city]||city.replace('ru:','')} <button type="button" className="text-btn" onClick={()=>change({city_ids:v.city_ids.filter(c=>c!==city)})}>Убрать город</button></li>)}</ul></>}
 {['cities','russia'].includes(v.mode)&&<><label>Стоимость отправки<Select aria-label="Стоимость отправки" value={v.cost_mode||'unknown'} onChange={e=>change({cost_mode:e.target.value,cost_rub:e.target.value==='free'?0:null})}><option value="unknown">Уточняется отдельно</option><option value="free">Бесплатно — явно предлагаю</option><option value="fixed">Известная сумма</option></Select></label>{v.cost_mode==='fixed'&&<label>Доставка, ₽<input required type="number" min="1" max="1000000" step="1" value={v.cost_rub??''} onChange={e=>change({cost_rub:e.target.value===''?null:Number(e.target.value)})}/></label>}</>}
 <label>Дополнительные условия<textarea maxLength={500} rows={2} value={v.terms||''} onChange={e=>change({terms:e.target.value})}/></label><p className="field-hint">Это ваше заявление, а не подтверждение перевозчика. Неизвестная стоимость не равна нулю. Для всех вариантов возможен самовывоз в городе объявления.</p></fieldset>
}
