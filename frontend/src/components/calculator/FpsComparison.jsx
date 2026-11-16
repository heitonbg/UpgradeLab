import { gainPresentation } from '../../lib/upgradeResult'
const number=value=>Number(value.toFixed(1)).toLocaleString('ru-RU')
const signed=value=>(value>0?'+':'')+number(value)
export function FpsComparison({result}) {
 const data=gainPresentation(result)
 const comparison=result.fps_result||{}
 const after=comparison.after||{}
 const targetSource=after.result_type==='measured_system_fps'?'в опубликованном тесте':
  after.result_type==='estimated_system_fps'?'по расчётному прогнозу':'по доступным данным'
 return <figure className="fps-chart">
  <figcaption>FPS до и после апгрейда</figcaption>
  {data.delta!==null&&<div className="fps-chart-change" data-direction={data.delta>0?'up':data.delta<0?'down':'same'}>
   <div><span>{data.title}</span><strong>{signed(data.delta)} FPS{data.percent!==null&&<small> ({signed(data.percent)}%)</small>}</strong></div>
   <p>{number(result.current_fps)} → {number(result.upgraded_fps)} FPS. {data.note}</p>
  </div>}
  {data.points.map(([label,value],index)=><div className={'fps-chart-row '+(index===1?'fps-chart-upgraded':'')} key={label}><span>{label}</span><meter min="0" max={data.max} value={value} aria-label={`${label}: ${value} FPS`}/><strong>{value} FPS</strong></div>)}
  <div className="fps-chart-axis"><span>0 FPS</span><span>{data.max} FPS</span></div>
  {data.target!==null&&<p>Цель: {data.target} FPS{typeof result.upgraded_fps==='number'&&Number.isFinite(result.upgraded_fps)?result.upgraded_fps<data.target?` · не хватает ${number(data.target-result.upgraded_fps)} FPS`:` · достигнута ${targetSource}`:''}. Значения относятся к источникам и условиям, указанным в подробностях.</p>}
 </figure>
}
