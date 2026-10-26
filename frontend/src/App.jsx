import { useCallback, useEffect, useRef, useState } from 'react'
import { request } from './api/client'
import { useHardware } from './hooks/useHardware'
import { useListings } from './hooks/useListings'
import { CalculatorSection } from './components/calculator/CalculatorSection'
import { MarketplaceSection } from './components/marketplace/MarketplaceSection'
import { AuthForm, AccountSettings } from './components/AccountPanel'

const tabs = [['calculator','Конфигуратор'],['marketplace','Биржа'],['account','Личный кабинет']]

function NavIcon({ name }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{name==='calculator'?<><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2m4 0h2m-8 4h2m4 0h2"/></>:name==='marketplace'?<><path d="M3 9h18l-2-6H5L3 9Zm1 0v12h16V9M8 21v-7h8v7"/></>:<><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>}</svg>
}

export default function App() {
  const [activeTab,setActiveTab] = useState('calculator')
  const [user,setUser] = useState(null)
  const [authReady,setAuthReady] = useState(false)
  const [builds,setBuilds] = useState([])
  const [mine,setMine] = useState([])
  const [notice,setNotice] = useState('')
  const [priceStatus,setPriceStatus] = useState(null)
  const pendingBuild = useRef(null)
  const {cpus,gpus,rams,loading:hwLoading,error:hwError} = useHardware()
  const {listings,loading:lstLoading,error:lstError,add:addListing,reload:refreshListings} = useListings()
  const loadAccount = useCallback(async()=>{
    try { const [saved,own] = await Promise.all([request('/api/builds'),request('/api/my/listings')]);setBuilds(saved);setMine(own) }
    catch(e) { setNotice(e.message) }
  },[])
  useEffect(()=>{
    request('/api/auth/me').then(setUser).catch(e=>{if(e.status!==401)setNotice('Не удалось связаться с сервером. Проверьте запуск backend.')}).finally(()=>setAuthReady(true))
    request('/api/prices/status').then(setPriceStatus).catch(()=>{})
    const expired=()=>{setUser(null);setActiveTab('account');setNotice('Сеанс завершён. Войдите ещё раз.')}
    window.addEventListener('upgradelab:session-expired',expired)
    return()=>window.removeEventListener('upgradelab:session-expired',expired)
  },[])
  useEffect(()=>{if(user)loadAccount();else{setBuilds([]);setMine([])}},[user,loadAccount])
  async function saveBuild(result) {
    if(!result?.config)return
    if(!user){pendingBuild.current=result;setActiveTab('account');setNotice('Войдите, и этот расчёт будет сохранён.');return}
    try{await request('/api/builds',{method:'POST',body:result.config});await loadAccount();setNotice('Расчёт сохранён в личном кабинете.')}
    catch(e){setNotice(e.message)}
  }
  async function onAuth(account) {
    setUser(account);setNotice('Вы вошли в аккаунт.')
    if(pendingBuild.current){
      const result=pendingBuild.current;pendingBuild.current=null
      try{await request('/api/builds',{method:'POST',body:result.config});await loadAccount();setNotice('Вы вошли в аккаунт. Расчёт сохранён.')}
      catch(e){setNotice(e.message)}
    }
  }
  async function createListing(data){const item=await addListing(data);await loadAccount();return item}
  async function removeListing(id){
    if(!window.confirm('Удалить объявление?'))return
    try{await request(`/api/listings/${id}`,{method:'DELETE'});await Promise.all([loadAccount(),refreshListings()]);setNotice('Объявление удалено.')}
    catch(e){setNotice(e.message)}
  }
  async function removeBuild(id){try{await request(`/api/builds/${id}`,{method:'DELETE'});await loadAccount()}catch(e){setNotice(e.message)}}
  async function logout(){try{await request('/api/auth/logout',{method:'POST'});setUser(null);setNotice('Вы вышли из аккаунта.')}catch(e){setNotice(e.message)}}

  return <div className="app-shell"><aside className="sidebar"><button className="brand" onClick={()=>setActiveTab('calculator')}>Upgrade<span>Lab</span></button><p className="brand-caption">Подбор комплектующих</p><nav className="side-nav" aria-label="Разделы">{tabs.map(([key,label])=><button key={key} className={activeTab===key?'active':''} onClick={()=>setActiveTab(key)}><NavIcon name={key}/><span>{label}</span></button>)}</nav><div className="sidebar-foot">Инструменты для вашей сборки<br/>Версия 1.2</div></aside><div className="workspace"><header className="topbar"><p>{tabs.find(t=>t[0]===activeTab)?.[1]}</p><button className="account-chip" onClick={()=>setActiveTab('account')}><NavIcon name="account"/>{user?.name||'Войти'}</button></header><main className="content">{notice&&<div className="notice" role="status">{notice}<button aria-label="Закрыть уведомление" onClick={()=>setNotice('')}>×</button></div>}
    <div hidden={activeTab!=='calculator'}><header className="page-heading"><div><p className="eyebrow">Анализ производительности</p><h1>Ваша конфигурация</h1><p>Сравните возможности CPU и GPU и выберите следующий апгрейд.</p></div></header>{hwError&&<p className="error">Не удалось загрузить каталог: {hwError.message}</p>}<CalculatorSection cpus={cpus} gpus={gpus} rams={rams} hardwareLoading={hwLoading} onFindOnMarketplace={()=>setActiveTab('marketplace')} onSaveBuild={saveBuild}/>{priceStatus&&<details className="price-status"><summary>Источники цен и покрытие каталога</summary><div>{Object.entries(priceStatus.coverage).map(([type,stat])=><span key={type}>{type}: {stat.priced} из {stat.total} моделей с ценой</span>)}</div><p>У цены есть источник и дата. PassMark — зарубежная розница с пересчётом по курсу ЦБ; Avito — сохранённые предложения. Доставка и региональные наценки не учтены.</p></details>}</div>
    {activeTab==='marketplace'&&<><header className="page-heading"><p className="eyebrow">Объявления сообщества</p><h1>Биржа комплектующих</h1><p>Найдите подходящую деталь или разместите своё объявление.</p></header><MarketplaceSection listings={listings} loading={lstLoading} error={lstError} onCreate={createListing} onLogin={()=>setActiveTab('account')} user={user}/></>}
    {activeTab==='account'&&(!authReady?<div className="panel">Проверяем сеанс…</div>:!user?<AuthForm onAuth={onAuth}/>:<><header className="page-heading"><p className="eyebrow">Личный кабинет</p><h1>{user.name}</h1><p>{user.email}</p></header><div className="account-toolbar"><p>{builds.length} сохранённых расчётов · {mine.length} объявлений</p><button className="secondary-btn" onClick={logout}>Выйти из аккаунта</button></div><div className="account-grid"><section className="panel"><h2>Сохранённые расчёты</h2>{builds.length?builds.map(b=><div className="account-item" key={b.id}><div><strong>{b.config.game}</strong><span>{cpus.find(x=>x.id===b.config.cpu_id)?.name||'CPU'} · {gpus.find(x=>x.id===b.config.gpu_id)?.name||'GPU'}</span><small>{b.config.mode} · ~{b.result.current_fps} FPS</small></div><button aria-label="Удалить расчёт" onClick={()=>removeBuild(b.id)}>Удалить</button></div>):<p className="empty-copy">Сохраните результат анализа, чтобы вернуться к нему позже.</p>}</section><section className="panel"><h2>Мои объявления</h2>{mine.length?mine.map(item=><div className="account-item" key={item.id}><div><strong>{item.title}</strong><span>{item.price} · {item.condition}</span><small>{new Date(item.created_at).toLocaleDateString('ru-RU')}</small></div><button aria-label="Удалить объявление" onClick={()=>removeListing(item.id)}>Удалить</button></div>):<p className="empty-copy">Ваши объявления появятся здесь после публикации на бирже.</p>}</section></div><AccountSettings user={user} onUser={setUser} onNotice={setNotice}/></>)}
  </main></div></div>
}
