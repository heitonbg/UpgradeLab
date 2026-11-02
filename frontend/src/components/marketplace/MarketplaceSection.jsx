import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Icon } from '../ui/Icon'
import { ListingGrid } from './ListingGrid'
import { ListingForm } from './ListingForm'
import { ListingDetail } from './ListingDetail'
import { CATEGORIES, filterListings } from '../../lib/marketplace'

const initialFilters = {search:'',deal:'all',category:'all',condition:'all',min:'',max:'',sort:'newest'}

export function MarketplaceSection({ listings=[], loading, error, onCreate, onRetry, user, onLogin, intent, onConsumed }) {
  const [filters,setFilters] = useState(initialFilters)
  const [isModalOpen,setIsModalOpen] = useState(false)
  const [selectedListing,setSelectedListing] = useState(null)
  const [draft,setDraft] = useState(null)
  useEffect(()=>{
    if(!intent)return
    setFilters({...initialFilters,search:intent.search||''})
    if(intent.draft){setDraft(intent.draft);setIsModalOpen(true)}
    onConsumed?.()
  },[intent,onConsumed])
  const set = key => event => setFilters({...filters,[key]:event.target.value})
  const changeDeal = deal => setFilters({...filters,deal,...(deal==='exchange'?{min:'',max:''}:{})})
  const create = () => {setDraft(null);setIsModalOpen(true)}
  const hasFilters = Object.entries(initialFilters).some(([key,value]) => key!=='sort' && filters[key]!==value)
  const filtered = filterListings(listings,filters)
  const invalidPrice = filters.min!=='' && filters.max!=='' && Number(filters.min)>Number(filters.max)
  const counts = {all:listings.length,sale:listings.filter(l=>(l.listing_type||'sale')==='sale').length,exchange:listings.filter(l=>l.listing_type==='exchange').length}
  async function handleCreate(data){await onCreate(data);setIsModalOpen(false)}

  return <section className="marketplace-browser">
    <div className="market-section-heading"><div><h2>Объявления сообщества</h2><p>Комплектующие от других пользователей — для продажи и обмена.</p></div><Button type="button" onClick={create}><Icon name="plus" size={17}/>Разместить объявление</Button></div>
    <section className="market-controls" aria-label="Поиск и фильтры объявлений">
      <div className="market-controls-top"><div className="deal-tabs" role="group" aria-label="Продажа или обмен">{[['all','Все объявления'],['sale','Продажа'],['exchange','Обмен']].map(([key,label])=><button type="button" key={key} aria-pressed={filters.deal===key} className={filters.deal===key?'selected':''} onClick={()=>changeDeal(key)}>{label}<span>{counts[key]}</span></button>)}</div><label className="market-sort"><span>Порядок</span><select aria-label="Сортировка объявлений" value={filters.sort} onChange={set('sort')}><option value="newest">Сначала новые</option><option value="price">Сначала дешевле</option></select></label></div>
      <div className="market-search"><Icon name="search"/><input type="search" aria-label="Поиск объявлений" placeholder="Модель или название: например, RTX 4060" value={filters.search} onChange={set('search')}/>{filters.search&&<button type="button" aria-label="Очистить поиск" onClick={()=>setFilters({...filters,search:''})}>×</button>}</div>
      <div className="market-filter-grid"><label><span>Комплектующее</span><select value={filters.category} onChange={set('category')}>{CATEGORIES.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label><span>Состояние</span><select value={filters.condition} onChange={set('condition')}><option value="all">Любое состояние</option><option value="new">Новое</option><option value="used">Б/у</option></select></label><fieldset className="market-price"><legend>Цена, ₽</legend><div><input aria-label="Цена от" type="number" min="0" placeholder="От" disabled={filters.deal==='exchange'} value={filters.min} onChange={set('min')}/><span>—</span><input aria-label="Цена до" type="number" min="0" placeholder="До" disabled={filters.deal==='exchange'} value={filters.max} onChange={set('max')}/></div></fieldset></div>
      <div className="market-filter-foot"><span><Icon name="filters" size={14}/>{loading?'Загружаем объявления…':`Найдено объявлений: ${filtered.length}`}</span>{hasFilters&&<button type="button" className="text-btn" onClick={()=>setFilters(initialFilters)}>Сбросить фильтры</button>}</div>
      {filters.deal==='exchange'&&<p className="field-hint">Для обмена цена не ограничивается: условия указаны в объявлении.</p>}
      {invalidPrice&&<p className="filter-validation" role="status">Цена «до» должна быть не меньше цены «от».</p>}
    </section>
    {error&&!loading?<div className="market-error" role="alert"><Icon name="refresh" size={24}/><div><h3>Не удалось загрузить объявления</h3><p>Связь с сервисом прервалась или он временно недоступен. Ваши фильтры сохранены.</p></div><Button type="button" variant="secondary" onClick={onRetry}>Повторить загрузку</Button></div>:<ListingGrid listings={invalidPrice?[]:filtered} loading={loading} hasFilters={hasFilters} onReset={()=>setFilters(initialFilters)} onCreate={create} emptyMessage={listings.length?'Попробуйте другое название или расширьте фильтры.':undefined} onClick={setSelectedListing}/>}
    <Modal open={isModalOpen} onClose={()=>setIsModalOpen(false)} title="Новое объявление" size="lg">{user?<ListingForm key={draft?.title||'new'} initial={draft} onSubmit={handleCreate} onCancel={()=>setIsModalOpen(false)}/>:<div className="login-prompt"><span className="empty-icon"><Icon name="box" size={30}/></span><h4>Разместите свою комплектующую</h4><p>Войдите в аккаунт, чтобы опубликовать объявление и управлять им из личного кабинета.</p><Button type="button" onClick={()=>{setIsModalOpen(false);onLogin()}}>Войти в аккаунт<Icon name="arrow" size={16}/></Button></div>}</Modal>
    {selectedListing&&<Modal open onClose={()=>setSelectedListing(null)} title={selectedListing.title} size="lg"><ListingDetail listing={selectedListing} onClose={()=>setSelectedListing(null)}/></Modal>}
  </section>
}
