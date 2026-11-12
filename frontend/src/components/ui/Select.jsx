import { Children, useLayoutEffect, useRef, useState, useMemo } from 'react'
import { Combobox } from './Combobox'
export function Select({children,value,onChange,disabled, ...props}) {
 const wrapper=useRef(null),[label,setLabel]=useState(props['aria-label']||'')
 useLayoutEffect(()=>{if(!props['aria-label'])setLabel([...wrapper.current.closest('label')?.childNodes||[]].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join(' ')||'Выбор значения')},[props['aria-label']])
 const options=useMemo(()=>Children.toArray(children).flatMap(child=>child?.props?.children&&child.type==='optgroup'?Children.toArray(child.props.children):[child]).filter(c=>c?.props).map(c=>({value:c.props.value??String(c.props.children),label:c.props.children,disabled:c.props.disabled})),[children])
 return <span className="ui-select" ref={wrapper}><Combobox showLabel={false} value={value} options={options} onChange={next=>onChange?.({target:{value:next}})} disabled={disabled} searchable={false} label={label} placeholder={options[0]?.label}/></span>
}
