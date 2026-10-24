export function Select({ label, value, onChange, options, placeholder, disabled }) {
  return (
    <label className="block">
      {label && <span className="block text-sm text-gray-400 mb-1">{label}</span>}
      <select
        value={value}
        onChange={onChange}
        disabled={disabled}
        className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm
                   focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}