import { fpsChartData } from './fpsChart.js'

export function upgradePrice(result) {
 const quote=result.upgrade_price||{}
 const valid=value=>typeof value==='number'&&Number.isFinite(value)&&value>0
 const amount=valid(quote.avg_price)?quote.avg_price:valid(result.avg_price)?result.avg_price:null
 return {visible:Boolean(result.upgrade_name),amount,quote:{...quote,avg_price:amount}}
}

export function gainPresentation(result) {
 const data=fpsChartData(result.current_fps,result.upgraded_fps,result.target_fps)
 const type=result.fps_result?.gain_type
 return {...data,title:type?'Изменение после апгрейда':'Разница оценок',
  note:type==='measured_comparison'?'Сопоставление опубликованных тестов одной серии.':type?
   'Обе оценки рассчитаны одной моделью; это не измерение в игре.':
   'Разные методы оценки: процент приблизительный, реальный прирост может отличаться.'}
}
