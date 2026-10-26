import { ListingCard } from './ListingCard'

export function ListingGrid({ listings, loading, onClick, emptyMessage }) {
  if (loading) return <p className="text-sm text-gray-400">Загрузка лотов...</p>
  if (!listings || listings.length === 0) {
    return <p className="text-sm text-gray-500 p-6 border border-border rounded-xl">{emptyMessage || 'Пока нет лотов. Создайте первый!'}</p>
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {listings.map((l) => (
        <button key={l.id} type="button" onClick={() => onClick?.(l)} className="text-left cursor-pointer w-full">
          <ListingCard listing={l} />
        </button>
      ))}
      <div className="text-xs text-gray-600 md:col-span-2 pt-1">
        Показано: {listings.length} лотов
      </div>
    </div>
  )
}
