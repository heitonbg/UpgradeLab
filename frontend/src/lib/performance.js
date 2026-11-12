export function fpsText(estimate, outlook) {
  if(outlook&&Number.isFinite(outlook.minimum)&&Number.isFinite(outlook.maximum)&&outlook.minimum>=0&&outlook.maximum>=outlook.minimum)return `${outlook.minimum}–${outlook.maximum}`
  return Number.isFinite(estimate)&&estimate>=0?`~${estimate}`:'Нет данных'
}

export function targetText(outlook, target, reached = false) {
  if (reached === null) return 'Цель не подтверждена замерами; FPS — ориентир модели'
  if (!outlook) return reached ? 'Цель достигнута по модели' : 'Диапазон не подтверждён'
  if (outlook.minimum >= target) return 'Ориентир выше цели'
  if (outlook.maximum < target) return 'Ориентир ниже цели'
  return 'Цель внутри диапазона — есть неопределённость'
}

export function upgradeTargetText(estimate, target) {
  if(!Number.isFinite(estimate))return 'Недостаточно данных для FPS'
  return estimate >= target
    ? `Цель достигнута по прогнозу (${estimate} FPS)`
    : `До цели по прогнозу не хватает ${target - estimate} FPS`
}
