const labels = {
  refreshed: 'Цены обновлены',
  cached: 'Сохранённые цены',
  unavailable: 'Источник недоступен',
  not_found: 'Подходящих цен нет',
  not_attempted: 'Не проверен',
}

export function UpgradeSearchStatus({ sources = [], onRefresh }) {
  if (!sources.length) return null
  const avito = sources.find(source => source.source === 'avito')
  return <div className="upgrade-search-status" aria-label="Результат поиска цен">
    <div className="upgrade-search-heading"><strong>Поиск цен на площадках</strong>
      {onRefresh && <button type="button" className="text-link" onClick={onRefresh}>Обновить цены</button>}
    </div>
    {avito?.last_error && <p className="field-hint">Avito: {avito.last_error} {avito.status === 'cached'
      ? 'Для оценки используются ранее полученные объявления с датой под ценой.'
      : 'Новые цены Avito получить не удалось. Предложения других выбранных магазинов показаны со своим источником.'}</p>}
    <div className="upgrade-source-list">{sources.map(source => <div className={`upgrade-source-row source-${source.status}`} key={source.source}>
      <span>{source.label}</span><span>{labels[source.status] || source.status}</span>
    </div>)}</div>
    <details><summary>Подробности поиска</summary><ul className="field-hint">
      {sources.map(source => <li key={source.source}><strong>{source.label}</strong>: проверено моделей — {source.models_searched || 0}.
        {source.last_error && ` ${source.last_error}`}
        {source.checked_at && ` Проверка: ${new Date(source.checked_at).toLocaleString('ru-RU')}.`}
      </li>)}
    </ul></details>
  </div>
}
