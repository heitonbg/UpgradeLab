export function sourceSearchNotice(data) {
  const message = data.search_cached
    ? 'Показан кеш предыдущего поиска; новые запросы к источникам не выполнялись.'
    : 'Поиск завершён.'
  const partial = data.partial_result ? ' Получен частичный результат; часть источников недоступна.' : ''
  const retry = data.unavailable_sources?.length ? ' Можно повторить поиск с другими источниками.' : ''
  return message + partial + retry
}
