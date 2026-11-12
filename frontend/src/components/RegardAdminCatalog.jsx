import { useState } from 'react'
import { request } from '../api/client'
import { Select } from './ui/Select'
import { RegardCatalog } from './RegardCatalog'

const CATEGORY_LABELS={CPU:'Процессоры',GPU:'Видеокарты',motherboard:'Материнские платы',memory:'Оперативная память',storage:'Накопители',psu:'Блоки питания',case:'Корпуса',cooler:'Охлаждение'}
const LOCAL_HOSTS=new Set(['localhost','127.0.0.1','::1'])

export function RegardAdminCatalog({onSelect}){
 const params=new URLSearchParams(window.location.search)
 const local=LOCAL_HOSTS.has(window.location.hostname)&&params.get('regard_admin')==='1'
 const [token,setToken]=useState(''),[query,setQuery]=useState(''),[category,setCategory]=useState(''),[offset,setOffset]=useState(0)
 const [data,setData]=useState(null),[history,setHistory]=useState({}),[busy,setBusy]=useState(false),[error,setError]=useState('')
 if(!local)return <RegardCatalog onSelect={onSelect}/>
 const headers={'X-UpgradeLab-Catalog-Admin':token}
 async function load(nextOffset=0){
  if(!token.trim()){setError('Укажите локальный ключ владельца.');return}
  setBusy(true);setError('')
  try{const params=new URLSearchParams({q:query.trim(),offset:String(nextOffset),limit:'60'});if(category)params.set('category',category);setData(await request('/api/admin/catalog/regard?'+params,{headers}));setOffset(nextOffset);setHistory({})}
  catch(e){setError(e.status===403?'Ключ не подошёл. Проверьте локальный файл ключа.':e.message)}finally{setBusy(false)}
 }
 async function loadHistory(key){
  if(history[key]?.data||history[key]?.busy)return
  setHistory(current=>({...current,[key]:{busy:true}}))
  try{const value=await request(`/api/admin/catalog/regard/${encodeURIComponent(key)}/price-history?days=14`,{headers});setHistory(current=>({...current,[key]:{data:value}}))}
  catch(e){setHistory(current=>({...current,[key]:{error:e.status===404?'История недоступна.':e.message}}))}
 }
 return <details className="regard-admin-panel">
  <summary>Закрытый локальный каталог Регарда</summary>
  <p className="field-hint">Только локальный просмотр для владельца проекта. Эти импортированные цены и товары не публикуются и не участвуют в обычном поиске или подборе.</p>
  <p className="field-hint">Локальный ключ находится в `.artifacts/regard-admin-preview-20261111/admin-token.txt`. Не отправляйте этот файл и его содержимое другим людям.</p>
  <form className="regard-admin-toolbar" onSubmit={e=>{e.preventDefault();load(0)}}>
   <label className="regard-admin-token">Ключ владельца<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="Вставьте ключ из локального файла"/></label>
   <label>Поиск товара<input value={query} maxLength={120} onChange={e=>setQuery(e.target.value)} placeholder="Название или производитель"/></label>
   <label>Категория<Select value={category} onChange={e=>setCategory(e.target.value)}><option value="">Все категории</option>{Object.entries(CATEGORY_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Select></label>
   <button type="submit" className="primary-btn" disabled={busy}>{busy?'Загружаю…':'Показать товары'}</button>
  </form>
  {error&&<p role="alert" className="error">{error}</p>}
  {data&&<>
   <p className="field-hint">{data.source_label} · прайс от {data.source_date||'дата неизвестна'} · {data.total.toLocaleString('ru-RU')} найдено из {data.catalog_product_count.toLocaleString('ru-RU')} · связанных предложений: {data.linked_store_offer_count.toLocaleString('ru-RU')}</p>
   {!data.items.length&&<p>По этому запросу товаров нет.</p>}
   <div className="regard-admin-grid">{data.items.map(item=>{const state=history[item.product_key];return <article className="regard-admin-card" key={item.product_key}>
    <div className="regard-admin-photo">{item.image_url?<><span>Фото недоступно</span><img src={item.image_url} alt={`${item.manufacturer||''} ${item.name}`} loading="lazy" referrerPolicy="no-referrer" onError={e=>{e.currentTarget.hidden=true}}/></>:<span>Фото в прайсе не указано</span>}</div>
    <p className="eyebrow">{CATEGORY_LABELS[item.category]||item.category||'Категория не указана'}</p>
    <h3>{item.name}</h3>
    {item.manufacturer&&<p className="field-hint">Производитель: {item.manufacturer}</p>}
    <p className="regard-admin-price">{item.price_rub===null?'Цена не указана':`${item.price_rub.toLocaleString('ru-RU')} ₽`}</p>
    <p className="field-hint">Прайс на {item.price_date?new Date(item.price_date).toLocaleDateString('ru-RU'):'дата не указана'} · наличие не проверялось</p>
    <p className="regard-admin-status">{item.status}</p>
    <p className="field-hint">{item.store_offer_id?'Есть связанная запись StoreOffer':'В StoreOffer не материализован'}</p>
    <div className="result-actions">{item.product_url?<a href={item.product_url} target="_blank" rel="noopener noreferrer">Страница Регарда</a>:<span className="field-hint">Ссылка в прайсе отсутствует</span>}<button type="button" className="text-btn" onClick={()=>loadHistory(item.product_key)}>История цены</button></div>
    {state?.busy&&<p role="status">Загружаю историю…</p>}{state?.error&&<p className="field-hint">{state.error}</p>}{state?.data&&<div className="regard-admin-history"><p>{state.data.note}</p>{state.data.observations.length?state.data.observations.map(point=><span key={point.date}>{new Date(point.date+'T12:00:00').toLocaleDateString('ru-RU')}: {point.price_rub.toLocaleString('ru-RU')} ₽</span>):<span>Исторических точек за последние 14 дней нет.</span>}</div>}
   </article>})}</div>
   <div className="regard-admin-pagination"><button type="button" className="secondary-btn" disabled={!offset||busy} onClick={()=>load(Math.max(0,offset-60))}>Назад</button><span>{offset+1}–{Math.min(offset+60,data.total)} из {data.total}</span><button type="button" className="secondary-btn" disabled={offset+60>=data.total||busy} onClick={()=>load(offset+60)}>Дальше</button></div>
   <p className="field-hint">Административный просмотр не подтверждает текущую цену, фактическое наличие, право публичного показа или коммерческого использования.</p>
  </>}
 </details>
}
