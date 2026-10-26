export function AdditionalUpgrades({ cpuSocket, ramType, ramCapacity }) {
  const suggestions=[]
  if(ramCapacity&&ramCapacity<=8)suggestions.push(['Объём памяти',`В сборке ${ramCapacity} ГБ RAM. Если игре не хватает памяти, увеличение объёма может уменьшить подгрузки и задержки.`])
  if(ramType==='DDR3')suggestions.push(['Совместимость памяти','DDR4 и DDR5 не устанавливаются в слот DDR3. Для перехода потребуется совместимая платформа.'])
  if(cpuSocket)suggestions.push(['Материнская плата',`Текущий сокет: ${cpuSocket}. Перед покупкой CPU проверьте список поддержки процессоров и версию BIOS на сайте производителя платы.`])
  suggestions.push(['Питание и габариты','Для замены GPU проверьте мощность и разъёмы блока питания, а также свободное место в корпусе.'])
  return <details className="panel"><summary className="text-sm cursor-pointer">Что проверить перед покупкой</summary><ul className="checklist mt-4">{suggestions.map(([title,body])=><li key={title}><strong>{title}</strong><p>{body}</p></li>)}</ul></details>
}
