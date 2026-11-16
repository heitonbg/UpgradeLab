export function AdaptiveFpsDetails({ result }) {
  if (!result) return null
  const current = result.after || result.current || result
  const sources = [...new Map((current.sources || []).map(source => [source.url || source.title, source])).values()]
  return <details className="fps-evidence"><summary>Данные расчёта</summary>
    <p className="field-hint">Расчётный FPS зависит от сцены и настроек игры.</p>
    {current.settings && <p>{current.settings.resolution} · {current.settings.preset}</p>}
    {current.requirements_enrichment?.source_type === 'steam_developer_requirements' && current.requirements_enrichment.source_url && <p><a href={current.requirements_enrichment.source_url} target="_blank" rel="noopener noreferrer">Системные требования · Steam</a></p>}
    {sources.map((source,index)=><p key={source.url || index}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.publisher || source.title || 'Источник'}</a>{source.license && ` · ${source.license}`}</p>)}
  </details>
}

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

export function FpsV2Evidence({ evidence }) {
  if (!evidence) return null
  const measured = evidence.status === 'measured_reference'
  const interpolated = evidence.status === 'estimated_interpolation'
  return <details className="fps-evidence fps-v2-evidence">
    <summary>FPS Engine v2 · {measured ? 'есть измерение этой пары' : interpolated ? 'интерполяция по измерениям' : 'проверка покрытия данными'}</summary>
    {measured || interpolated
      ? <>
        <p><strong>{evidence.average_fps} FPS</strong>{evidence.one_percent_low != null && ` · 1% Low: ${evidence.one_percent_low} FPS`}</p>
        <p>{measured ? 'Показано опубликованное измерение CPU/GPU при указанных условиях; это не повторный замер вашего ПК.' : 'Средний FPS оценён по времени кадра между двумя разрешениями этой же связки CPU/GPU. Это интерполяция, не замер.'}</p>
        <p>Данные: {evidence.sample_count} записей · {evidence.independent_series} тестовая серия · достоверность {evidence.confidence === 'limited' ? 'ограниченная' : 'по нескольким независимым источникам'}.</p>
        {evidence.interpolation?.anchors?.length > 0 && <p>Опоры: {evidence.interpolation.anchors.map(anchor => `${anchor.resolution}: ${anchor.average_fps} FPS`).join('; ')}.</p>}
        {evidence.sources?.map((source, index) => <p key={`${source.url}-${index}`}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.publisher}</a> · {source.license}{source.observed_date && ` · ${source.observed_date}`}</p>)}
      </>
      : <p>{evidence.reason || 'Пока нет достаточно близких лицензированных измерений для этой связки. Для полного FPS остаётся действующая оценочная модель.'}</p>}
    <p>V2 сейчас не оценивает независимые CPU/GPU-кривые и не определяет bottleneck по одной парной точке. Для таких выводов нужны разные процессоры и видеокарты в сопоставимых тестовых сериях.</p>
  </details>
}

export function FpsV3Evidence({ evidence }) {
  if (!evidence) return null
  const current = evidence.current
  const after = evidence.after
  return <details className="fps-evidence fps-v3-evidence">
    <summary>FPS Engine v3 · {evidence.method === 'legacy_anchored' ? 'оценка на основе прежней модели' : 'экспериментальный прогноз'}</summary>
    {current?.average_fps != null && <p>Текущая система: <strong>{current.average_fps} FPS</strong> · ограничение {current.bottleneck || 'не определено'}.</p>}
    {after?.average_fps != null && <p>После апгрейда: <strong>{after.average_fps} FPS</strong>{evidence.gain_percent != null && ` · ${evidence.gain_percent > 0 ? '+' : ''}${evidence.gain_percent}%`}{evidence.gain_fps_per_ruble != null && ` · ${evidence.gain_fps_per_ruble} FPS/₽`}.</p>}
    <p>{evidence.note}</p>
    {current?.explanation && <p>{current.explanation}</p>}
  </details>
}


