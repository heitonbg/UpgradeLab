export function sourceSearchNotice(data) {
  const message = data.search_cached
    ? 'Показан кеш предыдущего поиска; новые запросы к источникам не выполнялись.'
    : 'Поиск завершён.'
  const partial = data.partial_result ? ' Получен частичный результат; часть источников недоступна.' : ''
  const retry = data.unavailable_sources?.length ? ' Можно повторить поиск с другими источниками.' : ''
  return message + partial + retry
}


export function missingPartNotice(gap) {
  if (!gap) return 'Подходящих предложений пока нет.'
  if (gap.blocking_reason === 'model_unconfirmed') return 'Модель или ревизия не подтверждена техническим профилем.'
  if (gap.blocking_reason === 'insufficient_characteristics') return 'Недостаточно характеристик для подтверждения совместимости. Это не доказанная несовместимость.'
  if (gap.blocking_reason === 'incompatible') return 'Найденные детали имеют подтверждённую несовместимость.'
  if (gap.blocking_reason === 'delivery_unknown') return 'Доставка в выбранный город не подтверждена.'
  if (gap.blocking_reason === 'availability_unknown') return 'Наличие в выбранном городе не подтверждено.'
  if (gap.blocking_reason === 'compatibility') return 'Не подтверждена совместимость с найденными деталями. Проверьте характеристики и разъёмы.'
  if (gap.blocking_reason === 'quality_rejected') return 'Предложения найдены, но модель или характеристики не прошли проверку. Непроверенная деталь не подставляется.'
  if (gap.blocking_reason === 'candidates_rejected') return 'Предложения найдены, но не прошли ограничения подбора. Проверьте характеристики и бюджет.'
  if (gap.blocking_reason === 'outside_budget') return 'Подходящие предложения дороже плановой доли категории. Бюджет можно перераспределить; это не цена недостающей детали.'
  return 'Подходящие предложения не получены. Это не доказывает отсутствие товара в продаже.'
}
