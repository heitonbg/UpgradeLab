import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { upgradeTargetText } from '../../lib/performance'

export function PriceEvidence({ quote }) {
  if (!quote?.avg_price) return <small>Цена пока не найдена.</small>
  const count = quote.sample_count || 1
  const label = quote.price_origin === 'seller_declared' ? 'Цена заявлена продавцом UpgradeLab'
    : quote.price_origin === 'catalog_import' ? 'Цена по прайс-листу; магазинной сверки нет'
    : quote.average_method === 'one_offer' ? 'Цена одного объявления Avito'
    : quote.average_method === 'mean' ? `Средняя по ${count} объявлениям Avito`
    : quote.average_method === 'limited' ? `Только ${count} объявл. Avito — данных для надёжной средней мало`
    : quote.price_source?.includes('Avito') && quote.price_origin === 'snapshot' ? `Архив Avito · медиана по ${count} объявл.`
    : `${quote.price_source || 'Источник'}${quote.offer_id ? ' · одно предложение' : ''}`
  return <small>{label}{quote.price_date && ` · ${new Date(quote.price_date).toLocaleDateString('ru-RU')}`}<br/>
    {quote.price_url && <a href={quote.price_url} target="_blank" rel="noopener noreferrer">Открыть источник{quote.average_method === 'mean' ? ' (пример объявления)' : ''}</a>}
    {['market_average','limited_sample','single_listing'].includes(quote.price_origin) ? ' · цены и наличие сейчас не подтверждены' : ''}
    {quote.geography?.delivery_cost_unknown && ' · стоимость доставки неизвестна, итог покупки не подтверждён'}
    {quote.price_origin === 'seller_declared' && ' · наличие заявлено продавцом, независимой проверки нет'}
    {quote.price_market === 'retail_us_converted' && ' · зарубежная розница, без доставки и пошлин'}
  </small>
}

export function UpgradeChoices({ open, choices, targetFps, currentFps, onSelect, onClose, resaleNotice, onResolveResale, onRetryResale, onLookupPrice }) {
  return <Modal open={open} onClose={onClose} title="Варианты апгрейда" size="wide">
    {resaleNotice&&<div className="result-note" role="status"><p>{resaleNotice}</p><div className="result-actions">{onRetryResale&&<Button variant="secondary" onClick={onRetryResale}>Повторить автоматический поиск</Button>}{onResolveResale&&<Button variant="secondary" onClick={onResolveResale}>Указать ожидаемую цену продажи</Button>}</div></div>}
    <p className="choice-intro">Сравните замену детали или платформы. В комплект платформы включены CPU, плата, RAM и кулер; видеокарта остаётся. Цены и FPS — ориентиры.</p>
    <div className="upgrade-choice-grid">{choices.map((choice, index) => <article className="upgrade-choice-card" key={choice.key || choice.id || choice.name}>
      <div className="choice-card-top"><span className="choice-number">0{index + 1}</span><span className="choice-tag">{!choice.price ? 'Проверить цену' : choice.selection_block_reason === 'resale_price_unavailable' ? 'Продажа не оценена' : choice.budget_shortfall > 0 ? 'Выше бюджета' : index === 0 ? 'Рекомендуем' : 'Альтернатива'}</span></div>
      <p className="eyebrow">{choice.kind === 'platform' ? 'Смена платформы · 4 детали' : choice.component === 'CPU' ? 'Процессор' : 'Видеокарта'}</p>
      <h4>{choice.name}</h4>
      {choice.kind === 'platform' && <ul className="upgrade-package-parts">{choice.parts.map(part=><li key={part.type}><span>{part.name}</span><strong>{part.price.toLocaleString('ru-RU')} ₽</strong>{part.price_url&&<a href={part.price_url} target="_blank" rel="noopener noreferrer">{part.price_source}</a>}</li>)}</ul>}
      <p className="upgrade-choice-fps">~{choice.fps} <small>FPS</small></p>
      <p className="field-hint">{upgradeTargetText(choice.fps, targetFps)}</p>
      <p className="upgrade-gain">+{choice.fps - currentFps} FPS по модели</p>
      <div className="upgrade-choice-price"><strong>{choice.price ? `${choice.price.toLocaleString('ru-RU')} ₽` : 'Цена неизвестна · бюджет не проверен'}</strong>{choice.price != null && choice.resale_value > 0 && <small>Продажа старой детали: −{choice.resale_value.toLocaleString('ru-RU')} ₽<br/>Доплатить: {choice.net_cost.toLocaleString('ru-RU')} ₽</small>}<PriceEvidence quote={choice.price_quote}/></div>
      {choice.kind === 'platform' && <p className="field-hint">Предварительная сумма по наблюдениям за 7 дней. Видеокарта остаётся; BIOS, корпус и питание нужно проверить.</p>}
      {choice.budget_shortfall > 0 && <p className="field-hint">С учётом продажи нужно добавить ещё {choice.budget_shortfall.toLocaleString('ru-RU')} ₽.</p>}
      {choice.selection_block_reason === 'resale_price_unavailable' && <p className="field-hint">Своих денег не хватает {choice.cash_shortfall.toLocaleString('ru-RU')} ₽. Доступность после продажи пока не определена — её цена не получена.</p>}
      <Button type="button" disabled={!choice.price ? !onLookupPrice : choice.selection_allowed === false && !(choice.selection_block_reason === 'resale_price_unavailable' && onResolveResale)} variant={index === 0 ? 'primary' : 'secondary'} onClick={() => !choice.price ? onLookupPrice?.(choice) : choice.selection_block_reason === 'resale_price_unavailable' ? onResolveResale?.() : onSelect(choice)}>{!choice.price ? 'Найти цену' : choice.selection_block_reason === 'resale_price_unavailable' ? 'Указать цену продажи' : choice.selection_allowed === false ? 'Нужно увеличить бюджет' : 'Выбрать вариант'}</Button>
    </article>)}</div>
  </Modal>
}
