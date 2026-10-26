import { useId, useState } from 'react'
import { searchHardware } from '../../lib/hardware'

export function HardwareSearch({ label, items, value, onChange, placeholder }) {
  const id = useId()
  const selected = items.find(item => item.id === Number(value))
  const [query, setQuery] = useState(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const text = query ?? selected?.name ?? ''
  const matches = searchHardware(items, open && query !== null ? query : '').slice(0, 40)
  function select(item) { onChange(item.id); setQuery(null); setOpen(false); setActive(0) }
  return <div className="hardware-search" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setQuery(null) } }}>
    <label htmlFor={id}>{label}</label>
    <div className="search-input-wrap"><input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`} aria-activedescendant={open && matches[active] ? `${id}-${matches[active].id}` : undefined} autoComplete="off" value={text} placeholder={placeholder} onFocus={()=>{setQuery('');setOpen(true);setActive(0)}} onChange={e=>{setQuery(e.target.value);onChange(null);setOpen(true);setActive(0)}} onKeyDown={e=>{
      if (e.key==='ArrowDown') { e.preventDefault();setOpen(true);setActive(i=>Math.min(i+1,matches.length-1)) }
      if (e.key==='ArrowUp') { e.preventDefault();setActive(i=>Math.max(0,i-1)) }
      if (e.key==='Enter' && open) { e.preventDefault();if(matches[active])select(matches[active]) }
      if (e.key==='Escape') { setOpen(false);setQuery(null) }
    }}/><span aria-hidden="true">⌕</span></div>
    {open && <ul id={`${id}-options`} role="listbox" className="hardware-options">{matches.length ? matches.map((item,index)=><li id={`${id}-${item.id}`} role="option" aria-selected={item.id===Number(value)} key={item.id} className={active===index?'highlighted':''} onMouseEnter={()=>setActive(index)} onMouseDown={e=>{e.preventDefault();select(item)}}><span>{item.name}</span>{item.avg_price && <small>{item.avg_price.toLocaleString('ru-RU')} ₽</small>}</li>) : <li className="search-no-results">Модель не найдена. Попробуйте указать номер без производителя.</li>}</ul>}
    {!selected && !open && text && <small className="field-hint">Выберите модель из результатов поиска.</small>}
  </div>
}
