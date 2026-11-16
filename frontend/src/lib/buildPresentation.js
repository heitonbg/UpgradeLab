import { fpsText } from './performance.js'
// Presentation only. Never promotes unknown/reference prices to verified ones.
export function buildTrust(choice) {
 if(choice.parts?.some(part=>part.price_basis==='reference'||part.price_status==='reference'))return {kind:'reference',label:'Справочная конфигурация',note:'Ориентировочная стоимость. Текущие цена и наличие не подтверждены.'}
 if(choice.status==='complete'&&choice.purchase_ready===true&&choice.prices_confirmed===true)return {kind:'verified',label:'Цены сверены',note:'Проверьте наличие, доставку и условия покупки.'}
 return {kind:'draft',label:'Предварительный подбор',note:'Стоимость и совместимость требуют проверки перед покупкой.'}
}
export function distinctBuilds(choices) {
 const seen=new Set()
 return choices.filter(choice=>{const identity=JSON.stringify((choice.parts||[]).map(p=>[p.type,p.id,p.offer_id,p.name,p.price]).sort((a,b)=>a[0].localeCompare(b[0])));if(seen.has(identity))return false;seen.add(identity);return true}).slice(0,3)
}
export function variantHeading(choice) {
 if(choice.selection_policy==='target_fps'&&choice.title)return choice.title
 if(choice.variant_key==='recommended'&&choice.objective==='performance')return choice.workload==='cpu_work'?'Максимальная производительность CPU':'Максимальная игровая производительность'
 if(choice.variant_key==='recommended'&&choice.objective==='economy')return 'Экономичная'
 return {recommended:'Сбалансированная',performance:'Производительный вариант',value:'Цена и возможности',hybrid_comparison:'Справочная альтернатива'}[choice.variant_key]||choice.title||'Вариант сборки'
}
export function compatibilityLabel(choice) {
 if(choice.compatibility_status==='incompatible')return 'Есть несовместимость — состав требует изменения'
 if(choice.technical_compatibility_confirmed===true&&choice.compatibility_status==='compatible')return 'Совместимость по известным характеристикам проверена'
 return 'Совместимость требует проверки'
}
export function buildMetric(choice) {
 if(choice.workload==='cpu_work')return {kind:'cpu',label:'CPU Mark',value:Number.isFinite(choice.selection_score)?choice.selection_score.toLocaleString('ru-RU'):'Нет данных',note:'Аппаратный ориентир, не скорость конкретных приложений.'}
 const result=choice.fps_result||choice.fps_v4_evidence
 const evidence=result?.current||result
 const measured=evidence?.result_type==='measured_system_fps'||evidence?.measurement_type==='measured'
 if(Number.isFinite(evidence?.average_fps))return {kind:'system_fps',label:measured?'FPS по тесту':'Прогноз FPS',value:`${measured?'':'~'}${Math.round(evidence.average_fps)}`,note:measured?'Опубликованное измерение этой связки; это не повторный тест вашего ПК.':evidence?.confidence_label||'Расчётная оценка, не замер в игре.'}
 const scenario=evidence?.requirements_anchored_estimate
 if(scenario?.available&&Number.isFinite(scenario.scenario_fps)){const bounds=scenario.scenario_fps_sensitivity_range;return {kind:'experimental_scenario',label:'Экспериментальный сценарий FPS',value:`~${Math.round(scenario.scenario_fps)}${bounds?.length===2?` (${Math.round(bounds[0])}–${Math.round(bounds[1])})`:''}`,note:'Математический сценарий по требованиям игры и PassMark; не измерение и не подтверждённый прогноз.'}}
 if(Number.isFinite(evidence?.gpu_oriented_fps)){
  const details=evidence?.technical_details?.gpu_estimate_details||{}
  const range=evidence?.gpu_reference_range||details.fps_range
  const populationRange=evidence?.gpu_reference_range_type==='catalog_game_population_percentiles_not_prediction_interval'
  const broad=evidence?.technical_details?.status==='catalog_gpu_reference_only'
  const rangeNote=Array.isArray(range)&&range.length===2
   ? (populationRange?` Разброс центральных 80% игр в каталоге: ${Math.round(range[0])}–${Math.round(range[1])} FPS; это не интервал прогноза выбранной игры.`:` Диапазон источника: ${Math.round(range[0])}–${Math.round(range[1])} FPS.`)
   : ''
  return {kind:'gpu_oriented',label:broad?'Широкий GPU-ориентир по каталогу игр':evidence?.result_label||'Ориентир FPS видеокарты',value:`~${Math.round(evidence.gpu_oriented_fps)}`,note:(evidence?.confidence_label||'Это внешняя оценка видеокарты, не FPS полной системы.')+rangeNote}
 }
 if(evidence?.result_type==='unavailable'||evidence?.status==='insufficient_data')return {kind:'unavailable',label:'Оценка недоступна',value:'—',note:'Для этой конфигурации нет сопоставимого прогноза FPS всей системы.'}
 return {kind:'gaming',label:'FPS',value:fpsText(choice.fps,choice.fps_outlook),note:'Расчётная оценка игрового FPS.'}
}

export function buildTargetSummary(choice, target) {
 const result=choice.fps_result||choice.fps_v4_evidence
 const evidence=result?.current||result
 const fps=evidence?.average_fps
 if(Number.isFinite(fps)){
  const measured=evidence.result_type==='measured_system_fps'||evidence.measurement_type==='measured'
  const meets=fps>=target
  if(measured)return `В опубликованном тесте: ${Math.round(fps)} FPS; ${meets?'уровень цели достигнут в условиях источника':'до цели не хватает '+Math.round(target-fps)+' FPS'}.`
  return `По расчётному прогнозу: около ${Math.round(fps)} FPS; ${meets?'цель достигнута по модели':'до цели не хватает '+Math.round(target-fps)+' FPS'}. Это не игровой замер.`
 }
 const scenario=evidence?.requirements_anchored_estimate
 if(scenario?.available)return 'Есть экспериментальный сценарий около '+Math.round(scenario.scenario_fps)+' FPS; цель не подтверждена измерениями.'
 if(evidence?.result_type==='gpu_reference_only'||evidence?.gpu_oriented_fps!=null)
  return 'Есть только ориентир видеокарты; целевой FPS всей системы не проверен.'
 return 'FPS всей системы для этой конфигурации не рассчитан; цель не подтверждена.'
}
