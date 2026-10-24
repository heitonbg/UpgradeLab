import { useState } from 'react'
import { Button } from '../ui/Button'

const INITIAL = {
  title: '',
  condition: 'Б/У',
  price: '',
  contact: '',
  description: '',
}

export function ListingForm({ onSubmit, onCancel }) {
  const [form, setForm] = useState(INITIAL)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const handle = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await onSubmit(form)
      setForm(INITIAL)
    } catch (err) {
      setError(err.message ?? 'Не удалось создать лот')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handle} className="space-y-3">
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
          required
          value={form.price}
          onChange={set('price')}
          placeholder="Цена, ₽ или «Обмен»"
          className="bg-dark border border-border rounded-md px-3 py-2 text-sm"
        />
      </div>
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