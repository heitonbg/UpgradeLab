import { fpsText } from '../../lib/performance'
import { BuildResult } from '../calculator/BuildSection'
import { CalculatorResult } from '../calculator/CalculatorResult'

export function AccountBuilds({ builds, cpus, gpus, onFind, onRemove }) {
  return <section className="panel"><h2>Сохранённые сборки и расчёты</h2>
    {builds.length ? builds.map(build=>{
      const assembly=build.config.scenario==='build'
      const result={...build.result, config:build.config,
        cpuName:cpus.find(c=>c.id===build.config.cpu_id)?.name||'CPU',
        gpuName:gpus.find(g=>g.id===build.config.gpu_id)?.name||'GPU'}
      return <details className="saved-account-build" key={build.id}>
        <summary>{assembly?'Сборка с нуля':'Апгрейд'} · {build.config.game} · {assembly?fpsText(result.fps,result.fps_outlook):`~${result.current_fps} → ~${result.upgraded_fps}`} FPS</summary>
        <p className="field-hint">Сохранено {new Date(build.created_at).toLocaleString('ru-RU')} · {build.config.mode}</p>
        {assembly?<BuildResult result={result} onFind={onFind}/>:<CalculatorResult result={result} onFind={onFind}/>}
        <button className="secondary-btn" onClick={()=>onRemove(build.id)}>Удалить сохранённый результат</button>
      </details>
    }):<p className="empty-copy">Нажмите «Сохранить» в результате расчёта. Сборка будет доступна в вашем аккаунте после входа с любого устройства.</p>}
  </section>
}
