import { HardwareSearch } from '../ui/HardwareSearch'
import { Select } from '../ui/Select'
import { CategoryImage } from '../CategoryImage'
import { ListingCharacteristics } from './ListingCharacteristics'
import { ListingDeliveryEditor } from './ListingDeliveryEditor'
import { deliveryDraft, deliveryPayload, technicalText } from '../../lib/listingDetails'
import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { CityPicker } from '../CityPicker'
import { ListingPhoto } from './ListingPhoto'
import { useHardware } from '../../hooks/useHardware'
import { contactPreview } from '../../lib/contacts'

const INITIAL={title:'',condition:'Б/У',price:'',contact:'',contact_type:'telegram',description:'',
  listing_type:'sale',exchange_for:'',photo_url:'',city_id:null,category:null,hardware_id:null,
  publication_status:'active',confirm_availability:false,characteristics:{},delivery:null}
const categories=[['CPU','Процессор'],['GPU','Видеокарта'],['memory','RAM'],['motherboard','Материнская плата'],
  ['storage','Накопитель'],['psu','Блок питания'],['case','Корпус'],['cooler','Кулер']]
export function ListingForm({onSubmit,onCancel,initial,onDirtyChange}) {
  const [form,setForm]=useState({...INITIAL,...initial,characteristics:initial?.characteristics||{},delivery:deliveryDraft(initial?.delivery),confirm_availability:false})
  const original={...INITIAL,...initial,characteristics:initial?.characteristics||{},delivery:deliveryDraft(initial?.delivery),confirm_availability:false}
  const dirty=Object.keys(INITIAL).some(key=>JSON.stringify(form[key])!==JSON.stringify(original[key]))
  useEffect(()=>{onDirtyChange?.(dirty)},[dirty,onDirtyChange])
  useEffect(()=>{
    if(!dirty)return
    const leave=event=>{event.preventDefault();event.returnValue=''}
    window.addEventListener('beforeunload',leave)
    return()=>window.removeEventListener('beforeunload',leave)
  },[dirty])
  const [submitting,setSubmitting]=useState(false)
  const [error,setError]=useState('')
  const {cpus,gpus,rams,error:hardwareError}=useHardware()
  const models=(form.category==='CPU'?cpus:form.category==='GPU'?gpus:form.category==='memory'?rams:[])
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
      if(!form.city_id && (!initial?.id || initial.city_id)){const field=event.currentTarget.querySelector('[aria-label="Город"]');field?.closest('details')?.setAttribute('open','');field?.focus();throw Error('Выберите город из подсказки с регионом')}
      const legacy=initial?.id && form.contact===initial.contact && !form.contact_type
      if(!preview.contact&&!legacy)throw Error(preview.error||'Выберите тип контакта и введите полный контакт')
      const payload=Object.fromEntries(Object.keys(INITIAL).map(key=>[key,form[key]]))
      await onSubmit({...payload,contact:preview.contact?.value||form.contact,contact_type:preview.contact?.type||null,
        delivery:deliveryPayload(form.delivery),photo_url:form.photo_url||null,description:form.description||null,
        price:form.listing_type==='exchange'?'Обмен':form.price,
        exchange_for:form.listing_type==='exchange'?form.exchange_for:null})
      if(!initial?.id)setForm(INITIAL)
    }catch(error){setError(error.message||'Не удалось сохранить объявление')}
    finally{setSubmitting(false)}
  }
  return <form onSubmit={submit} onInvalid={e=>e.target.closest('details')?.setAttribute('open','')} className="listing-form"><p className="field-hint">Расскажите о комплектующей. Покупатели увидят цену, город и ваши условия передачи.</p><details open className="form-section"><summary>01 · Что вы продаёте</summary><div>
    <label>Тип объявления<Select aria-label="Тип объявления" value={form.listing_type} onChange={set('listing_type')}><option value="sale">Продажа</option><option value="exchange">Обмен</option></Select></label>
    <label>Название<input required minLength={2} maxLength={200} value={form.title} onChange={e=>setForm(current=>({...current,title:e.target.value,hardware_id:null}))}/></label>

    <label>Категория<Select aria-label="Категория" value={form.category||''} onChange={e=>{setForm(current=>({...current,category:e.target.value||null,hardware_id:null,characteristics:{}}))}}>
      <option value="">Обычное объявление</option>{categories.map(([key,label])=><option key={key} value={key}>{label}</option>)}</Select></label>
    {models.length>0&&<HardwareSearch hint="Привязка необязательна. Если модели нет, опишите товар вручную." label="Модель из каталога" items={models} value={form.hardware_id} onChange={id=>{const model=models.find(item=>item.id===id);if(!model){setForm(current=>({...current,hardware_id:null}));return}setForm(current=>({...current,hardware_id:model.id,title:form.category==='GPU'&&model.vram?`${model.name} ${model.vram}GB`:model.name,characteristics:form.category==='GPU'?{...current.characteristics,vram:model.vram}:form.category==='memory'?{...current.characteristics,ram_type:model.ram_type,capacity_gb:model.ram_capacity_gb}:current.characteristics}))}}/>}
    {hardwareError&&<p className="field-hint">Каталог моделей недоступен. Можно создать обычное объявление.</p>}
    {form.hardware_id&&<p className="field-hint">Модель каталога: {models.find(model=>model.id===form.hardware_id)?.name||'Выбрана'}.<button type="button" className="text-btn" onClick={()=>setForm(current=>({...current,hardware_id:null}))}>Убрать привязку</button></p>}
    </div></details><details className="form-section"><summary>02 · Характеристики</summary><div>
    {form.category&&<ListingCharacteristics category={form.category} value={form.characteristics} onChange={characteristics=>setForm(current=>({...current,characteristics}))}/>}
    {initial?.technical_assessment&&<p className="field-hint">{technicalText(initial.technical_assessment)}. После изменения данные будут проверены заново.</p>}
    </div></details><details className="form-section"><summary>03 · Город и передача товара</summary><div>
    <CityPicker value={form.city_id} onChange={city_id=>setForm(current=>({...current,city_id}))}/><ListingDeliveryEditor value={form.delivery} onChange={delivery=>setForm(current=>({...current,delivery}))}/>
    </div></details><details className="form-section" open><summary>04 · Цена и состояние</summary><div>
    <label>Состояние<Select aria-label="Состояние" value={form.condition} onChange={set('condition')}><option>Б/У</option><option>Новое</option><option>Неисправное</option></Select></label>
    <label>Цена<input required={form.listing_type==='sale'} disabled={form.listing_type==='exchange'} maxLength={50} value={form.price} onChange={set('price')}/></label>
    {form.listing_type==='exchange'&&<label>Что хотите получить<input required maxLength={500} value={form.exchange_for||''} onChange={set('exchange_for')}/></label>}
    <label>Статус<Select aria-label="Статус" value={form.publication_status} onChange={set('publication_status')}><option value="active">Активно</option><option value="sold">Продано</option><option value="withdrawn">Снято с публикации</option></Select></label>
    </div></details><details className="form-section"><summary>05 · Фотографии</summary><div>
    <label>Фото JPEG, PNG, WebP до 1 МБ<input type="file" accept="image/jpeg,image/png,image/webp" onChange={photo}/></label>
    <label>Или HTTPS-ссылка на фото<input type="url" maxLength={2000} value={form.photo_url?.startsWith('data:')?'':form.photo_url||''} onChange={set('photo_url')}/></label>
    {form.photo_url&&<><ListingPhoto src={form.photo_url} zoom/><button type="button" onClick={()=>setForm(current=>({...current,photo_url:null}))}>Убрать фото</button></>}
    </div></details><details className="form-section" open><summary>06 · Контакты и описание</summary><div>
    <label>Тип контакта<Select aria-label="Тип контакта" value={form.contact_type||''} onChange={set('contact_type')}><option value="">Определить автоматически / старый контакт</option><option value="telegram">Telegram</option><option value="phone">Телефон</option><option value="email">Почта</option></Select></label>
    <label>Контакт<input required maxLength={200} value={form.contact} onChange={set('contact')} placeholder="@username или +7…"/></label>
    {preview.contact?<p className="field-hint">Предпросмотр: <a href={preview.contact.href} target={preview.contact.type==='telegram'?'_blank':undefined} rel="noopener noreferrer">{preview.contact.label}</a> · {preview.contact.value}</p>
      :form.contact&&<p className="field-hint">{preview.error||'Нестандартный старый контакт будет показан текстом без ссылки'}</p>}
    <label>Описание<textarea maxLength={2000} rows={4} value={form.description||''} onChange={set('description')}/></label>
    </div></details><details className="form-section listing-preview"><summary>Предварительный просмотр</summary><div><CategoryImage category={form.category} label/><strong>{form.title||'Название объявления'}</strong><p>{form.price||'Цена не указана'}{form.price&&' ₽'} · {form.condition}</p><p className="field-hint">Характеристики и цена являются вашим заявлением; сервер проверит их после сохранения.</p></div></details>
    <label className="checkbox-label"><input type="checkbox" checked={form.confirm_availability} onChange={e=>setForm(current=>({...current,confirm_availability:e.target.checked}))}/>Подтверждаю указанную цену и наличие у меня сейчас</label>
    <p className="field-hint">Это заявление продавца, а не независимая проверка товара. Редактирование описания не продлевает подтверждение.</p>
    {error&&<p role="alert" className="error">{error}</p>}
    <div className="result-actions listing-actions"><Button type="submit" disabled={submitting}>{submitting?'Сохраняем…':initial?.id?'Сохранить изменения':'Опубликовать'}</Button><Button type="button" variant="secondary" onClick={onCancel}>Отмена</Button></div>
  </form>
}
