import { ListingCard } from './ListingCard'

export function ListingGrid({ listings, loading, onClick }) {
  if (loading) return <p className="text-sm text-gray-400">Загрузка лотов...</p>
  if (!listings || listings.length === 0) {
    return <p className="text-sm text-gray-500">Пока нет лотов. Создайте первый!</p>
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {listings.map((l) => (
        <div key={l.id} onClick={() => onClick && onClick(l)} className="cursor-pointer hover:scale-[1.02] transition-transform">
          <ListingCard listing={l} />
        </div>
      ))}
      <div className="text-xs text-gray-600 md:col-span-2 pt-1">
        Показано: {listings.length} лотов
      </div>
    </div>
  )
}
