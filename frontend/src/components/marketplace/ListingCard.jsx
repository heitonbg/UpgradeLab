export function ListingCard({ listing }) {
  const date = new Date(listing.created_at).toLocaleString('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
  return (
    <div className="bg-card border border-border rounded-lg p-4 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{listing.title}</div>
        <span className="text-xs px-2 py-0.5 rounded bg-border text-gray-300 shrink-0">
          {listing.condition}
        </span>
      </div>
      <div className="text-sm text-accent font-medium">{listing.price}</div>
      <div className="text-xs text-gray-400">{listing.contact}</div>
      {listing.description && (
        <p className="text-xs text-gray-500 pt-1">{listing.description}</p>
      )}
      <div className="text-[11px] text-gray-600 pt-1">{date}</div>
    </div>
  )
}