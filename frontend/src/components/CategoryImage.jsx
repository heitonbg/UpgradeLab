const categoryAssets = {
  cpu: 'cpu',
  gpu: 'gpu',
  motherboard: 'motherboard',
  memory: 'memory',
  storage: 'storage',
  psu: 'psu',
  case: 'case',
  cooler: 'cooler',
}

const categoryNames = {
  cpu: 'процессор',
  gpu: 'видеокарта',
  motherboard: 'материнская плата',
  memory: 'оперативная память',
  storage: 'накопитель',
  psu: 'блок питания',
  case: 'корпус',
  cooler: 'кулер',
}

export function CategoryImage({ category, className = '' }) {
  const normalized = String(category || '').trim().toLowerCase()
  const key = categoryAssets[normalized] || 'case'
  const name = categoryNames[normalized] || 'комплектующее'

  return <figure className={`category-visual ${className}`} title={`Иллюстрация категории: ${name}`}>
    <img
      src={`/images/hardware/${key}-320.webp`}
      srcSet={`/images/hardware/${key}-160.webp 160w, /images/hardware/${key}-320.webp 320w, /images/hardware/${key}-480.webp 480w`}
      sizes="(max-width: 600px) 40vw, 240px"
      width="320"
      height="320"
      loading="lazy"
      decoding="async"
      alt={`Иллюстрация категории: ${name}`}
    />
  </figure>
}
