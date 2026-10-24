export function Button({
  variant = 'primary',
  className = '',
  ...props
}) {
  const base =
    'inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium ' +
    'transition disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none ' +
    'focus:ring-2 focus:ring-accent/40'
  const variants = {
    primary: 'bg-accent text-black hover:opacity-90',
    secondary: 'bg-card text-gray-200 border border-border hover:bg-border/50',
    ghost: 'text-gray-300 hover:text-white',
    danger: 'text-red-400 hover:text-red-300',
  }
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />
}