export function fpsChartData(current,upgraded,target) {
 const valid=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0
 const points=[['Текущая система',current],['После апгрейда',upgraded]].filter(([,value])=>valid(value))
 const max=Math.max(10,...points.map(([,value])=>value),valid(target)?target:0)
 return {points,max:Math.ceil(max/10)*10,target:valid(target)?target:null}
}
