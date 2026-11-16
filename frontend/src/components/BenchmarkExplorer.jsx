import { useEffect, useMemo, useState } from 'react'
import { request } from '../api/client'
import { FpshqReferenceTable } from './FpshqReferenceTable'

const fps = value => value == null ? '—' : `${Math.round(value).toLocaleString('ru-RU')} FPS`
const recordId = row => `${row.settings?.game}|${row.settings?.cpu}|${row.settings?.gpu}|${row.settings?.resolution}|${row.settings?.preset}|${row.settings?.scene}|${row.mean_fps}`

export function BenchmarkExplorer({onAdd}) {
 const [fpshqOpen,setFpshqOpen]=useState(false)
 const [filtersOpen,setFiltersOpen]=useState(false)
 const [activeTab,setActiveTab]=useState('games'),[game,setGame]=useState(''),[cpu,setCpu]=useState(''),[gpu,setGpu]=useState(''),[resolution,setResolution]=useState('')
 const [filters,setFilters]=useState({game:'',cpu:'',gpu:''}),[sort,setSort]=useState('fps_desc'),[offset,setOffset]=useState(0)
 const [data,setData]=useState(null),[community,setCommunity]=useState(null),[reference,setReference]=useState(null),[gpuReference,setGpuReference]=useState(null),[referenceKey,setReferenceKey]=useState('')
 const [loading,setLoading]=useState(false),[error,setError]=useState(''),[refsOpen,setRefsOpen]=useState(false),[selected,setSelected]=useState([])
 useEffect(()=>{
  if(activeTab!=='games')return
  let cancelled=false;setLoading(true);setError('')
  const query=new URLSearchParams({...filters,resolution,sort,offset:String(offset),limit:'50'})
  request(`/api/benchmarks?${query}`).then(value=>{if(!cancelled)setData(value)}).catch(()=>{if(!cancelled)setError('Измерения временно недоступны.')}).finally(()=>{if(!cancelled)setLoading(false)})
  return()=>{cancelled=true}
 },[activeTab,filters,offset,resolution,sort])
 useEffect(()=>{
  if(activeTab!=='games')return
  let cancelled=false
  request(`/api/benchmarks/community?${new URLSearchParams({game:filters.game})}`).then(value=>{if(!cancelled)setCommunity(value)}).catch(()=>{if(!cancelled)setCommunity(null)})
  return()=>{cancelled=true}
 },[activeTab,filters.game])
 useEffect(()=>{
  if(activeTab!=='games'){if(referenceKey)setReferenceKey('');return}
  if(!refsOpen){if(!reference&&!gpuReference&&referenceKey)setReferenceKey('');return}
  const queryKey=JSON.stringify({game:filters.game,gpu:filters.gpu,resolution})
  if(referenceKey===queryKey)return
  let cancelled=false
  setReferenceKey(queryKey);setReference(null);setGpuReference(null)
  const params=new URLSearchParams({game:filters.game,resolution,limit:'50'})
  const gpuParams=new URLSearchParams({game:filters.game,gpu:filters.gpu,resolution,limit:'50'})
  request(`/api/benchmarks/game-reference?${params}`).then(value=>{if(!cancelled)setReference(value)}).catch(()=>{if(!cancelled)setReference(null)})
  request(`/api/benchmarks/gpu-reference?${gpuParams}`).then(value=>{if(!cancelled)setGpuReference(value)}).catch(()=>{if(!cancelled)setGpuReference(null)})
  return()=>{cancelled=true}
 },[refsOpen,activeTab,filters,resolution,referenceKey])
 const rows=useMemo(()=>{
  return data?.items||[]
 },[data])
 const selectedRows=rows.filter(row=>selected.includes(recordId(row)))
 function submit(event){event.preventDefault();setFiltersOpen(false);setOffset(0);setSelected([]);setReference(null);setGpuReference(null);setFilters({game:game.trim(),cpu:cpu.trim(),gpu:gpu.trim()})}
 function toggleCompare(row){const id=recordId(row);setSelected(current=>current.includes(id)?current.filter(value=>value!==id):current.length<3?[...current,id]:current)}
 return <section className="benchmark-page"><header className="page-heading benchmark-page-heading"><div><p className="eyebrow">Измерения производительности</p><h1>Бенчмарки</h1><p>Игровые измерения показываются отдельно от синтетических оценок CPU и GPU.</p></div><button type="button" className="primary-btn" onClick={onAdd}>Отправить свой бенчмарк</button></header>
  <div className="benchmark-tabs" role="group" aria-label="Бенчмарки"><span className="active">Игровые FPS</span></div>

  {activeTab==='games'&&<div className="benchmark-games-tab"><button type="button" className="benchmark-filter-toggle secondary-btn" aria-expanded={filtersOpen} aria-controls="benchmark-filters" onClick={()=>setFiltersOpen(value=>!value)}>{filtersOpen?"Скрыть фильтры":"Фильтры и сортировка"}</button><form id="benchmark-filters" className={"benchmark-filters panel"+(filtersOpen?" mobile-filters-open":"")} onSubmit={submit}><label>Игра<input value={game} onChange={e=>setGame(e.target.value)} placeholder="Cyberpunk 2077" maxLength={100}/></label><label>Процессор<input value={cpu} onChange={e=>setCpu(e.target.value)} placeholder="Ryzen 5 5600" maxLength={100}/></label><label>Видеокарта<input value={gpu} onChange={e=>setGpu(e.target.value)} placeholder="RTX 5060" maxLength={100}/></label><label>Разрешение<select value={resolution} onChange={e=>setResolution(e.target.value)}><option value="">Любое</option><option>1280x720</option><option>1920x1080</option><option>2560x1440</option><option>3840x2160</option></select></label><label>Сортировка<select value={sort} onChange={e=>setSort(e.target.value)}><option value="fps_desc">FPS: по убыванию</option><option value="fps_asc">FPS: по возрастанию</option><option value="game">Игра: А—Я</option></select></label><button type="submit" className="primary-btn">Применить фильтры</button></form>
   {loading&&<p role="status">Загружаем измерения…</p>}{error&&<p role="alert">{error}</p>}{data&&!loading&&<><div className="benchmark-table-caption"><span>{data.total} групп измерений · выбрано для сравнения: {selected.length}/3</span><button type="button" className="text-btn" onClick={()=>setRefsOpen(value=>!value)}>{refsOpen?'Скрыть':'Показать'} дополнительные сводки</button></div>{!rows.length?<div className="panel benchmark-empty"><h2>Совпадений нет</h2><p>Измените фильтр игры или комплектующих. Другие конфигурации не подставляются вместо точной пары.</p></div>:<div className="benchmark-table-wrap"><table className="benchmark-data-table benchmark-measurements-table" role="table"><thead><tr><th>Игра / настройки</th><th>CPU</th><th>GPU</th><th>Средний FPS</th><th>1% Low</th><th>Выборка</th><th>Сравнить</th></tr></thead><tbody>{rows.map(row=>{const s=row.settings||{},id=recordId(row);return <tr key={id}><th scope="row"><strong>{s.game}</strong><small>{[s.game_version,s.resolution,s.preset,s.scene].filter(Boolean).join(' · ')}</small><small>{s.rt===true?'RT включён':s.rt===false?'RT выключен':'RT неизвестен'} · {s.upscaling||'апскейл не указан'}{s.frame_generation===true?' · FG включён':''}</small></th><td>{s.cpu||'Не указан'}</td><td>{s.gpu||'Не указана'}{s.vram_gb?` · ${s.vram_gb} ГБ`:''}</td><td className="benchmark-number">{fps(row.mean_fps)}</td><td className="benchmark-number">{fps(row.one_percent_low_fps)}</td><td>{row.observations} запусков<small>{row.independent_publishers} источн. · {row.confidence==='multi_source'?'несколько источников':'ограниченная выборка'}</small></td><td><input aria-label={`Сравнить ${s.game} ${s.cpu} ${s.gpu}`} type="checkbox" checked={selected.includes(id)} disabled={!selected.includes(id)&&selected.length>=3} onChange={()=>toggleCompare(row)}/></td></tr>})}</tbody></table></div>}
   {selectedRows.length>1&&<section className="benchmark-compare panel"><h2>Сравнение FPS</h2><div>{selectedRows.map(row=><article key={recordId(row)}><strong>{row.settings.game}</strong><span>{row.settings.cpu} · {row.settings.gpu}</span><b>{fps(row.mean_fps)}</b><small>1% Low: {fps(row.one_percent_low_fps)}</small></article>)}</div><p className="field-hint">Сравнивайте результаты только при одинаковой игре, разрешении и настройках. Различия тестовых систем могут влиять на результат.</p></section>}
   <div className="result-actions"><button type="button" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-50))}>Назад</button><span>{data.total?`${offset+1}–${Math.min(offset+50,data.total)} из ${data.total}`:'0 результатов'}</span><button type="button" disabled={offset+50>=data.total||loading} onClick={()=>setOffset(offset+50)}>Дальше</button></div></>}
   {refsOpen&&<div className="benchmark-reference-tables">{reference?.items?.length>0&&<section className="panel"><h2>Сводные данные FPSHQ</h2><p className="field-hint">Агрегаты по видеокартам из разных обзоров, не результат конкретной пары CPU/GPU. FPSHQ · CC BY 4.0.</p><div className="benchmark-table-wrap"><table className="benchmark-data-table"><thead><tr><th>Игра</th><th>Разрешение / настройки</th><th>Медиана FPS</th><th>Диапазон / объём</th><th>Источник</th></tr></thead><tbody>{reference.items.map((r,i)=><tr key={`${r.game}-${r.resolution}-${i}`}><th>{r.game}</th><td>{r.resolution} · {r.preset}</td><td>{r.fps_median}</td><td>{r.fps_p25}–{r.fps_p75} · {r.measurements} тестов / {r.gpus_measured} GPU</td><td><a href={r.url} target="_blank" rel="noreferrer">Открыть ↗</a></td></tr>)}</tbody></table></div></section>}{gpuReference?.items?.length>0&&<section className="panel"><h2>Сводки по GPU</h2><div className="benchmark-table-wrap"><table className="benchmark-data-table"><thead><tr><th>Игра</th><th>GPU / настройки</th><th>FPS</th><th>1% Low</th><th>Источник</th></tr></thead><tbody>{gpuReference.items.map((r,i)=><tr key={`${r.game}-${r.gpu}-${i}`}><th>{r.game}</th><td>{r.gpu} · {r.resolution} · {r.preset}</td><td>{r.average_fps}</td><td>{r.one_percent_low??'—'}</td><td><a href={r.url} target="_blank" rel="noreferrer">FPSHQ ↗</a></td></tr>)}</tbody></table></div></section>}</div>}
   {community?.items?.length>0&&<section className="panel"><h2>Проверенные пользовательские измерения</h2><div className="benchmark-table-wrap"><table className="benchmark-data-table"><thead><tr><th>Игра</th><th>CPU / GPU</th><th>Настройки</th><th>FPS</th><th>Источник</th></tr></thead><tbody>{community.items.map(item=>{const r=item.result;return <tr key={item.id}><th>{r.game}</th><td>{r.cpu} / {r.gpu}</td><td>{r.resolution} · {r.preset}</td><td>{fps(r.average_fps)}</td><td>{r.evidence_url?<a href={r.evidence_url} target="_blank" rel="noreferrer">Подтверждение ↗</a>:'Проверено модератором'}</td></tr>})}</tbody></table></div></section>}
   <details className="benchmark-extra" onToggle={event=>setFpshqOpen(event.currentTarget.open)}><summary>Дополнительные GPU-данные FPSHQ</summary>{fpshqOpen&&<FpshqReferenceTable/>}</details>
  </div>}
 </section>
}
