export function FpsEvidence({ outlook }) {
  if (!outlook) return null
  const modelOnly = outlook.data_quality === 'model_only' || outlook.method === 'synthetic_estimate'
  const estimated = outlook.data_quality === 'estimated_from_tests'
  return <>
    {modelOnly && outlook.target_basis !== 'central_estimate' && <p className="fps-preview-warning">Для этой GPU и настроек мало игровых измерений. Ориентируйтесь на широкий диапазон.</p>}
    <details className="fps-evidence">
      <summary>{modelOnly ? 'Расчётная модель' : estimated ? 'Оценка по игровым тестам' : 'Есть игровые тесты GPU'} · как получен FPS</summary>
      {outlook.target_basis === 'central_estimate' && <p>Подбор выполняется по центральному прогнозу {outlook.central_estimate} FPS. Справочный диапазон неопределённости: {outlook.minimum}–{outlook.maximum} FPS; его границы не используются для достижения цели.</p>}
      <p>{outlook.note}</p><p>{outlook.settings}</p><p>{outlook.uncertainty}</p>
      {outlook.sources?.length > 0 && <ul>{outlook.sources.map((source,index) => <li key={`${source.url}-${source.settings||''}-${index}`}>
        <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a> · {source.fps} FPS на тестовой системе издания{source.settings&&` · ${source.settings}`}
      </li>)}</ul>}
      {outlook.context_sources?.length>0&&<ul>{outlook.context_sources.map(source=><li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a></li>)}</ul>}
      {outlook.comparison_tests?.length>0&&<><p>Другие тесты для сравнения; их настройки отличаются от выбранных:</p><ul>{outlook.comparison_tests.map(source=><li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a> · {source.fps} FPS · {source.settings}</li>)}</ul></>}
    </details>
  </>
}
