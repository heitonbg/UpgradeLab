export function fpsText(estimate, outlook) {
  return outlook ? `${outlook.minimum}–${outlook.maximum}` : `~${estimate}`
}

export function targetText(outlook, target, reached = false) {
  if (!outlook) return reached ? 'Цель достигнута по модели' : 'Ниже вашей цели'
  if (outlook.minimum >= target) return 'Ориентир выше цели'
  if (outlook.maximum < target) return 'Ориентир ниже цели'
  return 'Цель внутри диапазона — есть неопределённость'
}

export function upgradeTargetText(estimate, target) {
  return estimate >= target
    ? `Цель достигнута по прогнозу (${estimate} FPS)`
    : `До цели по прогнозу не хватает ${target - estimate} FPS`
}
