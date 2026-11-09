import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { CityPicker } from '../CityPicker'
import { ListingPhoto } from './ListingPhoto'
import { useHardware } from '../../hooks/useHardware'
import { contactPreview } from '../../lib/contacts'

const INITIAL={title:'',condition:'Б/У',price:'',contact:'',contact_type:'telegram',description:'',
  listing_type:'sale',exchange_for:'',photo_url:'',city_id:null,category:null,hardware_id:null,
  publication_status:'active',confirm_availability:false}
const categories=[['CPU','Процессор'],['GPU','Видеокарта'],['memory','RAM'],['motherboard','Материнская плата'],
  ['storage','Накопитель'],['psu','Блок питания'],['case','Корпус'],['cooler','Кулер']]
export function ListingForm({onSubmit,onCancel,initial,onDirtyChange}) {
  const [form,setForm]=useState({...INITIAL,...initial,confirm_availability:false})
  const original={...INITIAL,...initial,confirm_availability:false}
  const dirty=Object.keys(INITIAL).some(key=>form[key]!==original[key])
  useEffect(()=>{onDirtyChange?.(dirty)},[dirty,onDirtyChange])
  useEffect(()=>{
    if(!dirty)return
    const leave=event=>{event.preventDefault();event.returnValue=''}
    window.addEventListener('beforeunload',leave)
    return()=>window.removeEventListener('beforeunload',leave)
  },[dirty])
  const [query,setQuery]=useState('')
  const [submitting,setSubmitting]=useState(false)
  const [error,setError]=useState('')
  const {cpus,gpus,rams,error:hardwareError}=useHardware()
  const models=(form.category==='CPU'?cpus:form.category==='GPU'?gpus:form.category==='memory'?rams:[])
  const found=query.trim().length>=2 ? models.filter(model=>model.name.toLowerCase().includes(query.toLowerCase())).slice(0,12) : []
  const preview=contactPreview(form.contact,form.contact_type||undefined)
  const set=key=>e=>setForm(current=>({...current,[key]:e.target.value}))
  async function photo(event) {
    const file=event.target.files?.[0];if(!file)return
    if(file.size>1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type)){
      setError('Выберите JPEG, PNG или WebP до 1 МБ');return}
    const reader=new FileReader()
    reader.onload=()=>{setForm(current=>({...current,photo_url:reader.result}));setError('')}
    reader.onerror=()=>setError('Не удалось прочитать фото')
    reader.readAsDataURL(file)
  }
  async function submit(event) {
    event.preventDefault();setError('');setSubmitting(true)
    try {
      if(!form.city_id && (!initial?.id || initial.city_id))throw Error('Выберите город из подсказки с регионом')
      const legacy=initial?.id && form.contact===initial.contact && !form.contact_type
      if(!preview.contact&&!legacy)throw Error(preview.error||'Выберите тип контакта и введите полный контакт')
      const payload=Object.fromEntries(Object.keys(INITIAL).map(key=>[key,form[key]]))
      await onSubmit({...payload,contact:preview.contact?.value||form.contact,contact_type:preview.contact?.type||null,
        photo_url:form.photo_url||null,description:form.description||null,
        price:form.listing_type==='exchange'?'Обмен':form.price,
        exchange_for:form.listing_type==='exchange'?form.exchange_for:null})
      if(!initial?.id)setForm(INITIAL)
    }catch(error){setError(error.message||'Не удалось сохранить объявление')}
    finally{setSubmitting(false)}
  }
  return <form onSubmit={submit} className="listing-form space-y-3">
    <label>Тип объявления<select aria-label="Тип объявления" value={form.listing_type} onChange={set('listing_type')}><option value="sale">Продажа</option><option value="exchange">Обмен</option></select></label>
    <label>Название<input required minLength={2} maxLength={200} value={form.title} onChange={set('title')}/></label>
    <CityPicker value={form.city_id} onChange={city_id=>setForm(current=>({...current,city_id}))}/>
    <label>Категория<select aria-label="Категория" value={form.category||''} onChange={e=>{setForm(current=>({...current,category:e.target.value||null,hardware_id:null}));setQuery('')}}>
      <option value="">Обычное объявление</option>{categories.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
    {models.length>0&&<label>Модель каталога<input type="search" value={query} placeholder="Введите модель для поиска" onChange={e=>setQuery(e.target.value)}/>
      {found.map(model=><button type="button" className="text-btn" key={model.id} onClick={()=>{setForm(current=>({...current,hardware_id:model.id,title:model.name}));setQuery('')}}>{model.name}</button>)}
      {query.length>=2&&!found.length&&<small>Модель не найдена; можно оставить обычное объявление.</small>}
    </label>}
    {hardwareError&&<p className="field-hint">Каталог моделей недоступен. Можно создать обычное объявление.</p>}
    {form.hardware_id&&<p className="field-hint">Выбрана модель каталога #{form.hardware_id}.<button type="button" className="text-btn" onClick={()=>setForm(current=>({...current,hardware_id:null}))}>Убрать привязку</button></p>}
    <label>Состояние<select aria-label="Состояние" value={form.condition} onChange={set('condition')}><option>Б/У</option><option>Новое</option><option>Неисправное</option></select></label>
    <label>Цена<input required={form.listing_type==='sale'} disabled={form.listing_type==='exchange'} maxLength={50} value={form.price} onChange={set('price')}/></label>
    {form.listing_type==='exchange'&&<label>Что хотите получить<input required maxLength={500} value={form.exchange_for||''} onChange={set('exchange_for')}/></label>}
    <label>Статус<select aria-label="Статус" value={form.publication_status} onChange={set('publication_status')}><option value="active">Активно</option><option value="sold">Продано</option><option value="withdrawn">Снято с публикации</option></select></label>
    <label>Фото JPEG, PNG, WebP до 1 МБ<input type="file" accept="image/jpeg,image/png,image/webp" onChange={photo}/></label>
    <label>Или HTTPS-ссылка на фото<input type="url" maxLength={2000} value={form.photo_url?.startsWith('data:')?'':form.photo_url||''} onChange={set('photo_url')}/></label>
    {form.photo_url&&<><ListingPhoto src={form.photo_url} zoom/><button type="button" onClick={()=>setForm(current=>({...current,photo_url:null}))}>Убрать фото</button></>}
    <label>Тип контакта<select aria-label="Тип контакта" value={form.contact_type||''} onChange={set('contact_type')}><option value="">Определить автоматически / старый контакт</option><option value="telegram">Telegram</option><option value="phone">Телефон</option><option value="email">Почта</option></select></label>
    <label>Контакт<input required maxLength={200} value={form.contact} onChange={set('contact')} placeholder="@username или +7…"/></label>
    {preview.contact?<p className="field-hint">Предпросмотр: <a href={preview.contact.href} target={preview.contact.type==='telegram'?'_blank':undefined} rel="noopener noreferrer">{preview.contact.label}</a> · {preview.contact.value}</p>
      :form.contact&&<p className="field-hint">{preview.error||'Нестандартный старый контакт будет показан текстом без ссылки'}</p>}
    <label>Описание<textarea maxLength={2000} rows={4} value={form.description||''} onChange={set('description')}/></label>
    <label className="checkbox-label"><input type="checkbox" checked={form.confirm_availability} onChange={e=>setForm(current=>({...current,confirm_availability:e.target.checked}))}/>Подтверждаю указанную цену и наличие у меня сейчас</label>
    <p className="field-hint">Это заявление продавца, а не независимая проверка товара. Редактирование описания не продлевает подтверждение.</p>
    {error&&<p role="alert" className="error">{error}</p>}
    <div className="result-actions"><Button type="submit" disabled={submitting}>{submitting?'Сохраняем…':initial?.id?'Сохранить изменения':'Опубликовать'}</Button><Button type="button" variant="secondary" onClick={onCancel}>Отмена</Button></div>
  </form>
}
