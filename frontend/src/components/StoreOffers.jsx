import { PUBLIC_SOURCES, publicSourceIds } from '../lib/publicSources'
import { Select } from './ui/Select'
import { PriceHistory } from './PriceHistory'
import { sortOffers } from '../lib/catalogView'
import { PriceOriginBadge } from './PriceOriginBadge'
import { CategoryImage } from './CategoryImage'
import { technicalText } from '../lib/listingDetails'
import { GeoControls } from './GeoControls'
import { RegardAdminCatalog } from './RegardAdminCatalog'
import { offerEvidence } from '../lib/offerEvidence.js'
import { LoadingPanel } from './ui/LoadingPanel'
import { useState } from 'react'
import { request } from '../api/client'

export const STORES=PUBLIC_SOURCES
const CATEGORIES=[['CPU','Процессоры'],['GPU','Видеокарты'],['motherboard','Материнские платы'],['memory','RAM'],['storage','Накопители'],['psu','Блоки питания'],['case','Корпуса'],['cooler','Кулеры']]

export function PriceSources({value,onChange}) {
 const selected=publicSourceIds(value)
 return <fieldset className="price-sources source-picker"><legend>Где искать комплектующие</legend><div className="source-segments" role="group" aria-label="Источники предложений">{[['both','Оба источника'],['regard','Regard'],['upgradelab','Биржа UpgradeLab']].map(([id,label])=><button key={id} type="button" aria-pressed={id==='both'?selected.length===2:selected.length===1&&selected[0]===id} onClick={()=>onChange(id==='both'?['regard','upgradelab']:[id])}>{label}</button>)}</div><p className="field-hint">Regard — только разрешённые к показу данные. Биржа — объявления пользователей. Дата и подтверждение цены указаны отдельно.</p></fieldset>
}

export function StoreOffers({initialQuery='',category:fixedCategory,hardwareId,onSelect,initialCategory='GPU',selectLabel='Выбрать'}) {
 const [query,setQuery]=useState(initialQuery),[category,setCategory]=useState(fixedCategory||initialCategory)
 const [sources,setSources]=useState(['regard','upgradelab']),[geo,setGeo]=useState({city_id:null,geo_mode:'all',max_price:null})
 const [data,setData]=useState(null),[sort,setSort]=useState('price'),[busy,setBusy]=useState(false),[error,setError]=useState('')
 async function search(event){event.preventDefault();setBusy(true);setError('');setData(null);try{setData(await request('/api/offers/search',{method:'POST',body:{query,category,sources:publicSourceIds(sources),method:'http',...geo,limit:100,hardware_id:query===initialQuery?hardwareId:undefined}}))}catch(e){setError(e.message)}finally{setBusy(false)}}
 const offers=sortOffers((data?.offers||[]).filter(o=>publicSourceIds(sources).includes(o.source)),sort)
 return <section className="store-offers"><form className="configuration-form" onSubmit={search}>
  <div className="form-grid"><label>Модель<input required minLength="2" maxLength="160" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Например, Ryzen 5 5600"/></label>{!fixedCategory&&<label>Категория<Select value={category} onChange={e=>setCategory(e.target.value)}>{CATEGORIES.map(([id,label])=><option key={id} value={id}>{label}</option>)}</Select></label>}</div>
  <PriceSources value={sources} onChange={setSources}/><GeoControls value={geo} onChange={setGeo}/>
  <button className="primary-btn" disabled={busy||!sources.length}>{busy?'Проверяем доступные данные…':'Найти комплектующие'}</button>
 </form><RegardAdminCatalog onSelect={onSelect}/>{busy&&<LoadingPanel title="Проверяем предложения" description="Если данные недоступны, покажем это отдельно — без подставных цен." cards/>}{error&&<p role="alert" className="error">{error}</p>}
 {data&&<section className="offer-results"><div className="market-filter-foot"><p>{offers.length?`Найдено предложений: ${offers.length}`:'Доступные предложения не получены'}</p><label>Порядок<Select aria-label="Сортировка предложений" value={sort} onChange={e=>setSort(e.target.value)}><option value="price">Сначала дешевле</option><option value="newest">Свежие наблюдения</option><option value="name">По названию</option></Select></label></div>
 {(data.sources||[]).filter(s=>publicSourceIds(sources).includes(s.source)).map(source=><p key={source.source} className="field-hint"><strong>{source.label}: </strong>{source.message}</p>)}
 {!offers.length&&<div className="market-empty"><h4>Сейчас нет доступных предложений</h4><p>Это не означает, что товара нет в продаже. Данные магазина могут быть недоступны или не разрешены к публикации. Попробуйте другую модель или биржу.</p></div>}
 <div className="store-offer-list">{offers.map(offer=><article className="panel" key={offer.id}><CategoryImage category={offer.category} label/><strong>{offer.name}</strong><p className="offer-price">{offer.price_rub.toLocaleString('ru-RU')} ₽</p><PriceOriginBadge origin={offer.origin} verifiedAt={offer.price_verified_at}/>{offer.availability==='unknown'&&<p className="field-hint" role="status">Наличие по прайсу не указано; проверьте у магазина перед покупкой.</p>}<p className="field-hint">{offer.source_label} · {offer.condition==='used'?'Б/у':'Новое'} · {offer.observed_at?new Date(offer.observed_at).toLocaleString('ru-RU'):'Дата неизвестна'}</p><p className="field-hint">{offerEvidence(offer)}</p><details className="offer-evidence"><summary>Что известно о предложении</summary><p>{offer.technical_assessment&&technicalText(offer.technical_assessment)}</p><p>{offer.price_note||'Перед покупкой проверьте цену, наличие и доставку.'}</p></details><PriceHistory productId={offer.catalog_product_id}/><div className="result-actions"><a href={offer.url} target="_blank" rel="noopener noreferrer">Открыть предложение</a>{onSelect&&<button type="button" className="secondary-btn" disabled={offer.optimizer_eligible===false} onClick={()=>onSelect({...offer,selection_scope:geo})}>{typeof selectLabel==='function'?selectLabel(offer):selectLabel}</button>}</div></article>)}</div><p className="field-hint">{data.note}</p></section>}</section>
}
