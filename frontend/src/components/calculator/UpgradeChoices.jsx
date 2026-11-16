import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { upgradeTargetText } from '../../lib/performance'
import { AdaptiveFpsDetails } from './FpsEvidence'

export function PriceEvidence({ quote, hideLink = false }) {
  if (!quote?.avg_price) return <small>Цена пока не найдена.</small>
  const count = quote.sample_count || 1
  const label = quote.price_origin === 'passmark_reference' ? 'Справочный ориентир PassMark · зарубежная розница, пересчёт в рубли'
    : quote.price_origin === 'seller_declared' ? 'Цена заявлена продавцом UpgradeLab'
    : quote.price_origin === 'catalog_import' ? 'Цена по прайс-листу; магазинной сверки нет'
    : quote.average_method === 'one_offer' ? 'Цена одного объявления Avito'
    : quote.average_method === 'mean' ? `Средняя по ${count} объявлениям Avito`
    : quote.average_method === 'limited' ? `Только ${count} объявл. Avito — данных для надёжной средней мало`
    : quote.price_source?.includes('Avito') && quote.price_origin === 'snapshot' ? `Архив Avito · медиана по ${count} объявл.`
    : `${quote.price_source || 'Источник'}${quote.offer_id ? ' · одно предложение' : ''}`
  return <small>{label}{quote.price_date && ` · ${new Date(quote.price_date).toLocaleDateString('ru-RU')}`}<br/>
    {!hideLink && quote.price_url && <a href={quote.price_url} target="_blank" rel="noopener noreferrer">Открыть источник{quote.average_method === 'mean' ? ' (пример объявления)' : ''}</a>}
    {quote.reference_warning && <><br/><span>{quote.reference_warning}</span></>}
    {['market_average','limited_sample','single_listing'].includes(quote.price_origin) ? ' · цены и наличие сейчас не подтверждены' : ''}
    {quote.geography?.delivery_cost_unknown && ' · стоимость доставки неизвестна, итог покупки не подтверждён'}
    {quote.price_origin === 'seller_declared' && ' · наличие заявлено продавцом, независимой проверки нет'}
    {quote.price_market === 'retail_us_converted' && ' · зарубежная розница, без доставки и пошлин'}
  </small>
}

export function UpgradeChoices({ open, choices, targetFps, currentFps, onSelect, onClose, resaleNotice, onResolveResale }) {
  const sameCpuFps = choices.length > 1 && choices.every(choice=>choice.component==='CPU') && new Set(choices.map(choice=>choice.fps)).size === 1
  return <Modal open={open} onClose={onClose} title="Варианты апгрейда" size="wide">
    {resaleNotice&&<div className="result-note" role="status"><p>{resaleNotice}</p><div className="result-actions">{onResolveResale&&<Button variant="secondary" onClick={onResolveResale}>Указать ожидаемую цену продажи</Button>}</div></div>}
    <p className="choice-intro">Сравните FPS и доступные цены. Для смены платформы учитывается стоимость всего комплекта.</p>
    {sameCpuFps&&<p className="field-hint" role="note">Для этих процессоров доступная модель не различает результат в выбранной игре. Это не означает одинаковую производительность; сравните опубликованные тесты.</p>}
    <div className="upgrade-choice-grid">{choices.map((choice, index) => {
      const fpsResult = choice.fps_result?.after || choice.fps_result
      const fpsValue = fpsResult?.average_fps
      const gain = choice.fps_result?.gain_fps
      const measured = fpsResult?.result_type === 'measured_system_fps'
      return <article className="upgrade-choice-card" key={choice.key || choice.id || choice.name}>
      <div className="choice-card-top"><span className="choice-number">0{index + 1}</span><span className="choice-tag">{index === 0 ? 'Рекомендуем' : 'Альтернатива'}</span></div>
      <p className="eyebrow">{choice.kind === 'platform' ? 'Смена платформы · 4 детали' : choice.component === 'CPU' ? 'Процессор' : 'Видеокарта'}</p>
      <h4>{choice.name}</h4>
      <div className="upgrade-choice-price">{(choice.upgrade_price?.avg_price || choice.avg_price || choice.price) > 0 ? <><strong>{Number(choice.upgrade_price?.avg_price || choice.avg_price || choice.price).toLocaleString('ru-RU')} ₽</strong>{choice.kind === 'platform' ? <small>Сумма CPU, платы, памяти и кулера. Продажа старых деталей учитывается отдельно.</small> : <PriceEvidence quote={choice.upgrade_price || choice.price_quote || {avg_price:choice.avg_price || choice.price,price_source:'Предварительная оценка'}} hideLink/>}</> : <small>Цена неизвестна — стоимость и соответствие бюджету не подтверждены.</small>}</div>
      {choice.kind === 'platform' && <ul className="upgrade-package-parts">{choice.parts.map(part=><li key={part.type}><span>{part.type === 'CPU' ? 'Процессор' : part.type === 'motherboard' ? 'Материнская плата' : part.type === 'memory' ? 'Оперативная память' : 'Кулер'}</span><strong>{part.name}</strong></li>)}</ul>}
      {fpsValue != null ? <p className="upgrade-choice-fps">{measured ? '' : '~'}{Math.round(fpsValue)} <small>FPS</small></p> : <p className="field-hint">Оценка FPS полной системы для этого варианта недоступна.</p>}
      {fpsValue != null && <p className="field-hint">{upgradeTargetText(fpsValue, targetFps)}</p>}
      {gain != null && <p className="upgrade-gain">{gain > 0 ? '+' : ''}{Math.round(gain)} FPS {choice.fps_result?.gain_type === 'measured_comparison' ? 'по опубликованным тестам' : 'по расчётной модели'}</p>}
      {choice.upgrade_price?.is_purchase_quote && /^https?:\/\//i.test(choice.upgrade_price?.price_url || '') && <a className="secondary-btn" href={choice.upgrade_price.price_url} target="_blank" rel="noopener noreferrer">Открыть предложение ↗</a>}
      <AdaptiveFpsDetails result={choice.fps_result}/>
      {choice.budget_shortfall>0&&<p className="field-hint">Не хватает {Number(choice.budget_shortfall).toLocaleString('ru-RU')} ₽ с учётом указанной продажи.</p>}
      {choice.kind === 'platform' && <p className="field-hint">Комплект платформы включает CPU, плату, RAM и кулер; видеокарта остаётся. Совместимость деталей проверьте перед покупкой.</p>}
      <Button type="button" disabled={choice.selection_block_reason === 'resale_price_unavailable'} variant="secondary" onClick={() => onSelect(choice)}>{choice.selection_block_reason === 'resale_price_unavailable' ? 'Укажите цену продажи' : 'Выбрать вариант'}</Button>
    </article>})}</div>
  </Modal>
}