export function FpsV4Evidence({ evidence }) {
  if (!evidence) return null
  const current = evidence.current || evidence
  const after = evidence.after
  const settings = current.settings || {}
  const sourceContext = [
    settings.game_version && `версия игры ${settings.game_version}`,
    settings.resolution,
    settings.preset,
    settings.rt === true ? 'RT включена' : settings.rt === false ? 'без RT' : null,
    settings.upscaling && settings.upscaling !== 'off' ? `апскейлинг ${settings.upscaling}` : null,
    settings.ram_type && `${settings.ram_type}${settings.ram_gb ? `, ${settings.ram_gb} ГБ` : ''}${settings.ram_channels ? `, ${settings.ram_channels}-канальный режим` : ''}`
  ].filter(Boolean).join(' · ')
  const labels = {measured_pair: 'измерение этой связки', same_pair_interpolation: 'интерполяция по измерениям связки', legacy_profile: 'профиль прежней модели', external_model_estimate: 'внешняя оценка видеокарты', external_fpshq_gpu_only: 'GPU-данные FPSHQ', external_model_settings_fallback: 'GPU-опора в условиях источника', external_model_nearest_anchor_fallback: 'ближайшая GPU-опора игры', catalog_gpu_reference_only: 'широкий GPU-ориентир каталога', insufficient_data: 'данных недостаточно'}
  const adequacyLabels = {
    below_minimum_reference_range: 'ниже минимальных требований',
    within_minimum_reference_spread: 'в диапазоне минимальных требований',
    between_minimum_and_recommended_ranges: 'между минимальными и рекомендованными требованиями',
    within_recommended_reference_spread: 'в диапазоне рекомендованных требований',
    at_or_above_recommended_reference_range: 'не ниже рекомендованных требований',
    below_recommended_reference_range: 'ниже рекомендованных требований',
    at_or_above_minimum_reference_range: 'не ниже минимальных требований',
    unresolved_requirements: 'недостаточно данных для сравнения'
  }
  const externalGpuEstimate = ['external_model_anchored','external_fpshq_gpu_only','external_model_settings_fallback','external_model_nearest_anchor_fallback','catalog_gpu_reference_only'].includes(current.status)
  const cpuAdequacy = current.cpu_adequacy
  const requirementLine = (title, comparison) => comparison && <p key={title}>
    {title}: индекс {comparison.index_vs_reference_percent}% от медианного PassMark CPU Mark требований
    {comparison.range_vs_reference_percent?.length === 2 && ` · диапазон ${comparison.range_vs_reference_percent[0]}–${comparison.range_vs_reference_percent[1]}%`}
    {comparison.reference_model_count > 8 && ` · моделей в группе: ${comparison.reference_model_count}`}
  </p>
  return <details className="fps-evidence fps-v4-evidence">
    <summary>FPS Engine v4 · {labels[current.confidence_level] || current.confidence_level || 'проверка данных'}</summary>
    {current.average_fps != null && <p>Центральная оценка системы: <strong>{current.average_fps} FPS</strong>{current.one_percent_low != null && ` · 1% Low: ${current.one_percent_low} FPS`}</p>}
    {current.gpu_oriented_fps != null && <p>{current.result_label || 'Ориентир видеокарты'}: <strong>~{current.gpu_oriented_fps} FPS</strong>{current.source_settings?.resolution && ` · ${current.source_settings.resolution} ${current.source_settings.preset || ''}`}. Это не FPS полной системы; CPU и сцена могут изменить результат.</p>}
    {current.gpu_reference_alternative?.gpu_oriented_fps != null && <p>Дополнительная опора {current.gpu_reference_alternative.source_name || 'GPU'}: около {current.gpu_reference_alternative.gpu_oriented_fps} FPS{current.gpu_reference_alternative.source_settings?.resolution && ` · ${current.gpu_reference_alternative.source_settings.resolution} ${current.gpu_reference_alternative.source_settings.preset || ''}`}. Сверяйте настройки: GPU-only опора не заменяет прогноз всей системы.</p>}
    {after?.average_fps != null && <p>После апгрейда: <strong>{after.average_fps} FPS</strong>{evidence.gain_fps != null && ` · ${evidence.gain_fps > 0 ? '+' : ''}${evidence.gain_fps} FPS`}.</p>}
    {after?.gpu_oriented_fps != null && <p>GPU-only оценка после апгрейда: ~{after.gpu_oriented_fps} FPS{evidence.gpu_oriented_gain_fps != null && ` · ${evidence.gpu_oriented_gain_fps > 0 ? '+' : ''}${evidence.gpu_oriented_gain_fps} FPS к оценке видеокарты`}.</p>}
    {evidence.cpu_adequacy_change && <p>Индекс CPU относительно требований: {evidence.cpu_adequacy_change.before_index}% → {evidence.cpu_adequacy_change.after_index}% ({evidence.cpu_adequacy_change.change_points > 0 ? '+' : ''}{evidence.cpu_adequacy_change.change_points} п.); это не прирост FPS.</p>}
    {cpuAdequacy && <div className="fps-adequacy">
      <p><strong>Процессор и системные требования</strong></p>
      {cpuAdequacy.available ? <>
        <p>{cpuAdequacy.cpu_name}: PassMark CPU Mark {cpuAdequacy.current_cpu_mark?.toLocaleString('ru-RU')} · {adequacyLabels[cpuAdequacy.status] || 'сопоставление по требованиям'}.</p>
        {requirementLine('Минимальные требования', cpuAdequacy.minimum)}
        {requirementLine('Рекомендуемые требования', cpuAdequacy.recommended)}
      </> : <p>Требование CPU не удалось сопоставить с конкретной моделью: {cpuAdequacy.minimum_requirement || cpuAdequacy.recommended_requirement || 'источник его не указал'}.</p>}
      <p>{cpuAdequacy.note}</p>
      {cpuAdequacy.requirement_source?.url && <p><a href={cpuAdequacy.requirement_source.url} target="_blank" rel="noopener noreferrer">Источник требований CPU · {cpuAdequacy.requirement_source.license}</a></p>}
    </div>}
    <p>{current.note || evidence.note}</p>
    {sourceContext && <p>{externalGpuEstimate ? 'Условия внешней модели' : 'Условия опубликованного теста'}: {sourceContext}{!externalGpuEstimate && '. Память показана как контекст источника и не используется как коэффициент FPS.'}</p>}
    {current.missing_data?.length > 0 && <p>Не хватает: {current.missing_data.join('; ')}.</p>}
    {current.source_evidence?.map((source, index) => <p key={`${source.url}-${index}`}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.publisher || source.title || source.attribution || (source.data_type === 'external_model_estimate' ? 'Источник внешней оценки' : 'Источник измерений')}</a>{source.license && ` · ${source.license}`}{source.observed_date && ` · ${source.observed_date}`}</p>)}
    <p>RAM не используется как коэффициент FPS. PassMark показывается отдельно как относительный рейтинг CPU или GPU, не как FPS.</p>
  </details>
}
