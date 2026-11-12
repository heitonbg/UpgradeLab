import { useEffect, useRef, useState } from 'react'
import { request } from '../api/client'
export function ExternalProductSearch({ model, category, sources, cityId, maxPrice }) {
 const [job,setJob]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const timer=useRef(null),generation=useRef(0)
 useEffect(()=>()=>{generation.current++;clearTimeout(timer.current)},[])
 async function start(){
  const current=++generation.current;clearTimeout(timer.current);setBusy(true);setError('');setJob(null)
  const deadline=Date.now()+120000
  async function receive(value){
   if(current!==generation.current)return
   setJob(value)
   if(['queued','running'].includes(value.status)){
    if(Date.now()>deadline){setBusy(false);setError('Проверка заняла больше времени. Повторите позже.');return}
    timer.current=setTimeout(async()=>{try{await receive(await request(`/api/product-search/${value.id}`))}catch(e){if(current===generation.current){setError(e.message);setBusy(false)}}},1500)
   }else setBusy(false)
  }
  try{await receive(await request('/api/product-search',{method:'POST',body:{model,category,sources:sources.filter(s=>['avito','dns','citilink','ozon','wb'].includes(s)),city_id:cityId||null,max_price:maxPrice||null}}))}
  catch(e){if(current===generation.current){setBusy(false);setError(e.message)}}
 }
 const result=job?.result
 return <details><summary>AI-поиск внешних карточек</summary><p className="field-hint">Отдельный поиск после входа. Ссылки не подтверждают цену и наличие и не участвуют в подборе ПК.</p><button type="button" className="secondary-btn" disabled={busy||model.trim().length<2||!sources.some(s=>['avito','dns','citilink','ozon','wb'].includes(s))} onClick={start}>{busy?'Ищем карточки…':'Найти карточки с AI'}</button>{error&&<p role="alert" className="error">{error}</p>}{result&&<><p className="field-hint">{result.status==='completed'?(result.offers?.length?'Найдены ссылки; стоимость требует отдельной проверки.':'Подходящие карточки не найдены.'):'Поиск сейчас недоступен или временно ограничен. Попробуйте обычный поиск площадок.'}</p>{result.offers?.map(item=><p key={item.source_url}><a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.display_title}</a> · Цена и наличие не подтверждены</p>)}</>}</details>
}
