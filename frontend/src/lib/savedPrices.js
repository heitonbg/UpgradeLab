export function money(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('ru-RU') + ' ₽' : 'Неизвестна'
}

export function currentItemPrice(item, now = Date.now()) {
  if (item.state === 'user_zero_cost') return 0
  const until = Date.parse(item.valid_until)
  const valid = Number.isFinite(until) && (item.state === 'feed' ? now <= until : now < until)
  return valid && ['confirmed', 'feed'].includes(item.state) ? item.confirmed_price ?? null : null
}

export function currentSavedTotal(review, now = Date.now()) {
  if (!review || review.current_total == null || !review.items?.length) return null
  return review.items.every(item => currentItemPrice(item, now) != null) ? review.current_total : null
}

export function savedItemState(item, now = Date.now()) {
  if (item.state === 'user_zero_cost') return 'Нулевая стоимость указана пользователем; повторная покупка не учитывается'
  if (currentItemPrice(item, now) != null) return item.state === 'feed' ? 'Актуальное наблюдение из фида' : 'Есть свежее подтверждение цены'
  return ({
    missing: 'Предложение удалено или больше не соответствует сохранённому',
    unavailable: 'Источник недоступен; актуальная цена неизвестна',
    manual: 'Ручная цена; автоматически не подтверждается',
    historical_observation: 'Историческая оценка; свежего подтверждения нет',
  })[item.state] || 'Свежего подтверждения цены нет'
}

// Server UTC plus elapsed monotonic time avoids trusting the device wall clock.
export function reviewTime(review, elapsedMs = 0) {
  const serverTime = Date.parse(review?.evaluated_at)
  return Number.isFinite(serverTime) && Number.isFinite(elapsedMs)
    ? serverTime + Math.max(0, elapsedMs) : Infinity
}
