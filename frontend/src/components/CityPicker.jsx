import { useCallback,useEffect,useState } from 'react'
import { request } from '../api/client'
import { createCityLoader } from '../lib/cityLoader'
import { citySuggestions } from '../lib/cities'
import { Combobox } from './ui/Combobox'
const loader=createCityLoader(request)
export function CityPicker({value,onChange,label='Город',required=false}) {
 const [cities,setCities]=useState([]),[query,setQuery]=useState(''),[loading,setLoading]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0)
 const merge=useCallback(rows=>setCities(previous=>[...new Map([...previous,...rows].map(c=>[c.city_id,c])).values()]),[])
 useEffect(()=>{let alive=true;setLoading(true);const timer=setTimeout(async()=>{try{const rows=query?await loader.search(query):await loader.load(retry>0);if(alive){merge(rows);setError('')}}catch{if(alive)setError('Не удалось загрузить города. Выбранный город сохранён.')}finally{if(alive)setLoading(false)}},180);return()=>{alive=false;clearTimeout(timer)}},[query,retry,merge])
 useEffect(()=>{if(!value)return;let alive=true;loader.search(value).then(rows=>{if(alive)merge(rows)}).catch(()=>{if(alive)setError('Не удалось загрузить название выбранного города.')});return()=>{alive=false}},[value,merge])
 const suggestions=citySuggestions(cities,query)
 const selected=cities.find(c=>c.city_id===value)
 const options=[...new Map([...(selected?[selected]:[]),...suggestions].map(c=>[c.city_id,{value:c.city_id,label:c.name,description:c.region}])).values()]
 return <Combobox required={required} label={label} value={value} options={options} onChange={onChange} onQueryChange={setQuery} loading={loading} error={error} onRetry={()=>setRetry(n=>n+1)} clearable placeholder="Город или регион" hint={selected?selected.region:'Выберите город из списка; регион указан в подсказке.'}/>
}
