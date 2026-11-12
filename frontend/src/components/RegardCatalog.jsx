import { useEffect, useState } from 'react'
import { request } from '../api/client'
import { PriceHistory } from './PriceHistory'
import { CategoryImage } from './CategoryImage'
import { Select } from './ui/Select'
import { catalogQuery } from '../lib/catalogView'

const categories=[['','Все категории'],['CPU','Процессоры'],['GPU','Видеокарты'],['motherboard','Материнские платы'],['memory','Память'],['storage','Накопители'],['psu','Блоки питания'],['case','Корпуса'],['cooler','Кулеры']]

export function RegardCatalog({onSelect}) {
 const [q,setQ]=useState(''),[category,setCategory]=useState(''),[page,setPage]=useState(1)
 const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let active=true;setBusy(true);setError('');request(`/api/catalog/products?${catalogQuery(q,category,page)}`).then(value=>{if(active)setData(value)}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setBusy(false)});return()=>{active=false}},[q,category,page])
 const pages=Math.max(1,Math.ceil((data?.total||0)/24))
 return <section className="panel regard-public-catalog" aria-labelledby="regard-catalog-title">
  <header className="page-heading"><p className="eyebrow">Официальный XLSX прайс · Регард</p><h2 id="regard-catalog-title">Каталог комплектующих</h2><p>Цены и дата взяты из последнего импорта. Наличие по этому прайсу не указано и требует проверки у магазина.</p></header>
  <form className="configuration-form" onSubmit={e=>e.preventDefault()}><div className="form-grid"><label>Поиск по модели<input value={q} maxLength={120} onChange={e=>{setPage(1);setQ(e.target.value)}} placeholder="Например, Ryzen 5 5600"/></label><label>Категория<Select value={category} onChange={e=>{setPage(1);setCategory(e.target.value)}}>{categories.map(([value,label])=><option value={value} key={value}>{label}</option>)}</Select></label></div></form>
  {error&&<p role="alert" className="error">Каталог сейчас недоступен: {error}</p>}{busy&&!data&&<p>Загружаем каталог…</p>}
  {data&&<><p className="field-hint">Найдено товаров: {data.total.toLocaleString('ru-RU')} · страница {data.page} из {pages}. Фото отдельных товаров в прайсе отсутствуют.</p>{!data.items.length&&!busy&&<p className="empty-copy">По этому запросу товаров нет.</p>}
   <div className="store-offer-list">{data.items.map(item=><article className="panel" key={item.product_key}><CategoryImage category={item.category} label/><strong>{item.name}</strong>{item.manufacturer&&<p>{item.manufacturer}</p>}<p className="offer-price">{item.price_rub.toLocaleString('ru-RU')} ₽</p><p className="field-hint">{item.availability_label} · дата прайса {item.price_date?new Date(item.price_date).toLocaleString('ru-RU'):'не указана'}</p>{!item.price_fresh&&<p className="field-hint" role="status">{item.price_freshness==='stale'?'Цена старше 24 часов; разрешена только для предварительного расчёта.':'Цена вне окна предварительного расчёта; показана для истории.'}</p>}{item.availability==='unknown'&&<p className="field-hint" role="status">Предварительная цена: наличие и текущая цена в магазине не подтверждены.</p>}<PriceHistory productId={item.product_key}/><div className="result-actions">{item.product_url?<a href={item.product_url} target="_blank" rel="noopener noreferrer">Открыть в Регарде</a>:<span className="field-hint">Ссылка на товар не подтверждена</span>}{item.preliminary_candidate&&<button type="button" className="secondary-btn" onClick={()=>onSelect?.({id:item.offer_id,source:'regard',category:item.category,name:item.name,price_rub:item.price_rub,selection_scope:{}})}>В предварительную сборку</button>}</div></article>)}</div>
   <div className="result-actions" aria-label="Страницы каталога"><button className="secondary-btn" disabled={page<=1||busy} onClick={()=>setPage(value=>value-1)}>Назад</button><span>{page} / {pages}</span><button className="secondary-btn" disabled={page>=pages||busy} onClick={()=>setPage(value=>value+1)}>Дальше</button></div>
  </>}
 </section>
}
