export function Icon({ name = 'box', size = 20, ...props }) {
  const paths = {
    chart: <><path d="M4 20V5m0 15h17M8 16v-4m5 4V8m5 8V4"/></>,
    pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    box: <><path d="m12 3 9 5v9l-9 5-9-5V8l9-5Z"/><path d="m3 8 9 5 9-5M12 13v9M8 5l9 5"/></>,
    chip: <><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 9h6v6H9zM9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/></>,
    gpu: <><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="10" cy="12" r="3"/><path d="M17 9v6M6 18v3m4-3v3m4-3v3"/></>,
    drive: <><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M4 14h16M8 17h.01M12 17h.01M8 8h8"/></>,
    shield: <><path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
    fan: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M12 10C7 3 4 9 10 12m4 0c7-5 1-8-2-2m0 4c5 7 8 1 2-2m-4 0c-7 5-1 8 2 2"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    refresh: <><path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/></>,
    filters: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="17" r="2"/></>,
    exchange: <><path d="M3 7h17m-5-5 5 5-5 5M21 17H4m5-5-5 5 5 5"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.box}</svg>
}
