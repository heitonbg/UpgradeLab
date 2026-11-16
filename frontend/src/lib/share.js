import { request } from '../api/client.js'
export async function shareLink(url) {
 if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(url);return 'copied'}catch{}}
 const input=document.createElement('textarea');input.value=url;input.setAttribute('readonly','');input.style.position='fixed';input.style.opacity='0';document.body.appendChild(input)
 const focused=document.activeElement
 try{input.select();if(!document.execCommand('copy'))throw Error('Не удалось скопировать ссылку. Разрешите доступ к буферу обмена.');return 'copied'}finally{input.remove();focused?.focus()}
}
export function sharedBuildUrl(id){const url=new URL(window.location.pathname,window.location.origin);url.searchParams.set('tab','calculator');url.searchParams.set('scenario','custom');url.searchParams.set('shared',id);return url.toString()}
export async function saveAndShareBuild(snapshot){
 const saved=await request('/api/shared-builds',{method:'POST',body:snapshot})
 window.dispatchEvent(new Event('upgradelab:shared-saved'))
 const url=sharedBuildUrl(saved.id)
 try{await shareLink(url)}catch{throw Error(`Снимок сохранён. Скопируйте ссылку: ${url}`)}
 return url
}

export function buildShareUrl(config) {
  const url = new URL(window.location.href)
  url.searchParams.set('tab', 'configurator')
  url.hash = `config=${encodeURIComponent(JSON.stringify(config))}`
  return url.toString()
}

export function listingShareUrl(listingId) {
  const url = new URL(window.location.pathname, window.location.origin || new URL(window.location.href).origin)
  url.searchParams.set('tab', 'marketplace')
  url.searchParams.set('listing', String(listingId))
  url.hash = ''
  return url.toString()
}
