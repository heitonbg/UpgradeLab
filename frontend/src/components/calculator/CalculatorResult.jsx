import { saveAndShareBuild } from '../../lib/share'
import { useEffect, useState } from 'react'
import { FpsComparison } from './FpsComparison'
import { upgradeTargetText } from '../../lib/performance'
import { AdaptiveFpsDetails } from './FpsEvidence'
import { Button } from '../ui/Button'
import { upgradePrice } from '../../lib/upgradeResult'
import { PriceEvidence } from './UpgradeChoices'

export function CalculatorResult({ result, onFind, onSave, onCompare, onResolveResale, onSetResalePrice }) {
  if (!result) return null
  const price = upgradePrice(result)
  const oldName = result.bottleneck === 'CPU' ? result.cpuName : result.gpuName
  const unavailable = result.price_search_status?.some(source => ['unavailable', 'timeout'].includes(source.status))
  const [salePrice, setSalePrice] = useState('')
  const [platformSale, setPlatformSale] = useState('')
  const [shareNotice,setShareNotice]=useState(''),[sharing,setSharing]=useState(false)
  async function shareResult(){setSharing(true);try{const parts=[{category:'Процессор',name:result.cpuName||'CPU',price:null,url:'',image_url:''},{category:'Видеокарта',name:result.gpuName||'GPU',price:null,url:'',image_url:''},...(result.upgrade_name?[{category:'Выбранный апгрейд',name:result.upgrade_name,price:result.avg_price??null,url:result.upgrade_price?.price_url||'',image_url:''}]:[])];await saveAndShareBuild({v:1,parts,game:result.game||result.config?.game||null,fps:result.upgraded_fps??null,current_fps:result.current_fps??null});setShareNotice('Снимок расчёта сохранён. Ссылка скопирована.')}catch(error){setShareNotice(error.message)}finally{setSharing(false)}}
  useEffect(()=>{
    const value=result.config?.expected_sale_price ?? result.resale_price?.avg_price
    setSalePrice(value == null ? '' : String(value))
  },[result.bottleneck,result.config?.expected_sale_price,result.resale_price?.avg_price])
  function submitSalePrice(event) {
    event.preventDefault()
    if(salePrice===''||!Number.isSafeInteger(Number(salePrice))||Number(salePrice)<0)return
    onSetResalePrice?.(Number(salePrice))
  }
  if (result.current_fps == null && result.fps_result?.current?.average_fps == null) return <section className="panel upgrade-result">
    <h2>Не удалось получить результат</h2>
    <p className="result-note">{result.recommendation}</p>
    <AdaptiveFpsDetails result={result.fps_result||result.fps_v4_evidence}/>
  </section>
  return <section className="panel upgrade-result">
    <h2>{result.upgrade_kind === 'platform' ? 'Апгрейд со сменой платформы' : result.is_maxed_out ? 'Доступный апгрейд не найден' : 'Рекомендация по апгрейду'}</h2>
    {price.visible && <div className="upgrade-purchase-summary">
      <div><span className="field-hint">{result.upgrade_kind==='platform'?'Выбранная платформа':'Выбранный компонент'}</span><strong>{result.upgrade_name}</strong></div>
      <div className="upgrade-purchase-price"><strong>{price.amount!==null?price.amount.toLocaleString('ru-RU')+' ₽':'Цена пока не найдена'}</strong>{price.amount!==null&&<PriceEvidence quote={price.quote} hideLink/>}</div>
    </div>}
    <FpsComparison result={result}/>
    <p className="field-hint">Цель: {result.target_fps} FPS · {upgradeTargetText(result.upgraded_fps ?? result.current_fps, result.target_fps)}</p>

    <AdaptiveFpsDetails result={result.fps_result||result.fps_v4_evidence}/>
    <details className="result-explanation"><summary>Подробности расчёта</summary><p>{result.recommendation}</p></details>
    <details className="upgrade-resale-details"><summary>Продать старую платформу и перейти на новую</summary><form className="result-note resale-price-form" onSubmit={event=>{event.preventDefault();if(platformSale!==''&&Number.isSafeInteger(Number(platformSale))&&Number(platformSale)>=0)onSetResalePrice?.(Number(platformSale),true)}}>
      <p>Сравним совместимые комплекты CPU, платы, двух модулей памяти и кулера: Intel с DDR4 или AM5 с DDR5. Видеокарта сохраняется.</p>
      <div className="resale-price-controls"><label>Ожидаемая сумма за старые CPU + плату + RAM, ₽<input type="number" min="0" max="10000000" step="100" required value={platformSale} onChange={event=>setPlatformSale(event.target.value)} placeholder="Ваша оценка всего комплекта"/></label><Button type="submit">Сравнить смену платформы</Button></div>
      <small>Выручка учитывается только для смены платформы. Неограниченный бюджет остаётся неограниченным. Деньги доступны после продажи.</small>
      {result.platform_upgrade_note&&<p className="field-hint">{result.platform_upgrade_note}</p>}
    </form></details>
    {result.bottleneck != null && (result.mode !== 'budget_plus_sell' || result.resale_status === 'unavailable') && <details className="upgrade-resale-details"><summary>Продажа старой детали</summary><form className="result-note upgrade-budget resale-price-form" onSubmit={submitSalePrice}>
      <div><strong>{oldName}</strong></div>
      {result.resale_price?.price_origin === 'market_median' && <p className="field-hint">Ориентир UpgradeLab: медиана {result.resale_price.avg_price.toLocaleString('ru-RU')} ₽ по {result.resale_price.sample_count} активным объявлениям за 30 дней{result.resale_price.min_price_rub!=null&&result.resale_price.max_price_rub!=null?` (диапазон ${result.resale_price.min_price_rub.toLocaleString('ru-RU')}–${result.resale_price.max_price_rub.toLocaleString('ru-RU')} ₽)`:''}. Это цены продавцов, не завершённые сделки.</p>}
      <div className="resale-price-controls"><label>Ожидаемая выручка от продажи {result.bottleneck === 'CPU' ? 'процессора' : 'видеокарты'}, ₽<input id="resale-price-input" type="number" min="0" max="10000000" step="100" value={salePrice} onChange={event=>setSalePrice(event.target.value)} placeholder="Укажите сумму после результата" required/></label>
      <Button type="submit" disabled={salePrice===''||!onSetResalePrice}>Пересчитать варианты с этой суммой</Button></div>
      <small className="resale-price-note">Это ваш ориентир, а не подтверждённая цена продажи. Деньги появятся после сделки.</small>
    </form></details>}
    {result.upgrade_parts?.length > 0 && <ul className="upgrade-package-parts result-package-parts">{result.upgrade_parts.map(part=><li key={part.type}><span>{part.type === 'CPU' ? 'Процессор' : part.type === 'motherboard' ? 'Материнская плата' : part.type === 'memory' ? 'Оперативная память' : 'Кулер'}</span><strong>{part.name}</strong></li>)}</ul>}
    {result.platform_upgrade_note && <p className="result-note">{result.platform_upgrade_note}</p>}
    {result.mode === 'budget_plus_sell' && result.resale_status === 'unavailable' && <div className="result-note upgrade-budget" role="status"><p>{result.resale_notice}</p>{onResolveResale&&<Button variant="secondary" onClick={onResolveResale}>Указать ожидаемую цену продажи</Button>}</div>}
    {result.mode === 'budget_plus_sell' && result.resale_status !== 'unavailable' && <p className="result-note upgrade-budget">Бюджет: {result.config?.budget == null ? 'без ограничений' : `${result.total_budget.toLocaleString('ru-RU')} ₽ с учётом продажи`}. Ожидаемая выручка: {(result.current_component_price || 0).toLocaleString('ru-RU')} ₽.</p>}
    <ul className="field-hint">{result.compatibility_notes?.map(note => <li key={note}>{note}</li>)}</ul>
    {shareNotice&&<p role="status">{shareNotice}</p>}<div className="result-actions">
      {result.upgrade_price?.is_purchase_quote && /^https?:\/\//i.test(result.upgrade_price?.price_url || '') && <a className="primary-btn" href={result.upgrade_price.price_url} target="_blank" rel="noopener noreferrer">{result.upgrade_price.price_source === 'Регард' || result.upgrade_price.price_source === 'Regard' ? 'Открыть в Регарде' : 'Открыть предложение'}</a>}
      {onCompare && <Button onClick={onCompare} variant="secondary">Сравнить варианты</Button>}
      {onSave && <Button onClick={onSave}>Сохранить расчёт</Button>}
    </div>
    <details className="upgrade-more-actions"><summary>Другие действия</summary><div className="result-actions">
      <Button type="button" variant="secondary" loading={sharing} onClick={shareResult}>Поделиться ссылкой</Button>
      {result.upgrade_name && <Button variant="secondary" onClick={() => onFind({search: result.upgrade_name})}>Найти на бирже</Button>}
      {result.upgrade_name && oldName && <Button variant="secondary" onClick={() => onFind({draft: {title: oldName, price: result.current_component_price ? String(result.current_component_price) : '', condition: 'Б/У'}})}>Выставить старый компонент</Button>}
    </div></details>
  </section>
}
