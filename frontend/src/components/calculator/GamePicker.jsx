import { useEffect, useState } from 'react'
import { GAMES } from '../../constants/game'
import { request } from '../../api/client'
import { Combobox } from '../ui/Combobox'
const cache=new Map()
export function GamePicker({value,onChange}) {
 const [query,setQuery]=useState(''),[remote,setRemote]=useState([]),[loading,setLoading]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let alive=true;setLoading(true);const timer=setTimeout(async()=>{
  try{const key=query.trim().toLowerCase();let data=cache.get(key);if(!data){data=await request('/api/games?q='+encodeURIComponent(key)+'&limit=20');if(!Array.isArray(data.items))throw Error();if(cache.size>=50)cache.delete(cache.keys().next().value);cache.set(key,data)}if(alive){setRemote(data.items);setError('')}}catch{if(alive)setError('Каталог игр временно недоступен. Основные игры остаются доступны.')}finally{if(alive)setLoading(false)}
 },200);return()=>{alive=false;clearTimeout(timer)}},[query])
 const local=GAMES.filter(g=>(!query&&g.value===value)||[g.label,...(g.aliases||[])].some(n=>n.toLowerCase().includes(query.toLowerCase()))).map(g=>({value:g.value,label:g.label,description:'Поддерживается оценка FPS'}))
 const options=[...new Map([...local,...remote.map(g=>({value:g.id,label:g.name,disabled:!g.fps_supported,description:g.fps_supported?'Поддерживается оценка FPS':'Пока недостаточно данных для FPS'}))].map(g=>[g.value,g])).values()]
 return <div className="game-picker"><Combobox label="Игра" value={value} selectedOption={GAMES.find(g=>g.value===value)?{value,label:GAMES.find(g=>g.value===value).label}:undefined} options={options} onChange={next=>onChange(next||'')} onQueryChange={next=>{if(next!==query){setRemote([]);setQuery(next)}}} clearable filter={false} loading={loading} error={error} required placeholder="Найдите игру…" hint="В каталоге более 16 000 игр. Выбрать для расчёта можно игры с поддержкой FPS."/><small className="catalog-attribution">Каталог: <a href="https://github.com/emilioagustin83/pc-game-fps-dataset" target="_blank" rel="noopener noreferrer">PCGameBenchmarks · CC BY 4.0</a></small></div>
}
