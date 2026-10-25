import { useState } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export function ListingDetail({ listing, onClose }) {
  const [photos, setPhotos] = useState([])
  
  const date = new Date(listing.created_at).toLocaleString('ru-RU', {
    dateStyle: 'long',
    timeStyle: 'short',
  })

  const handlePhotoUpload = (e) => {
    const files = Array.from(e.target.files)
    const newPhotos = files.map(file => ({
      url: URL.createObjectURL(file),
      name: file.name,
    }))
    setPhotos([...photos, ...newPhotos])
  }

  // Извлекаем цену из строки
  const priceNum = parseInt(listing.price.replace(/\D/g, '')) || 0
  const priceStr = listing.price

  // Определяем тип
  const isCpu = /cpu|процессор|ryzen|core\s*\d/i.test(listing.title.toLowerCase())
  const isGpu = /gpu|видеокарт|rtx|gtx|rx\s*\d|geforce|radeon/i.test(listing.title.toLowerCase())

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Фото */}
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {photos.map((photo, idx) => (
            <div key={idx} className="relative aspect-video rounded-lg overflow-hidden bg-dark border border-border">
              <img src={photo.url} alt={photo.name} className="w-full h-full object-cover" />
            </div>
          ))}
          {photos.length === 0 && (
            <div className="col-span-2 aspect-video rounded-lg bg-dark border border-border flex items-center justify-center text-gray-600">
              Нет фотографий
            </div>
          )}
        </div>
        <label className="block">
          <span className="text-xs text-gray-500">Добавить фото</span>
          <input
            type="file"
            multiple
            accept="image/*"
            onChange={handlePhotoUpload}
            className="block w-full text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-accent/20 file:text-accent file:cursor-pointer hover:file:bg-accent/30"
          />
        </label>
      </div>

      {/* Информация */}
      <Card className="space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <span className={`text-xs px-2 py-0.5 rounded ${
              listing.condition === 'Новое' 
                ? 'bg-green-500/20 text-green-400' 
                : 'bg-blue-500/20 text-blue-400'
            }`}>
              {listing.condition}
            </span>
            {isCpu && <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 ml-2">Процессор</span>}
            {isGpu && <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 ml-2">Видеокарта</span>}
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-accent">{priceStr}</p>
          </div>
        </div>

        <p className="text-sm text-gray-400">{listing.description || 'Описание отсутствует'}</p>

        <div className="text-xs text-gray-600">
          Опубликовано: {date}
        </div>
      </Card>

      {/* Контакты */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-white">Контакт продавца:</p>
        <div className="flex flex-wrap gap-2">
          {/* Telegram */}
          {listing.contact.includes('@') || listing.contact.includes('t.me') ? (
            <a
              href={`https://t.me/${listing.contact.replace('@', '').replace('t.me/', '')}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 min-w-[150px] px-4 py-3 rounded-lg bg-blue-500/20 border border-blue-500/30 text-blue-400 text-sm font-medium hover:bg-blue-500/30 transition flex items-center justify-center gap-2"
            >
              <span>✈️</span> Написать в Telegram
            </a>
          ) : (
            <a
              href={`https://t.me/+${listing.contact.replace(/\D/g, '')}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 min-w-[150px] px-4 py-3 rounded-lg bg-blue-500/20 border border-blue-500/30 text-blue-400 text-sm font-medium hover:bg-blue-500/30 transition flex items-center justify-center gap-2"
            >
              <span>✈️</span> Telegram
            </a>
          )}

          {/* VK */}
          <a
            href="https://vk.com/im"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 min-w-[150px] px-4 py-3 rounded-lg bg-blue-600/20 border border-blue-600/30 text-blue-300 text-sm font-medium hover:bg-blue-600/30 transition flex items-center justify-center gap-2"
          >
            <span>💬</span> Написать в VK
          </a>

          {/* Телефон */}
          {listing.contact.match(/\d{10,}/) && (
            <a
              href={`tel:${listing.contact.replace(/\D/g, '')}`}
              className="flex-1 min-w-[150px] px-4 py-3 rounded-lg bg-green-500/20 border border-green-500/30 text-green-400 text-sm font-medium hover:bg-green-500/30 transition flex items-center justify-center gap-2"
            >
              <span>📞</span> Позвонить
            </a>
          )}
        </div>
      </div>

      <div className="flex gap-3 pt-2">
        <Button variant="secondary" onClick={onClose}>Закрыть</Button>
      </div>
    </div>
  )
}
