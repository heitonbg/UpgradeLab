import { useSteamRequirements } from '../../hooks/useSteamRequirements'
import { useEffect, useState } from 'react'
import { GAMES } from '../../constants/game'
import { request } from '../../api/client'
import { Combobox } from '../ui/Combobox'
const cache=new Map()
export function GamePicker({value,onChange}) {
 useSteamRequirements(value)
 const [query,setQuery]=useState(''),[remote,setRemote]=useState([]),[loading,setLoading]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let alive=true;setLoading(true);const timer=setTimeout(async()=>{
  try{const key=query.trim().toLowerCase();let data=cache.get(key);if(!data){data=await request('/api/games?q='+encodeURIComponent(key)+'&limit=20');if(!Array.isArray(data.items))throw Error();if(cache.size>=50)cache.delete(cache.keys().next().value);cache.set(key,data)}if(alive){setRemote(data.items);setError('')}}catch{if(alive)setError('Каталог игр временно недоступен. Основные игры остаются доступны.')}finally{if(alive)setLoading(false)}
 },200);return()=>{alive=false;clearTimeout(timer)}},[query])
 const local=GAMES.filter(g=>(!query&&g.value===value)||[g.label,...(g.aliases||[])].some(n=>n.toLowerCase().includes(query.toLowerCase()))).map(g=>({value:g.value,label:g.label}))
 const options=[...new Map([...local,...remote.map(g=>({value:g.name||g.id,label:g.name||g.id}))].map(g=>[g.value,g])).values()]
 return <div className="game-picker"><Combobox label="Игра" value={value} selectedOption={value?{value,label:GAMES.find(g=>g.value===value)?.label||remote.find(g=>g.name===value)?.name||value}:undefined} options={options} onChange={next=>onChange(next||'')} onQueryChange={next=>{if(next!==query){setRemote([]);setQuery(next)}}} clearable filter={false} loading={loading} error={error} required placeholder="Найдите игру…"/><small className="catalog-attribution">Каталог: <a href="https://github.com/emilioagustin83/pc-game-fps-dataset" target="_blank" rel="noopener noreferrer">PCGameBenchmarks · CC BY 4.0</a></small></div>
}
