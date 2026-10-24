export function Card({ className = '', children }) {
  return (
    <div className={`bg-card border border-border rounded-lg p-5 ${className}`}>
      {children}
    </div>
  )
}