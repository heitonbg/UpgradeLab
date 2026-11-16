import { useEffect, useState } from 'react'
import { request } from '../api/client'

const PAGE = 50
const sourceLabel = value => value === 'measured' ? 'Замер' : value === 'aggregate' ? 'Агрегат обзоров' : 'Модель FPSHQ'

export function FpshqReferenceTable() {
  const [game, setGame] = useState('')
  const [resolution, setResolution] = useState('')
  const [source, setSource] = useState('any')
  const [sort, setSort] = useState('game')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setLoading(true)
    const query = new URLSearchParams({game, resolution, source, sort, offset: String(offset), limit: String(PAGE)})
    request('/api/benchmarks/gpu-reference?' + query)
      .then(value => { if (active) { setData(value); setError('') } })
      .catch(() => { if (active) setError('Не удалось загрузить таблицу FPSHQ.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [game, resolution, source, sort, offset])
  function update(setter, value) { setter(value); setOffset(0) }
  return <section className="panel fpshq-reference" aria-labelledby="fpshq-table-title">
    <header><p className="eyebrow">Открытые игровые данные · FPSHQ · CC BY 4.0</p><h2 id="fpshq-table-title">GPU-бенчмарки по играм</h2>
      <p>50 игр и до 2 400 строк для видеокарт, разрешений и High. Измерения, агрегаты обзоров и модельные строки помечены отдельно. Это FPS видеокарты, а не тест выбранной связки CPU/GPU.</p></header>
    <form className="benchmark-filters" onSubmit={event => event.preventDefault()}>
      <label>Игра<input value={game} onChange={event => update(setGame, event.target.value)} placeholder="Например, Cyberpunk 2077" maxLength={100}/></label>
      <label>Разрешение<select value={resolution} onChange={event => update(setResolution, event.target.value)}><option value="">Любое</option><option value="1080p">1080p</option><option value="1440p">1440p</option><option value="4K">4K</option></select></label>
      <label>Происхождение<select value={source} onChange={event => update(setSource, event.target.value)}><option value="any">Все типы</option><option value="measured">Замеры</option><option value="aggregate">Агрегаты обзоров</option><option value="model">Модель FPSHQ</option></select></label>
      <label>Сортировка<select value={sort} onChange={event => update(setSort, event.target.value)}><option value="game">Игра: А–Я</option><option value="fps_desc">FPS: по убыванию</option><option value="fps_asc">FPS: по возрастанию</option></select></label>
    </form>
    {loading&&<p role="status">Загружаем строки бенчмарков…</p>}{error&&<p role="alert">{error}</p>}
    {data&&!loading&&<><p className="benchmark-table-caption">{data.total.toLocaleString('ru-RU')} строк · версия {data.version} · {sourceLabel(source==='any'?'model':source)}{source==='any'?' и другие типы':''}</p>
      {data.items.length===0?<p className="benchmark-empty">По фильтрам строк нет.</p>:<div className="benchmark-table-wrap"><table className="benchmark-data-table"><thead><tr><th>Игра</th><th>Видеокарта</th><th>Разрешение / пресет</th><th>Средний FPS</th><th>1% Low</th><th>Тип данных</th><th>Источник</th></tr></thead><tbody>{data.items.map((row,index)=><tr key={row.game+'|'+row.gpu+'|'+row.resolution+'|'+index}><th>{row.game}</th><td>{row.gpu}</td><td>{row.resolution} · {row.preset}</td><td className="benchmark-number">{row.average_fps}</td><td className="benchmark-number">{row.one_percent_low??'—'}</td><td>{sourceLabel(row.data_type)}</td><td><a href={row.url} target="_blank" rel="noreferrer">FPSHQ ↗</a></td></tr>)}</tbody></table></div>}
      <div className="result-actions"><button type="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-PAGE))}>Назад</button><span>{data.total?offset+1+'–'+Math.min(offset+PAGE,data.total)+' из '+data.total:'0 результатов'}</span><button type="button" disabled={offset+PAGE>=data.total} onClick={()=>setOffset(offset+PAGE)}>Дальше</button></div>
    </>}
    <small>Источник и лицензия: <a href="https://fpshq.com/en/data/fps-model-top50/" target="_blank" rel="noreferrer">FPSHQ open data</a> · CC BY 4.0.</small>
  </section>
}
