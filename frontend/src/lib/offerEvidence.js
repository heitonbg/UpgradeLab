export function offerEvidence(offer) {
  const g=offer.geography||{}
  const kind=offer.offer_type==='seller'?'Частный продавец':offer.offer_type==='catalog'?'Прайс-лист':'Магазин'
  const price=offer.price_trust==='seller_declared'?'Цена заявлена продавцом':offer.price_trust==='verified'?'Цена сверена по карточке':offer.price_trust==='catalog_import'?'Цена по прайс-листу':'Цена не подтверждена'
  const place=g.location_status==='seller_declared'?'Город заявлен продавцом':g.location_status==='store_stock'?'Есть подтверждение магазина':'География неизвестна'
  const delivery=g.delivery_match?(g.delivery_cost_rub==null?'Доставка заявлена, стоимость неизвестна':`Доставка: ${g.delivery_cost_rub.toLocaleString('ru-RU')} ₽`):'Доставка не подтверждена'
  return `${kind} · ${price} · ${place} · ${delivery}`
}
export function compatibilityNotice(value) {
  return value?.status==='compatible'?'Совместимость подтверждена':value?.status==='incompatible'?'Есть подтверждённая несовместимость':'Недостаточно характеристик для подтверждения совместимости'
}
