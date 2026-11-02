import { useEffect, useState, useSyncExternalStore } from 'react'
import { getPendingRequests, subscribeRequests } from '../../api/client'
import { Spinner } from './Spinner'
import { Icon } from './Icon'

const TIPS = ['Более мощная видеокарта помогает, пока производительность не ограничена процессором.', 'Для NVMe SSD важен подходящий слот M.2 PCIe на материнской плате.', 'Смотрите на весь состав сборки: питание и охлаждение тоже важны.', 'Диапазон FPS помогает учесть различия сцен, настроек и тестовых систем.']

export function NetworkActivity() {
  const pending = useSyncExternalStore(subscribeRequests, getPendingRequests)
  if (!pending) return null
  return <div className="network-activity"><span className="network-track" aria-hidden="true"/><Spinner label="Обмениваемся данными с сервером…"/></div>
}

export function LoadingPanel({ title = 'Загружаем данные', description, cards = false, startedAt }) {
  const [elapsed, setElapsed] = useState(() => startedAt ? Math.max(0,Math.floor((Date.now()-startedAt)/1000)) : 0)
  useEffect(() => {
    const started = startedAt || Date.now()
    const tick = () => setElapsed(Math.max(0,Math.floor((Date.now()-started)/1000)))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [startedAt])
  return <section className={`loading-panel ${cards?'loading-search':''}`} aria-busy="true">
    {cards&&<div className="search-orbit" aria-hidden="true"><span/><span/><div><Icon name="chip" size={30}/></div><i><Icon name="gpu" size={17}/></i><i><Icon name="drive" size={17}/></i></div>}
    <Spinner label={title}/>
    {description && <p>{description}</p>}
    <div className="loading-time"><span aria-hidden="true">Прошло {Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')}</span><span>{elapsed<30?'Запрос выполняется':elapsed<90?'Некоторым площадкам нужно больше времени':'Поиск продолжается. Можно закрыть окно и вернуться к нему.'}</span></div>
    {cards&&<div className="loading-tip"><span>Пока идёт поиск</span><p key={Math.floor(elapsed/12)%TIPS.length}>{TIPS[Math.floor(elapsed/12)%TIPS.length]}</p></div>}
    {cards && <div className="loading-cards" aria-hidden="true">{[0,1,2].map(index => <div className="skeleton-card" key={index}><span/><span/><span/><span/></div>)}</div>}
    <div className="loading-track" aria-hidden="true"><span/></div>
  </section>
}
