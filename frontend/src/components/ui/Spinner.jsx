export function Spinner({ label = 'Загрузка...' }) {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-400">
      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-accent" />
      {label}
    </div>
  )
}