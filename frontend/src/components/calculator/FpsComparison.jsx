import { fpsChartData } from '../../lib/fpsChart'
export function FpsComparison({result}) {
 const data=fpsChartData(result.current_fps,result.upgraded_fps,result.target_fps)
 return <figure className="fps-chart"><figcaption>Производительность · центральный прогноз FPS</figcaption>{data.points.map(([label,value])=><div className="fps-chart-row" key={label}><span>{label}</span><meter min="0" max={data.max} value={value} aria-label={`${label}: ${value} FPS`}/><strong>{value} FPS</strong></div>)}<div className="fps-chart-axis"><span>0 FPS</span><span>{data.max} FPS</span></div>{data.target!==null&&<p>Цель: {data.target} FPS. Это расчётная оценка, а не измерение в игре.</p>}</figure>
}
