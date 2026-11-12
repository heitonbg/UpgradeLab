const names={CPU:'процессора',GPU:'видеокарты',motherboard:'материнской платы',memory:'оперативной памяти',storage:'SSD',psu:'блока питания',case:'корпуса',cooler:'кулера'}
export function CategoryImage({category,className='',label=false}) {
 const key=category==='CPU'?'cpu':category==='GPU'?'gpu':category
 const known=Object.hasOwn(names,category)
 return <figure className={`category-visual ${className}`} title="Декоративная иллюстрация категории, не фотография товара"><img src={known?`/images/hardware/${key}-320.webp`:'/images/hardware/placeholder.svg'} srcSet={known?`/images/hardware/${key}-160.webp 160w, /images/hardware/${key}-320.webp 320w, /images/hardware/${key}-480.webp 480w`:undefined} sizes="(max-width: 600px) 40vw, 240px" width="320" height="320" loading="lazy" decoding="async" alt={known?`Иллюстрация категории ${names[category]}, не фото товара`:'Фото товара отсутствует'}/>{label&&<figcaption>Иллюстрация категории · фото товара отсутствует</figcaption>}</figure>
}
