import { useRef, useState } from 'react'
import { request } from '../api/client'
const empty={game:'',cpu:'',gpu:'',resolution:'',preset:'',scene:'',os:'',game_version:'',driver:'',rt:null,frame_generation:null,upscaling:null,publication_consent:false}
const fields=[['game','Игра'],['cpu','Процессор'],['gpu','Видеокарта'],['resolution','Разрешение'],['preset','Графический пресет'],['scene','Тестовая сцена / маршрут'],['os','Операционная система']]
export function BenchmarkUpload(){
 const input=useRef(null),revision=useRef(0)
 const [file,setFile]=useState(null),[preview,setPreview]=useState(null),[meta,setMeta]=useState(empty),[editing,setEditing]=useState([])
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[mine,setMine]=useState(null),[templateOpen,setTemplateOpen]=useState(false)
 async function load(selected){
  if(!selected||busy)return
  const version=++revision.current;setPreview(null);setFile(null);setError('');setMessage('');setEditing([])
  if(!/\.(csv|json)$/i.test(selected.name)||selected.size>4*1024*1024){setError('Нужен CSV/JSON до 4 МиБ. Экспортируйте один прогон.');return}
  setBusy(true)
  try{const capture={filename:selected.name,content:await selected.text()};const data=await request('/api/benchmarks/capture/preview',{method:'POST',body:capture});if(version===revision.current){setFile(capture);setPreview(data);setMeta({...empty,...data.metadata,publication_consent:false})}}
  catch(e){setError(e.message)}finally{setBusy(false);if(input.current)input.current.value=''}
 }
 async function send(event){
  event.preventDefault();if(busy||!file||!preview||preview.duplicate)return
  setBusy(true);setError('')
  try{const data=await request('/api/benchmarks/capture/submit',{method:'POST',body:{...file,metadata:meta}});setMessage(data.message);setPreview(null);setFile(null);setMeta(empty);setMine(null)}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function my(){try{setMine(await request('/api/benchmarks/submissions/mine'));setError('')}catch(e){setError(e.message)}}
 return <section className="panel capture-upload" aria-labelledby="capture-upload-title">
  <div className="capture-upload-heading"><div><h2 id="capture-upload-title">Файл игрового теста</h2><p>Поддерживаются CapFrameX JSON и PresentMon CSV. Для распознавания и отправки нужен вход в аккаунт.</p></div><div className="capture-upload-actions"><button type="button" className="secondary-btn" onClick={()=>setTemplateOpen(value=>!value)} aria-expanded={templateOpen}>Шаблон файла</button><button type="button" className="secondary-btn" onClick={my}>Мои отправки</button></div></div>
  {templateOpen&&<section className="capture-template" aria-label="Шаблон файла игрового замера"><h3>Формат файла</h3><p>Экспортируйте один прогон из CapFrameX в JSON или из PresentMon в CSV. Файл должен содержать времена отдельных кадров, а не только средний FPS.</p><pre><code>{"MsBetweenPresents\n<интервал реального кадра в миллисекундах>\n..."}</code></pre><p>Для CSV нужна колонка MsBetweenPresents и минимум 100 кадров. В примере показана структура, его нельзя отправить. Недостающие характеристики и настройки можно указать после загрузки.</p></section>}
  <div className="capture-drop" aria-busy={busy} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(e.dataTransfer.files.length!==1){setError('Выберите один файл захвата.');return}load(e.dataTransfer.files[0])}}>
   <strong>{busy?'Обрабатываем захват…':'Перетащите один CSV/JSON сюда'}</strong><span>До 4 МиБ · до 100 000 кадров · один прогон/процесс</span><button type="button" className="primary-btn" disabled={busy} onClick={()=>input.current?.click()}>{preview?'Выбрать другой файл':'Выбрать файл'}</button><input ref={input} type="file" accept=".csv,.json" hidden onChange={e=>load(e.target.files?.[0])}/>
  </div>
  {preview&&<form onSubmit={send} className="capture-preview"><h3>Предпросмотр · {preview.source}</h3>
   <dl className="capture-metrics"><div><dt>Средний FPS</dt><dd>{preview.average_fps}</dd></div><div><dt>1% Low</dt><dd>{preview.one_percent_low}</dd></div><div><dt>Длительность</dt><dd>{preview.duration_seconds} с · {preview.frames} кадров</dd></div></dl>
   <p className="field-hint">Метрика: {preview.metric}, мс. 1% Low = 1000 / среднее время худшего 1% кадров. Это может отличаться от P1 в других программах.</p>
   {preview.warnings.length>0&&<div className="capture-warnings"><strong>Нужно проверить</strong><ul>{preview.warnings.map(w=><li key={w}>{w}</li>)}</ul></div>}
   {preview.duplicate&&<p className="error" role="alert">Такой захват уже отправлен. Повторное добавление заблокировано.</p>}
   <div className="capture-metadata">{fields.map(([key,label])=>preview.metadata[key]&&!editing.includes(key)?<div key={key}><span>{label}</span><strong>{meta[key]}</strong><button type="button" className="text-btn" onClick={()=>setEditing([...editing,key])}>Уточнить</button></div>:<label key={key}>{label}{key==='resolution'?<select required value={meta[key]} onChange={e=>setMeta({...meta,[key]:e.target.value})}><option value="">Укажите разрешение</option>{['1280x720','1920x1080','2560x1440','3840x2160','other'].map(v=><option key={v} value={v}>{v==='other'?'Другое':v}</option>)}</select>:<input required minLength={2} maxLength={key==='scene'?160:key==='preset'||key==='os'?60:100} value={meta[key]} onChange={e=>setMeta({...meta,[key]:e.target.value})}/>}</label>)}</div>
   <details><summary>RT, апскейлинг, генерация кадров и версии</summary><div className="capture-metadata">{[['rt','Ray Tracing'],['frame_generation','Frame Generation']].map(([key,label])=><label key={key}>{label}<select value={meta[key]===null?'':String(meta[key])} onChange={e=>setMeta({...meta,[key]:e.target.value===''?null:e.target.value==='true'})}><option value="">Не указано</option><option value="false">Выключено</option><option value="true">Включено</option></select></label>)}<label>Апскейлинг<input maxLength={60} placeholder="Если известен: off, DLSS Quality…" value={meta.upscaling||''} onChange={e=>setMeta({...meta,upscaling:e.target.value||null})}/></label><label>Версия игры<input maxLength={40} value={meta.game_version||''} onChange={e=>setMeta({...meta,game_version:e.target.value})}/></label><label>Драйвер<input maxLength={80} value={meta.driver||''} onChange={e=>setMeta({...meta,driver:e.target.value})}/></label></div></details>
   <p>CSV/JSON можно подделать. Анализ файла выявляет отдельные аномалии, но не доказывает подлинность.</p>
   <label className="capture-consent"><input required type="checkbox" checked={meta.publication_consent} onChange={e=>setMeta({...meta,publication_consent:e.target.checked})}/>Я провёл тест, имею право отправить данные и разрешаю публикацию после проверки.</label>
   <button type="submit" className="primary-btn" disabled={busy||preview.duplicate||!meta.publication_consent}>{busy?'Отправляем…':'Отправить на модерацию'}</button>
  </form>}
  {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  {mine&&<ul>{mine.items.map(item=><li key={item.id}>#{item.id} · {item.result.game} · {item.status==='pending'?'На проверке':item.status==='approved'?'Проверен':'Отклонён'}</li>)}</ul>}
 </section>
}
