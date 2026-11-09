import { useEffect, useId, useState } from 'react'
import { request } from '../api/client'
import { cityLabel, citySuggestions } from '../lib/cities'
let pending
export function CityPicker({ value, onChange, label='Город' }) {
  const id=useId()
  const [cities,setCities]=useState([])
  const [query,setQuery]=useState('')
  const [error,setError]=useState('')
  useEffect(()=>{
    let alive=true
    if(!pending) pending=request('/api/cities').catch(error=>{pending=null;throw error})
    pending.then(data=>{if(alive)setCities(data)}).catch(()=>{if(alive)setError('Не удалось загрузить справочник городов')})
    return()=>{alive=false}
  },[])
  useEffect(()=>{
    const city=cities.find(city=>city.city_id===value)
    if(city)setQuery(cityLabel(city))
  },[value,cities])
  useEffect(()=>{
    if(!query || cities.some(city=>cityLabel(city)===query))return
    let alive=true
    const timer=setTimeout(()=>{
      request('/api/cities?q='+encodeURIComponent(query.slice(0,100))).then(found=>{
        if(alive)setCities(previous=>[...new Map([...previous,...found].map(city=>[city.city_id,city])).values()])
      }).catch(()=>{if(alive)setError('Не удалось найти город; повторите ввод')})
    },180)
    return()=>{alive=false;clearTimeout(timer)}
  },[query])
  useEffect(()=>{
    if(!value)return
    let alive=true
    request('/api/cities?q='+encodeURIComponent(value)).then(found=>{
      if(alive)setCities(previous=>[...new Map([...previous,...found].map(city=>[city.city_id,city])).values()])
    }).catch(()=>{})
    return()=>{alive=false}
  },[value])
  function choose(text) {
    setQuery(text)
    const city=cities.find(city=>cityLabel(city)===text)
    onChange(city?.city_id||null)
  }
  return <label className="city-picker">{label}<input aria-label={label} type="search" list={id} value={query} maxLength={150}
    placeholder="Все города / начните вводить название" onChange={e=>choose(e.target.value)}/>
    <datalist id={id}>{citySuggestions(cities,query).map(city=><option key={city.city_id} value={cityLabel(city)}/>)}</datalist>
    {(query||value)&&<button type="button" className="text-btn" onClick={()=>choose('')}>Очистить город</button>}
    <small>{error || (cities.some(city=>city.city_id===value) ? 'Город выбран из справочника' : query ? 'Выберите подсказку с регионом' : 'Город не указан; география неизвестна')}</small>
  </label>
}
