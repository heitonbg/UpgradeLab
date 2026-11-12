export const PUBLIC_SOURCES=Object.freeze([['regard','Regard'],['upgradelab','Биржа UpgradeLab']])
export function publicSourceIds(value) {
 const allowed=PUBLIC_SOURCES.map(([id])=>id)
 return value==null?[...allowed]:[...new Set(value.filter(id=>allowed.includes(id)))]
}
