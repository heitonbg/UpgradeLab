import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// One focus model: focus stays on the trigger, including when the list is portalled.
export function Combobox({label, showLabel=true, value, selectedOption, options=[], onChange, onQueryChange, searchable=true, placeholder='Выберите вариант', loading=false, error='', emptyMessage='Ничего не найдено', disabled=false, clearable=false, required=false, hint='', filter=true, onRetry}) {
 const id=useId(), anchor=useRef(null), panel=useRef(null), input=useRef(null)
 const selected=options.find(option=>String(option.value)===String(value))||selectedOption
 const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[typing,setTyping]=useState(false),[active,setActive]=useState(-1),[position,setPosition]=useState({})
 const items=(filter&&searchable&&query?options.filter(o=>(o.label+' '+(o.description||'')).toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru'))):options).slice(0,50)
 const close=()=>{setOpen(false);setQuery('');setTyping(false);setActive(-1)}
 useEffect(()=>{if(!open)return;const outside=e=>{if(!anchor.current?.contains(e.target)&&!panel.current?.contains(e.target))close()};document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside)},[open])
 useLayoutEffect(()=>{
  if(!open)return
  function place(){const r=anchor.current.querySelector('.ui-combobox-control').getBoundingClientRect(),height=window.visualViewport?.height||innerHeight;if(r.bottom<0||r.top>height){setOpen(false);return}const below=height-r.bottom-12,above=r.top-12,up=below<180&&above>below;setPosition({position:'fixed',left:Math.max(8,Math.min(r.left,innerWidth-Math.min(r.width,innerWidth-16)-8)),width:Math.min(r.width,innerWidth-16),maxHeight:Math.max(100,Math.min(300,up?above:below)),...(up?{bottom:height-r.top+6}:{top:r.bottom+6})})}
  place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);window.visualViewport?.addEventListener('resize',place)
  return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);window.visualViewport?.removeEventListener('resize',place)}
 },[open])
 const optionKeys=options.map(o=>String(o.value)+':'+Boolean(o.disabled)).join('|')
 useEffect(()=>{setActive(items.findIndex(o=>!o.disabled))},[query,optionKeys])
 useEffect(()=>{if(searchable&&input.current)input.current.setCustomValidity(required&&!selected?'Выберите значение из списка':'')},[required,selected,searchable])
 function choose(option){if(option.disabled)return;onChange(option.value);close();input.current?.focus()}
 function key(e){
  if(e.key==='Escape'&&open){e.preventDefault();e.stopPropagation();close();return}
  if(e.key==='Tab'){close();return}
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
   e.preventDefault();if(!open){setOpen(true);onQueryChange?.('')}
   const direction=e.key==='ArrowDown'?1:-1;let index=active
   for(let n=0;n<items.length;n++){index=(index+direction+items.length)%items.length;if(!items[index].disabled){setActive(index);requestAnimationFrame(()=>document.getElementById(id+'-'+index)?.scrollIntoView({block:'nearest'}));break}}
  }
  if(e.key==='Enter'&&open){e.preventDefault();if(active>=0&&items[active])choose(items[active])}
  else if((e.key==='Enter'||e.key===' ')&&!searchable){e.preventDefault();setOpen(!open)}
 }
 const common={id,role:'combobox','aria-label':label,'aria-expanded':open,'aria-controls':open?id+'-list':undefined,'aria-activedescendant':open&&active>=0?id+'-'+active:undefined,'aria-describedby':hint||error?id+'-hint':undefined,disabled,onKeyDown:key,onBlur:e=>{if(!panel.current?.contains(e.relatedTarget))close()}}
 return <div className="ui-field ui-combobox" ref={anchor}>
  {label&&showLabel&&<label htmlFor={id}>{label}</label>}
  <div className="ui-combobox-control">
   {searchable?<input {...common} ref={input} type="text" autoComplete="off" aria-autocomplete="list" placeholder={placeholder} value={open&&typing?query:selected?.label||''} required={required} onFocus={()=>{setOpen(true);setTyping(false);onQueryChange?.('');requestAnimationFrame(()=>input.current?.select())}} onClick={()=>{if(!open){setOpen(true);onQueryChange?.('')}}} onChange={e=>{setTyping(true);setQuery(e.target.value);onQueryChange?.(e.target.value);setOpen(true)}}/>:<button {...common} ref={input} type="button" onClick={()=>setOpen(!open)}><span>{selected?.label||placeholder}</span><span aria-hidden="true">⌄</span></button>}
   {clearable&&value!==null&&value!==undefined&&value!==''&&<button className="ui-clear" type="button" aria-label={'Очистить: '+label} onClick={()=>{onChange(null);setQuery('');onQueryChange?.('');input.current?.focus()}}>×</button>}
  </div>
  {(hint||error)&&<small id={id+'-hint'} className="field-hint" role={error?'status':undefined}>{error||hint}{error&&onRetry&&<button type="button" className="text-btn" onClick={onRetry}>Повторить</button>}</small>}
  {open&&createPortal(<div ref={panel} className="ui-options" style={position} onPointerDown={e=>e.preventDefault()}>
   {loading&&<p role="status" className="ui-option-status">Ищем…</p>}
   <div id={id+'-list'} role="listbox" aria-label={label} aria-busy={loading}>{items.slice(0,50).map((option,index)=><div id={id+'-'+index} key={option.value} role="option" aria-selected={String(option.value)===String(value)} aria-disabled={option.disabled||undefined} className={'ui-option '+(active===index?'is-active':'')} onPointerMove={()=>!option.disabled&&setActive(index)} onClick={()=>choose(option)}><span><strong>{option.label}</strong>{option.description&&<small>{option.description}</small>}</span>{String(option.value)===String(value)&&<span aria-hidden="true">✓</span>}</div>)}</div>
   {!loading&&!items.length&&<p className="ui-option-status" role={error?undefined:'status'}>{error?'Повторите загрузку с помощью кнопки под полем.':emptyMessage}</p>}
  </div>,document.body)}
 </div>
}
