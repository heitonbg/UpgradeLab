import { useState } from 'react'
import { Button } from '../ui/Button'

const INITIAL = {
  title: '',
  condition: 'Б/У',
  price: '',
  contact: '',
  description: '',
  listing_type: 'sale',
  exchange_for: '',
  photo_url: '',
}

export function ListingForm({ onSubmit, onCancel, initial }) {
  const [form, setForm] = useState({...INITIAL,...initial})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  async function photo(event) {
    const file=event.target.files?.[0]
    if(!file)return
    if(file.size>1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type)){setError('Выберите JPEG, PNG или WebP до 1 МБ.');return}
    const reader=new FileReader()
    reader.onload=()=>{setForm(f=>({...f,photo_url:reader.result}));setError(null)}
    reader.onerror=()=>setError('Не удалось прочитать фото')
    reader.readAsDataURL(file)
  }

  const handle = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await onSubmit({...form,price:form.listing_type==='exchange'?'Обмен':form.price,exchange_for:form.listing_type==='exchange'?form.exchange_for:null,photo_url:form.photo_url||null})
      setForm(INITIAL)
    } catch (err) {
      setError(err.message ?? 'Не удалось создать лот')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handle} className="listing-form space-y-3">
      <label>Тип объявления<select value={form.listing_type} onChange={set('listing_type')}><option value="sale">Продажа</option><option value="exchange">Обмен на компонент или услугу</option></select></label>
      <input
        required
        value={form.title}
        onChange={set('title')}
        placeholder="Название (например, RTX 3060 12GB)"
        className="w-full bg-dark border border-border rounded-md px-3 py-2 text-sm"
      />
      <div className="grid grid-cols-[120px_1fr] gap-2">
        <select
          value={form.condition}
          onChange={set('condition')}
          className="bg-dark border border-border rounded-md px-3 py-2 text-sm"
        >
          <option>Б/У</option>
          <option>Новое</option>
        </select>
        <input
          required={form.listing_type==='sale'}
          disabled={form.listing_type==='exchange'}
          value={form.price}
          onChange={set('price')}
          placeholder="Цена, ₽ или «Обмен»"
          className="bg-dark border border-border rounded-md px-3 py-2 text-sm"
        />
      </div>
      {form.listing_type==='exchange'&&<label>Что хотите получить<input required maxLength="500" value={form.exchange_for} onChange={set('exchange_for')} placeholder="Например: настройка ПК или Ryzen 5 с доплатой"/></label>}
      <label>Фото JPEG, PNG или WebP, до 1 МБ<input type="file" accept="image/jpeg,image/png,image/webp" onChange={photo}/></label>
      <label>Или HTTPS-ссылка на фото<input type="url" value={form.photo_url.startsWith('data:')?'':form.photo_url} onChange={set('photo_url')} placeholder="https://…"/></label>
      {form.photo_url&&<div><img className="listing-photo" src={form.photo_url} alt="Фото лота"/><button type="button" onClick={()=>setForm({...form,photo_url:''})}>Убрать фото</button></div>}
      <input
        required
        value={form.contact}
        onChange={set('contact')}
        placeholder="Телефон / Telegram"
        className="w-full bg-dark border border-border rounded-md px-3 py-2 text-sm"
      />
      <textarea
        value={form.description}
        onChange={set('description')}
        placeholder="Описание (необязательно)"
        rows={3}
        className="w-full bg-dark border border-border rounded-md px-3 py-2 text-sm"
      />
      {error && <p className="text-sm text-red-400">{error}</p>}
      <div className="flex gap-3 pt-1">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Публикация...' : 'Опубликовать'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>Отмена</Button>
      </div>
    </form>
  )
}
