import { useConfirm } from './components/ui/useConfirm'
import { HomePage } from './components/HomePage'
import { Modal } from './components/ui/Modal'
import { ListingForm } from './components/marketplace/ListingForm'
import { money as savedMoney } from './lib/savedPrices'
import { Icon } from './components/ui/Icon'
import { NetworkActivity } from './components/ui/LoadingPanel'
import { useCallback, useEffect, useRef, useState } from 'react'
import { request } from './api/client'
import { useHardware } from './hooks/useHardware'
import { useListings } from './hooks/useListings'
import { CalculatorSection } from './components/calculator/CalculatorSection'
import { MarketplaceSection } from './components/marketplace/MarketplaceSection'
import { BuildSection } from './components/calculator/BuildSection'
import { AccountBuilds } from './components/saved/AccountBuilds'
import { useSavedBuilds } from './hooks/useSavedBuilds'
import { ResetPassword } from './components/PasswordRecovery'
import { StoreOffers } from './components/StoreOffers'
import { AuthForm, AccountSettings } from './components/AccountPanel'

const tabs = [['home','Главная'],['calculator','Подбор ПК'],['search','Поиск комплектующих'],['marketplace','Биржа'],['account','Профиль']]

function NavIcon({ name }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{name==='calculator'?<><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2m4 0h2m-8 4h2m4 0h2"/></>:name==='marketplace'?<><path d="M3 9h18l-2-6H5L3 9Zm1 0v12h16V9M8 21v-7h8v7"/></>:<><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>}</svg>
}

export default function App() {
  const [resetToken,setResetToken]=useState('')
  const [scenario,setScenario] = useState(()=>new URLSearchParams(window.location.search).get('scenario')==='upgrade'?'upgrade':'build')
  const [marketIntent,setMarketIntent] = useState(null)
  const localBuilds = useSavedBuilds()
  const pendingBuild = useRef(null)
  const accountId = useRef(null)
  const [authMode,setAuthMode] = useState('login')
  const [importing,setImporting] = useState(false)
  const [editingListing,setEditingListing] = useState(null)
  const [editingDirty,setEditingDirty] = useState(false)
  const {confirm,confirmation}=useConfirm()
  const closeEditor=async()=>{if(!editingDirty||await confirm({title:'Закрыть без сохранения?',description:'Изменения в объявлении будут потеряны.',cancel:'Продолжить редактирование',action:'Не сохранять'}))setEditingListing(null)}
  const setAccount = useCallback(account=>{
    accountId.current=account?.id??null
    setUser(account);setBuilds([]);setMine([]);setEditingListing(null)
  },[])
  const findOnMarket = intent=>{setMarketIntent(intent||{});setActiveTab('marketplace')}
  const consumeIntent = useCallback(()=>setMarketIntent(null),[])
  const [activeTab,setActiveTab] = useState(()=>{const tab=new URLSearchParams(window.location.search).get('tab');return tabs.some(([key])=>key===tab)?tab:'home'})
  const [searchCategory,setSearchCategory]=useState('GPU')
  const [assemblyOffer,setAssemblyOffer]=useState(null)
  const selectSearchOffer=offer=>{if(['motherboard','memory','storage','psu','case','cooler'].includes(offer.category)){setAssemblyOffer(offer);setNotice('Предложение добавлено в ручную сборку. Укажите остальные детали; сервер проверит цену и совместимость.')}else setNotice('CPU и GPU выбираются парой в варианте сборки. Здесь можно продолжить подбор.');startScenario('build')}
  const startScenario=kind=>{setScenario(kind);setActiveTab('calculator')}
  const openSearch=category=>{setSearchCategory(category||'GPU');setActiveTab('search')}
  useEffect(()=>{const url=new URL(window.location.href);url.searchParams.set('tab',activeTab);if(activeTab==='calculator')url.searchParams.set('scenario',scenario);else url.searchParams.delete('scenario');window.history.replaceState(null,'',url.pathname+url.search+url.hash)},[activeTab,scenario])
  const [user,setUser] = useState(null)
  const [authReady,setAuthReady] = useState(false)
  const [builds,setBuilds] = useState([])
  const [mine,setMine] = useState([])
  const [notice,setNotice] = useState('')
  const {cpus,gpus,rams,loading:hwLoading,error:hwError} = useHardware()
  const {listings,loading:lstLoading,error:lstError,add:addListing,reload:refreshListings} = useListings()
  const loadAccount = useCallback(async()=>{
    const owner=accountId.current
    try { const [saved,own] = await Promise.all([request('/api/builds'),request('/api/my/listings')]);if(owner!==null&&accountId.current===owner){setBuilds(saved);setMine(own)} }
    catch(e) { setNotice(e.message) }
  },[])
  useEffect(()=>{
    const readResetLink=()=>{
      const token=new URLSearchParams(window.location.hash.slice(1)).get('reset_token')
      if(token){setResetToken(token);setActiveTab('account');window.history.replaceState(null,'',window.location.pathname+window.location.search)}
    }
    readResetLink()
    window.addEventListener('hashchange',readResetLink)
    request('/api/auth/me').then(setAccount).catch(e=>{if(e.status!==401)setNotice('Не удалось связаться с сервером. Проверьте запуск backend.')}).finally(()=>setAuthReady(true))
    const expired=()=>{setAccount(null);setActiveTab('account');setNotice('Сеанс завершён. Войдите ещё раз.')}
    window.addEventListener('upgradelab:session-expired',expired)
    return()=>{window.removeEventListener('upgradelab:session-expired',expired);window.removeEventListener('hashchange',readResetLink)}
  },[])
  useEffect(()=>{if(user)loadAccount();else{setBuilds([]);setMine([])}},[user,loadAccount])
  async function saveBuild(result) {
    if(!result?.config)return
    if(!user){pendingBuild.current=result;setAuthMode('login');setActiveTab('account');setNotice('Войдите или зарегистрируйтесь — затем этот результат сохранится в вашем аккаунте.');return}
    try{await request('/api/builds',{method:'POST',body:result.config});await loadAccount();setNotice('Результат сохранён на сервере в вашем аккаунте.')}
    catch(e){setNotice(e.message)}
  }
  async function onAuth(account) {
    setAccount(account);setNotice('Вы вошли в аккаунт.')
    if(pendingBuild.current){
      try{
        await request('/api/builds',{method:'POST',body:pendingBuild.current.config})
        pendingBuild.current=null
        await loadAccount();setNotice('Вы вошли в аккаунт. Результат сохранён на сервере.')
      }catch(e){setNotice(`Вы вошли, но сохранить результат не удалось: ${e.message}. Повторите сохранение в конфигураторе.`)}
    }
  }
  async function importLocalBuilds(){
    if(!user||importing)return
    setImporting(true)
    let count=0
    try{
      for(const build of localBuilds.builds){
        await request('/api/builds',{method:'POST',body:build.config})
        count++
      }
      setNotice(`Создано новых расчётов: ${count}. Исторические локальные снимки оставлены в браузере.`)
    }catch(e){setNotice(`Создано новых расчётов: ${count}. Исходные локальные снимки остались в браузере. ${e.message}`)}
    finally{await loadAccount();setImporting(false)}
  }

  async function updateListing(data) {
    const owner=accountId.current
    await request(`/api/listings/${editingListing.id}`,{method:'PATCH',body:data})
    if(owner!==accountId.current)return
    setEditingListing(null)
    await Promise.all([loadAccount(),refreshListings()])
    setNotice('Объявление обновлено.')
  }
  async function createListing(data){const item=await addListing(data);await loadAccount();return item}
  async function removeListing(id){
    if(!await confirm({title:'Удалить объявление?',description:'Объявление будет удалено из биржи.',action:'Удалить'}))return
    try{await request(`/api/listings/${id}`,{method:'DELETE'});await Promise.all([loadAccount(),refreshListings()]);setNotice('Объявление удалено.')}
    catch(e){setNotice(e.message)}
  }
  async function removeBuild(id){if(!await confirm({title:'Удалить сохранённый расчёт?',description:'Это действие нельзя отменить.',action:'Удалить'}))return;try{await request(`/api/builds/${id}`,{method:'DELETE'});await loadAccount()}catch(e){setNotice(e.message)}}
  async function recalculateSaved(build){await request('/api/builds',{method:'POST',body:build.config});await loadAccount();setNotice('Создан новый расчёт. Историческая сборка сохранена.')}
  async function logout(){try{await request('/api/auth/logout',{method:'POST'});setAccount(null);setNotice('Вы вышли из аккаунта.')}catch(e){setNotice(e.message)}}

  return <div className="app-shell">{confirmation}<NetworkActivity/><div className="workspace"><header className="site-header"><a href="?tab=home" className="brand" onClick={e=>{e.preventDefault();setActiveTab('home')}} aria-label="UpgradeLab — главная"><svg width="27" height="30" viewBox="0 0 27 30" fill="none" aria-hidden="true"><path d="M4 4v13a9.5 9.5 0 0 0 19 0V4h-5v13a4.5 4.5 0 0 1-9 0V4H4Z" fill="currentColor"/><path d="M13.5 1v12" stroke="var(--accent-text)" strokeWidth="3"/></svg>Upgrade<span>Lab</span></a><nav className="main-nav" aria-label="Разделы">{[['calculator','Подбор ПК'],['upgrade','Апгрейд'],['search','Поиск комплектующих'],['marketplace','Биржа']].map(([key,label])=><button key={key} className={(key==='upgrade'?activeTab==='calculator'&&scenario==='upgrade':activeTab===key&&(key!=='calculator'||scenario==='build'))?'active':''} aria-current={(key==='upgrade'?activeTab==='calculator'&&scenario==='upgrade':activeTab===key&&(key!=='calculator'||scenario==='build'))?'page':undefined} onClick={()=>key==='calculator'?startScenario('build'):key==='upgrade'?startScenario('upgrade'):setActiveTab(key)}>{label}</button>)}</nav><div className="header-account"><button className="account-chip" onClick={()=>{setAuthMode('login');setActiveTab('account')}}><NavIcon name="account"/>{user?.name||'Войти'}</button>{!user&&authReady&&<button className="text-btn register-link" onClick={()=>{setAuthMode('register');setActiveTab('account')}}>Регистрация</button>}</div></header><main className="content">{notice&&<div className="notice" role="status">{notice}<button aria-label="Закрыть уведомление" onClick={()=>setNotice('')}>×</button></div>}
    {activeTab==='home'&&<HomePage onBuild={()=>startScenario('build')} onUpgrade={()=>startScenario('upgrade')} onSearch={openSearch} onMarketplace={()=>setActiveTab('marketplace')}/>}
    {activeTab==='search'&&<><header className="page-heading"><p className="eyebrow">Каталог предложений</p><h1>Найдите нужную деталь.</h1><p>Магазины, разрешённые прайсы и предложения сообщества. Проверяйте источник и дату цены.</p></header><StoreOffers key={searchCategory} initialCategory={searchCategory} onSelect={selectSearchOffer} selectLabel={offer=>['CPU','GPU'].includes(offer.category)?'К вариантам сборки':'Добавить в сборку'}/></>}
    <div className="configurator-stack" hidden={activeTab!=='calculator'}><header className="page-heading configurator-heading"><div><p className="eyebrow">Конфигуратор UpgradeLab</p><h1>{scenario==='build'?'Новый ПК. В вашем бюджете.':'Ваш следующий апгрейд'}</h1><p>{scenario==='build'?'Сравните конфигурации под ваши задачи и бюджет.':'Найдите ограничение производительности и решите, что действительно стоит менять.'}</p></div><div className="hero-mark"><Icon name={scenario==='build'?'box':'chip'} size={38}/></div></header>{hwError&&<p className="error">Не удалось загрузить каталог: {hwError.message}</p>}<div className="scenario-switch scenario-tabs" role="group" aria-label="Сценарий подбора"><button className={scenario==='upgrade'?'selected':''} aria-pressed={scenario==='upgrade'} onClick={()=>setScenario('upgrade')}><Icon name="chip" size={23}/><span><strong>У меня есть ПК</strong><small>Найти нужный апгрейд</small></span><Icon name="arrow" size={17}/></button><button className={scenario==='build'?'selected':''} aria-pressed={scenario==='build'} onClick={()=>setScenario('build')}><Icon name="box" size={23}/><span><strong>Собрать с нуля</strong><small>Подобрать весь компьютер</small></span><Icon name="arrow" size={17}/></button></div><div hidden={scenario!=='upgrade'}><CalculatorSection cpus={cpus} gpus={gpus} rams={rams} hardwareLoading={hwLoading} onFindOnMarketplace={findOnMarket} onSaveBuild={saveBuild}/></div><div hidden={scenario!=='build'}><BuildSection offerIntent={assemblyOffer} onOfferConsumed={()=>setAssemblyOffer(null)} active={activeTab==='calculator'&&scenario==='build'} onSave={saveBuild} onFind={findOnMarket}/></div>{user&&<button className="text-btn" onClick={()=>setActiveTab('account')}>Открыть сохранённые сборки</button>}<button className="secondary-btn catalog-link" onClick={()=>openSearch()}>Открыть поиск комплектующих <Icon name="arrow" size={16}/></button><details className="price-status"><summary>Как читать цены и результаты</summary><p>Цена сопровождается источником и датой. Свежая запись не равна подтверждённой покупке: проверяйте наличие, доставку и совместимость. Закрытые данные каталога не отображаются публично.</p></details></div>
    {activeTab==='marketplace'&&<><MarketplaceSection ownedIds={mine.map(item=>item.id)} onEdit={setEditingListing} onRetry={refreshListings} listings={listings} loading={lstLoading} error={lstError} onCreate={createListing} onLogin={()=>setActiveTab('account')} user={user} intent={marketIntent} onConsumed={consumeIntent}/></>}
    {activeTab==='account'&&(resetToken?<ResetPassword token={resetToken} onDone={message=>{setResetToken('');setAccount(null);setAuthMode('login');setNotice(message)}}/>:!authReady?<div className="panel">Проверяем сеанс…</div>:!user?<AuthForm key={authMode} initialMode={authMode} onAuth={onAuth}/>:<><header className="page-heading"><p className="eyebrow">Личный кабинет</p><h1>{user.name}</h1><p>{user.email}</p></header><div className="account-toolbar"><p>{builds.length} сохранённых расчётов · {mine.length} объявлений</p><button className="secondary-btn" onClick={logout}>Выйти из аккаунта</button></div>{localBuilds.builds.length>0&&<section className="panel"><h2>Ранее сохранено в этом браузере</h2><p>Найдено результатов: {localBuilds.builds.length}. Это исторические снимки с неподтверждёнными текущими ценами. Можно создать новые расчёты в аккаунте по их настройкам; исходные снимки останутся в браузере.</p>{localBuilds.builds.map(build=><p className="field-hint" key={build.id}>Историческая стоимость: {savedMoney(build.result?.total_price ?? build.total_price ?? build.result?.avg_price ?? build.avg_price)} · {build.createdAt ? new Date(build.createdAt).toLocaleString('ru-RU') : 'Дата неизвестна'}. Актуальность не подтверждена.</p>)}<button className="secondary-btn" disabled={importing} onClick={importLocalBuilds}>{importing?'Рассчитываем…':'Создать новые расчёты по настройкам'}</button></section>}<div className="account-grid"><AccountBuilds builds={builds} cpus={cpus} gpus={gpus} onFind={findOnMarket} onRemove={removeBuild} onRecalculate={recalculateSaved}/><section className="panel"><h2>Мои объявления</h2>{mine.length?mine.map(item=><div className="account-item" key={item.id}><div><strong>{item.title}</strong><span>{item.price} · {item.condition}</span><small>{new Date(item.created_at).toLocaleDateString('ru-RU')}</small></div><button className="secondary-btn" onClick={()=>setEditingListing(item)}>Редактировать</button><button aria-label="Удалить объявление" onClick={()=>removeListing(item.id)}>Удалить</button></div>):<p className="empty-copy">Ваши объявления появятся здесь после публикации на бирже.</p>}</section></div><AccountSettings user={user} onUser={setAccount} onNotice={setNotice}/></>)}
  {editingListing&&<Modal open title="Редактировать объявление" size="lg" onClose={closeEditor}><ListingForm key={editingListing.id} initial={editingListing} onSubmit={updateListing} onCancel={closeEditor} onDirtyChange={setEditingDirty}/></Modal>}
  </main></div></div>
}
