import { useEffect, useMemo, useState } from 'react'
import { saveAndShareBuild } from '../lib/share'
import { request } from '../api/client'

const categories = ['Процессор','Видеокарта','Материнская плата','Оперативная память','Накопитель','Блок питания','Корпус','Кулер','Другое']
const safeUrl = value => { try { const url = new URL(value); return url.protocol === 'https:' ? url.href : '' } catch { return '' } }

export function CustomConfigurator() {
  const [parts,setParts] = useState([])
  const [form,setForm] = useState({category:categories[0],name:'',price:'',url:'',image_url:''})
  const [message,setMessage] = useState('')
  const [shared,setShared]=useState(null)
  useEffect(()=>{
    const sharedId=new URLSearchParams(window.location.search).get('shared')
    if(sharedId){let alive=true;request('/api/shared-builds/'+encodeURIComponent(sharedId)).then(data=>{if(alive){setParts(data.snapshot.parts);setShared(data);setMessage('Открыт сохранённый снимок. Цены и FPS не проверяются повторно.')}}).catch(error=>{if(alive)setMessage(error.message)});return()=>{alive=false}}
    const raw=new URLSearchParams(window.location.hash.slice(1)).get('config')
    if(!raw)return
    try { const value=JSON.parse(raw);if(value?.v===1&&Array.isArray(value.parts))setParts(value.parts.filter(p=>p&&typeof p.name==='string'&&categories.includes(p.category))) }
    catch { setMessage('Ссылка на конфигурацию повреждена или имеет неподдерживаемый формат.') }
  },[])
  const allPriced=parts.length>0&&parts.every(part=>typeof part.price==='number'&&Number.isFinite(part.price)&&part.price>=0)
  const total=useMemo(()=>parts.reduce((sum,p)=>sum+(Number(p.price)||0),0),[parts])
  function add(event){
    event.preventDefault();setMessage('')
    const price=Number(form.price)
    if(form.name.trim().length<2||!Number.isSafeInteger(price)||price<0){setMessage('Укажите название детали и цену целым числом.');return}
    const url=form.url?safeUrl(form.url):'';const image_url=form.image_url?safeUrl(form.image_url):''
    if((form.url&&!url)||(form.image_url&&!image_url)){setMessage('Ссылки должны начинаться с HTTPS.');return}
    setShared(null)
    setParts(current=>[...current,{category:form.category,name:form.name.trim(),price,url,image_url}])
    setForm({...form,name:'',price:'',url:'',image_url:''})
  }
  async function share(){
    try { await saveAndShareBuild({v:1,parts});setMessage('Сборка сохранена. Ссылка скопирована.') }
    catch(error) { setMessage(error.message||'Не удалось сохранить и скопировать ссылку.') }

  }
  return <section className="custom-configurator">
    <header className="page-heading"><p className="eyebrow">Своя сборка</p><h1>Конфигуратор комплектующих</h1><p>Добавляйте детали с любых сайтов, указывайте цену и делитесь списком по ссылке. Ссылки и цены вводятся вами и не проверяются автоматически.</p></header>
    <form className="panel custom-config-form" onSubmit={add}>
      <label>Категория<select value={form.category} onChange={e=>setForm({...form,category:e.target.value})}>{categories.map(c=><option key={c}>{c}</option>)}</select></label>
      <label>Название детали<input required minLength="2" maxLength="200" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Например, Ryzen 5 5600"/></label>
      <label>Цена, ₽<input required type="number" min="0" step="1" value={form.price} onChange={e=>setForm({...form,price:e.target.value})} placeholder="12500"/></label>
      <label className="custom-config-wide">Ссылка на товар (HTTPS)<input type="url" value={form.url} onChange={e=>setForm({...form,url:e.target.value})} placeholder="https://..."/></label>
      <label className="custom-config-wide">Ссылка на фотографию (HTTPS, необязательно)<input type="url" value={form.image_url} onChange={e=>setForm({...form,image_url:e.target.value})} placeholder="https://.../photo.webp"/></label>
      <button type="submit">Добавить комплектующую</button>
    </form>
    {message&&<p role="status" className="field-hint">{message}</p>}
    <section className="panel custom-config-list"><div className="custom-config-head"><h2>Состав сборки</h2><strong>{total.toLocaleString('ru-RU')} ₽{!allPriced?' · известная часть суммы':''}</strong></div>
      {!parts.length?<p className="field-hint">Пока нет комплектующих. Добавьте первую деталь выше.</p>:parts.map((part,index)=><article key={`${part.name}-${index}`} className="custom-config-part">{part.image_url&&<img src={part.image_url} alt="" loading="lazy" referrerPolicy="no-referrer"/>}<div><small>{part.category}</small><strong>{part.name}</strong>{part.url&&<a href={part.url} target="_blank" rel="noreferrer">Открыть товар</a>}</div><b>{typeof part.price==='number'?part.price.toLocaleString('ru-RU')+' ₽':'Цена не указана'}</b><button type="button" aria-label={`Удалить ${part.name}`} onClick={()=>{setShared(null);setParts(current=>current.filter((_,i)=>i!==index))}}>Удалить</button></article>)}
      {shared&&<p className="field-hint">Снимок от {new Date(shared.created_at).toLocaleString('ru-RU')}{shared.snapshot.game?` · ${shared.snapshot.game}`:''}{shared.snapshot.fps!=null?` · прогноз ${shared.snapshot.current_fps!=null?shared.snapshot.current_fps+' → ':''}${shared.snapshot.fps} FPS`:''}. Данные пользователя, не подтверждённые предложения.</p>}<div className="result-actions"><button type="button" className="secondary-btn" disabled={!parts.length} onClick={share}>Поделиться сборкой</button><button type="button" className="text-btn" disabled={!parts.length} onClick={()=>{setParts([]);setShared(null);setMessage('Сборка очищена.')}}>Очистить</button></div>
      {!!parts.length&&<p className="field-hint">Общий итог рассчитан из введённых цен. Совместимость, наличие, ссылки и цены не проверены UpgradeLab.</p>}
    </section>
  </section>
}
