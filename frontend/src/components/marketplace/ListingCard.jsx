export function ListingCard({ listing }) {
  const isGpu = /gpu|видеокарт|rtx|gtx|geforce|radeon|rx\s*\d/i.test(listing.title)
  const date = new Date(listing.created_at).toLocaleString('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
  return (
    <div className="bg-card border border-border hover:border-accent/40 rounded-2xl p-5 space-y-3 min-h-[180px] transition-colors">
      <div className="text-[11px] text-gray-400">{isGpu ? 'Видеокарта' : 'Комплектующее'}</div>
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{listing.title}</div>
        <span className="text-xs px-2 py-0.5 rounded bg-border text-gray-300 shrink-0">
          {listing.condition}
        </span>
      </div>
      <div className="text-xl text-accent font-bold">{listing.price}</div>
      {listing.description && (
        <p className="text-xs text-gray-500 pt-1">{listing.description}</p>
      )}
      <div className="text-[11px] text-gray-500 pt-2 border-t border-border flex justify-between"><span>{date}</span><span>Подробнее</span></div>
    </div>
  )
}
