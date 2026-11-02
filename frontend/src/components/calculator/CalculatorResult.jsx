import { upgradeTargetText } from '../../lib/performance'
import { FpsEvidence } from './FpsEvidence'
import { StoreOffers } from '../StoreOffers'
import { Button } from '../ui/Button'
import { PriceEvidence } from './UpgradeChoices'

export function CalculatorResult({ result, onFind, onSave, onCompare, onResolveResale }) {
  if (!result) return null
  const oldName = result.bottleneck === 'CPU' ? result.cpuName : result.gpuName
  const unavailable = result.price_search_status?.some(source => ['unavailable', 'timeout'].includes(source.status))
  return <section className="panel upgrade-result">
    <h2>{result.upgrade_kind === 'platform' ? 'Апгрейд со сменой платформы' : result.is_maxed_out ? 'Доступный апгрейд не найден' : 'Рекомендация по апгрейду'}</h2>
    <div className="fps-comparison">
      <div>Сейчас<strong>~{result.current_fps} FPS</strong><small>Центральный прогноз</small></div><span>→</span>
      <div>{result.upgrade_component ? 'После замены' : 'Без замены'}<strong>~{result.upgraded_fps} FPS</strong><small>Центральный прогноз</small></div>
      <div>Прирост<strong>+{result.upgraded_fps - result.current_fps} FPS</strong><small>По расчётной модели</small></div>
    </div>
    <p className="field-hint">Цель: {result.target_fps} FPS · {upgradeTargetText(result.upgraded_fps, result.target_fps)}</p>
    <FpsEvidence outlook={result.upgraded_fps_outlook}/>
    <p className="result-note">{result.recommendation}</p>
    {result.upgrade_component && <div className="result-price"><strong>{result.upgrade_name}</strong>
      <strong className="upgrade-price-value">{result.avg_price ? `${result.avg_price.toLocaleString('ru-RU')} ₽` : 'Цена неизвестна'}</strong>
      {result.within_budget && <small>Укладывается в бюджет по оценке цены.</small>}
      {result.mode === 'budget_plus_sell' && result.net_upgrade_cost != null && <small>После предполагаемой продажи доплатить: {result.net_upgrade_cost.toLocaleString('ru-RU')} ₽.</small>}
      <PriceEvidence quote={result.upgrade_price}/>
    </div>}
    {result.upgrade_parts?.length > 0 && <ul className="upgrade-package-parts result-package-parts">{result.upgrade_parts.map(part=><li key={part.type}><span>{part.name}</span><strong>{part.price.toLocaleString('ru-RU')} ₽</strong>{part.price_url&&<a href={part.price_url} target="_blank" rel="noopener noreferrer">{part.price_source}</a>}</li>)}</ul>}
    {result.platform_upgrade_note && <p className="result-note">{result.platform_upgrade_note}</p>}
    {unavailable && <p className="field-hint">Avito не удалось обновить во время расчёта. Использованы доступные сохранённые наблюдения; если их нет, цена не показывается.</p>}
    {result.mode === 'budget_plus_sell' && result.resale_status === 'unavailable' && <div className="result-note upgrade-budget" role="status"><p>{result.resale_notice}</p>{onResolveResale&&<Button variant="secondary" onClick={onResolveResale}>Указать ожидаемую цену продажи</Button>}</div>}
    {result.mode === 'budget_plus_sell' && result.resale_status !== 'unavailable' && <div className="result-note upgrade-budget"><p>Деньги на апгрейд: {(result.cash_budget ?? result.config?.budget ?? 0).toLocaleString('ru-RU')} ₽ + продажа старой детали: {result.current_component_price.toLocaleString('ru-RU')} ₽ = <strong>{result.total_budget.toLocaleString('ru-RU')} ₽</strong>.</p>{result.current_component_price > 0 ? <><p>Продажа — ожидаемая выручка; сумма станет доступна после сделки.</p><PriceEvidence quote={result.resale_price}/></> : <p>{result.resale_price?.price_origin === 'manual' ? 'Вы указали нулевую выручку от продажи.' : 'Оценки продажи нет. Укажите ожидаемую цену в форме, чтобы учесть её в бюджете.'}</p>}</div>}
    {result.ai_warning && <p className="result-note"><strong>Нейросети. </strong>{result.ai_warning}</p>}
    <ul className="field-hint">{result.compatibility_notes?.map(note => <li key={note}>{note}</li>)}</ul>
    <p className="field-hint">Подбор и достижение цели рассчитаны по центральному прогнозу FPS. Это оценка: результат зависит от версии игры, сцены, драйверов и памяти.</p>
    <details><summary>Сравнить предложения на площадках</summary><StoreOffers key={result.upgrade_name || oldName} initialQuery={result.upgrade_name || oldName || ''} category={result.bottleneck} hardwareId={result.upgrade_id}/><p className="field-hint">После обновления предложений выполните расчёт снова, чтобы учесть новые цены.</p></details>
    <div className="result-actions">
      {onCompare && <Button onClick={onCompare} variant="secondary">Сравнить варианты</Button>}
      {onSave && <Button onClick={onSave}>Сохранить расчёт</Button>}
      {result.upgrade_name && <Button variant="secondary" onClick={() => onFind({search: result.upgrade_name})}>Найти на бирже</Button>}
      {result.upgrade_name && oldName && <Button variant="secondary" onClick={() => onFind({draft: {title: oldName, price: result.current_component_price ? String(result.current_component_price) : '', condition: 'Б/У'}})}>Выставить старый компонент</Button>}
    </div>
  </section>
}
