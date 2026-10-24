import { ListingCard } from './ListingCard'

export function ListingGrid({ listings, loading, error }) {
  if (loading) return <p className="text-sm text-gray-400">Загрузка лотов...</p>
  if (error) return <p className="text-sm text-red-400">Ошибка: {error.message}</p>
  if (listings.length === 0) {
    return <p className="text-sm text-gray-500">Пока нет лотов. Создайте первый!</p>
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {listings.map((l) => <ListingCard key={l.id} listing={l} />)}
    </div>
  )
}