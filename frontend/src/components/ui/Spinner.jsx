export function Spinner({ label = 'Загрузка...' }) {
  return (
    <div className="loading-inline" role="status" aria-live="polite">
      <span className="loading-ring" aria-hidden="true" />
      {label}
    </div>
  )
}
