import { useState } from 'react'
import { searchHardware } from '../../lib/hardware'
import { Combobox } from './Combobox'
export function HardwareSearch({label,items,value,onChange,placeholder,hint}) {
 const [query,setQuery]=useState('')
 const option=item=>({value:item.id,label:item.name,description:[item.socket,item.vram?`${item.vram} GB`:null,item.ram_type].filter(Boolean).join(' · ')})
 const selected=items.find(item=>item.id===Number(value))
 return <Combobox label={label} value={value} selectedOption={selected?option(selected):undefined} options={searchHardware(items,query).slice(0,40).map(option)} onChange={onChange} onQueryChange={setQuery} filter={false} clearable placeholder={placeholder||'Найдите модель…'} hint={hint} emptyMessage="Модель не найдена. Попробуйте другое название."/>
}
