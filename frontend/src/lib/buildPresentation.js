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
 return {kind:'gaming',label:'FPS',value:fpsText(choice.fps,choice.fps_outlook),note:'Расчётная оценка игрового FPS.'}
}
