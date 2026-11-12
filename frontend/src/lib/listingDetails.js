export const SPEC_FIELDS={
 CPU:[['manufacturer','Производитель'],['model','Полная модель'],['socket','Сокет'],['generation','Поколение'],['integrated_graphics','Встроенная графика','boolean']],
 GPU:[['gpu_manufacturer','Производитель GPU'],['model','Полная модель с Ti/Super'],['vram','VRAM, ГБ','number'],['board_manufacturer','Производитель исполнения'],['length_mm','Длина видеокарты, мм','number'],['power_connectors','Дополнительное питание']],
 motherboard:[['manufacturer','Производитель'],['model','Модель платы'],['revision','Ревизия'],['socket','Сокет'],['chipset','Чипсет'],['ram_type','Тип RAM',['DDR3','DDR4','DDR5']],['form_factor','Форм-фактор',['ATX','mATX','Mini-ITX','EATX']],['storage_interfaces','Интерфейсы SSD',['SATA','NVMe'],'list'],['m2_sizes','Размеры M.2',[2230,2242,2260,2280,22110],'list'],['m2_free_slots','Свободных слотов M.2','number']],
 memory:[['model','Модель памяти'],['ram_type','Тип RAM',['DDR3','DDR4','DDR5']],['capacity_gb','Общий объём, ГБ','number'],['modules','Физических модулей','number'],['frequency_mhz','Частота, МГц','number'],['module_type','Тип модуля',['DIMM','SO-DIMM','RDIMM','ECC']]],
 storage:[['manufacturer','Производитель'],['model','Модель SSD'],['revision','Ревизия'],['capacity_gb','Объём, ГБ','number'],['interface','Интерфейс',['SATA','NVMe']],['form_factor','Форм-фактор',['M.2','2.5','mSATA','external']],['m2_size','Размер M.2',[2230,2242,2260,2280,22110]]],
 psu:[['manufacturer','Производитель'],['model','Полная модель БП'],['revision','Ревизия'],['watts','Мощность, Вт','number'],['form_factor','Форм-фактор',['ATX','SFX','SFX-L']],['power_connectors','Какие разъёмы есть']],
 case:[['manufacturer','Производитель'],['model','Модель корпуса'],['form_factor','Тип корпуса'],['board_formats','Поддерживаемые платы',['ATX','mATX','Mini-ITX','EATX'],'list'],['psu_formats','Поддерживаемые БП',['ATX','SFX','SFX-L'],'list'],['max_gpu_length_mm','Максимальная длина GPU, мм','number'],['max_cooler_height_mm','Максимальная высота кулера, мм','number']],
 cooler:[['model','Модель кулера'],['sockets','Совместимые сокеты',['AM4','AM5','LGA1151','LGA1200','LGA1700','LGA1851'],'list'],['height_mm','Высота, мм','number'],['cooling_type','Тип охлаждения',['air','liquid']]]
}
export function deliveryDraft(value){return value?{mode:value.mode||'cities',city_ids:value.city_ids||[],cost_rub:value.cost_rub??null,terms:value.terms||'',cost_mode:value.cost_rub==null?'unknown':value.cost_rub===0?'free':'fixed',city_labels:value.city_labels||{}}:null}
export function deliveryPayload(value){
 if(!value)return null
 const shipping=['cities','russia'].includes(value.mode)
 if(value.mode==='cities'&&!value.city_ids?.length)throw Error('Выберите города доставки')
 let cost=null
 if(shipping&&value.cost_mode==='free')cost=0
 if(shipping&&value.cost_mode==='fixed'){
   cost=Number(value.cost_rub)
   if(!Number.isInteger(cost)||cost<=0||cost>1000000)throw Error('Укажите целую стоимость доставки в рублях')
 }
 return {mode:value.mode||'unknown',city_ids:value.mode==='cities'?value.city_ids||[]:[],cost_rub:cost,terms:value.terms||''}
}
export function technicalText(value){return value?.state==='contradictory'?'Противоречивые характеристики':value?.optimizer_eligible?`${({trusted_profile:'Есть технический профиль',catalog_matched:'Модель сопоставлена с каталогом',seller_declared:'Характеристики заявлены продавцом'})[value.state]||'Характеристики оценены'} · подходит для предварительного подбора`:'Недостаточно данных для проверки совместимости'}
export function deliveryText(value){
 if(!value||value.mode==='unknown')return 'Условия передачи и доставки неизвестны'
 if(value.mode==='meetup')return 'Только личная встреча'
 if(value.mode==='pickup')return 'Самовывоз в городе продавца'
 const where=value.mode==='russia'?'Отправка по России':'Отправка в выбранные города'
 return `${where} · ${value.cost_rub==null?'стоимость уточняется':value.cost_rub===0?'бесплатно (заявлено продавцом)':`${value.cost_rub.toLocaleString('ru-RU')} ₽`} · заявление продавца`
}
