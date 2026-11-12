import { useConfirm } from '../ui/useConfirm'
import { Select } from '../ui/Select'
import { ErrorState } from '../ui/ErrorState'
import { marketDataState,marketCountLabel,validPriceRange } from '../../lib/marketState'
import { CityPicker } from '../CityPicker'
import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Icon } from '../ui/Icon'
import { ListingGrid } from './ListingGrid'
import { ListingForm } from './ListingForm'
import { ListingDetail } from './ListingDetail'
import { CATEGORIES, filterListings } from '../../lib/marketplace'

const initialFilters = {search:'',deal:'all',category:'all',condition:'all',min:'',max:'',sort:'newest',city_id:null}

export function MarketplaceSection({ listings=[], loading, error, onCreate, onRetry, user, onLogin, intent, onConsumed, ownedIds=[], onEdit }) {
  const [filters,setFilters] = useState(()=>({...initialFilters,city_id:new URLSearchParams(window.location.search).get('city')||null}))
  const [isModalOpen,setIsModalOpen] = useState(false)
  const [selectedListing,setSelectedListing] = useState(null)
  useEffect(()=>{
    const id=Number(new URLSearchParams(window.location.search).get('listing'))
    const item=listings.find(l=>l.id===id)
    if(item)setSelectedListing(item)
  },[listings])
  const [draft,setDraft] = useState(null)
  const [draftDirty,setDraftDirty] = useState(false)
  const {confirm,confirmation}=useConfirm()
  const closeDraft=async()=>{if(!draftDirty||await confirm({title:'Закрыть без сохранения?',description:'Изменения в объявлении будут потеряны.',cancel:'Продолжить редактирование',action:'Не сохранять'}))setIsModalOpen(false)}
  useEffect(()=>{
    if(!intent)return
    setFilters(current=>({...initialFilters,city_id:current.city_id,search:intent.search||''}))
    if(intent.draft){setDraft(intent.draft);setIsModalOpen(true)}
    onConsumed?.()
  },[intent,onConsumed])
  useEffect(()=>{
    const url=new URL(window.location.href)
    if(filters.city_id)url.searchParams.set('city',filters.city_id)
    else url.searchParams.delete('city')
    window.history.replaceState(null,'',url.pathname+url.search+url.hash)
  },[filters.city_id])
  const set = key => event => setFilters({...filters,[key]:event.target.value})
  const changeDeal = deal => setFilters({...filters,deal,...(deal==='exchange'?{min:'',max:''}:{})})
  const create = () => {setDraft(null);setIsModalOpen(true)}
  const hasFilters = Object.entries(initialFilters).some(([key,value]) => key!=='sort' && filters[key]!==value)
  const filtered = filterListings(listings,filters)
  const invalidPrice = !validPriceRange(filters.min,filters.max)
  const dataState=marketDataState({loading,error,count:listings.length})
  const countsKnown=!['loading','error'].includes(dataState)
  const [filtersOpen,setFiltersOpen]=useState(false)
  const counts = {all:listings.length,sale:listings.filter(l=>(l.listing_type||'sale')==='sale').length,exchange:listings.filter(l=>l.listing_type==='exchange').length}
  async function handleCreate(data){await onCreate(data);setIsModalOpen(false)}

  return <section className="marketplace-browser">{confirmation}
    <div className="market-section-heading page-heading"><div><p className="eyebrow">Объявления сообщества</p><h1>Биржа комплектующих</h1><p>Комплектующие от других пользователей — для продажи и обмена.</p></div><Button type="button" onClick={create}><Icon name="plus" size={17}/>Разместить объявление</Button></div>
    <button type="button" className="secondary-btn market-filter-toggle" aria-expanded={filtersOpen} aria-controls="market-filters" onClick={()=>setFiltersOpen(v=>!v)}>Фильтры{hasFilters?' · выбраны':''}</button>
    <section id="market-filters" className={`market-controls ${filtersOpen?'is-open':''}`} aria-label="Поиск и фильтры объявлений">
      <div className="market-controls-top"><div className="deal-tabs" role="group" aria-label="Продажа или обмен">{[['all','Все объявления'],['sale','Продажа'],['exchange','Обмен']].map(([key,label])=><button type="button" key={key} aria-pressed={filters.deal===key} className={filters.deal===key?'selected':''} onClick={()=>changeDeal(key)}>{label}<span aria-label={countsKnown?`${counts[key]} объявлений`:'Количество неизвестно'}>{countsKnown?counts[key]:'—'}</span></button>)}</div><label className="market-sort"><span>Порядок</span><Select aria-label="Сортировка объявлений" value={filters.sort} onChange={set('sort')}><option value="newest">Сначала новые</option><option value="price">Сначала дешевле</option></Select></label></div>
      <div className="market-search"><Icon name="search"/><input type="search" aria-label="Поиск объявлений" placeholder="Модель или название: например, RTX 4060" value={filters.search} onChange={set('search')}/>{filters.search&&<button type="button" aria-label="Очистить поиск" onClick={()=>setFilters({...filters,search:''})}>×</button>}</div>
      <CityPicker label="Город продавца" value={filters.city_id} onChange={city_id=>setFilters(current=>({...current,city_id}))}/><div className="market-filter-grid"><label><span>Комплектующее</span><Select value={filters.category} onChange={set('category')}>{CATEGORIES.map(([key,label])=><option key={key} value={key}>{label}</option>)}</Select></label><label><span>Состояние</span><Select value={filters.condition} onChange={set('condition')}><option value="all">Любое состояние</option><option value="new">Новое</option><option value="used">Б/у</option><option value="broken">Неисправное / на запчасти</option></Select></label><fieldset className="market-price"><legend>Цена, ₽</legend><div><input aria-invalid={invalidPrice} aria-label="Цена от" type="number" min="0" placeholder="От" disabled={filters.deal==='exchange'} value={filters.min} onChange={set('min')}/><span>—</span><input aria-invalid={invalidPrice} aria-label="Цена до" type="number" min="0" placeholder="До" disabled={filters.deal==='exchange'} value={filters.max} onChange={set('max')}/></div></fieldset></div>
      <div className="market-filter-foot"><span><Icon name="filters" size={14}/>{invalidPrice?'Проверьте диапазон цены':marketCountLabel(dataState,filtered.length)}</span>{hasFilters&&<button type="button" className="text-btn" onClick={()=>setFilters(initialFilters)}>Сбросить фильтры</button>}</div>
      {filters.deal==='exchange'&&<p className="field-hint">Для обмена цена не ограничивается: условия указаны в объявлении.</p>}
      {invalidPrice&&<p className="filter-validation" role="status">Цена «до» должна быть не меньше цены «от».</p>}
    </section>
    <div className="market-results-area" aria-busy={loading}>
      {error&&!loading&&<ErrorState title={listings.length?'Не удалось обновить объявления':'Не удалось загрузить объявления'} description={listings.length?'Показана последняя успешная загрузка. Цены и наличие могли измениться; фильтры сохранены.':'Сервис временно недоступен. Повторите загрузку — выбранные фильтры сохранятся.'} onRetry={onRetry}/>}
      {invalidPrice?<p className="filter-validation" role="status">Укажите неотрицательную цену и корректный диапазон.</p>:dataState!=='error'&&<ListingGrid listings={filtered} loading={loading&&!listings.length} hasFilters={hasFilters} onReset={()=>setFilters(initialFilters)} onCreate={create} emptyMessage={listings.length?'Попробуйте другое название или расширьте фильтры.':undefined} onClick={setSelectedListing}/>}
    </div>
    <Modal open={isModalOpen} onClose={closeDraft} title="Новое объявление" size="lg">{user?<ListingForm key={draft?.title||'new'} initial={draft||{city_id:filters.city_id}} onSubmit={handleCreate} onCancel={closeDraft} onDirtyChange={setDraftDirty}/>:<div className="login-prompt"><span className="empty-icon"><Icon name="box" size={30}/></span><h4>Разместите свою комплектующую</h4><p>Войдите в аккаунт, чтобы опубликовать объявление и управлять им из личного кабинета.</p><Button type="button" onClick={()=>{setIsModalOpen(false);onLogin()}}>Войти в аккаунт<Icon name="arrow" size={16}/></Button></div>}</Modal>
    {selectedListing&&<Modal open onClose={()=>setSelectedListing(null)} title={selectedListing.title} size="lg"><>{ownedIds.includes(selectedListing.id)&&<button className="secondary-btn" onClick={()=>{onEdit?.(selectedListing);setSelectedListing(null)}}>Редактировать своё объявление</button>}<ListingDetail listing={selectedListing} onClose={()=>setSelectedListing(null)}/></></Modal>}
  </section>
}
