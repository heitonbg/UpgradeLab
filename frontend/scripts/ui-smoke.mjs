// Local browser check: start Vite and Edge with --remote-debugging-port=9223.
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const pages=await (await fetch('http://127.0.0.1:9223/json')).json()
const page=pages.find(p=>p.type==='page')
const ws=new WebSocket(page.webSocketDebuggerUrl)
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}))
let next=0
const pending=new Map()
ws.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id){const promise=pending.get(data.id);pending.delete(data.id);data.error?promise.reject(new Error(data.error.message)):promise.resolve(data.result)}})
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value}
async function until(expression){for(let i=0;i<80;i++){if(await evaluate(`Boolean(${expression})`))return;await new Promise(resolve=>setTimeout(resolve,100))}throw new Error(`Timed out: ${expression}`)}
const artifacts=fileURLToPath(new URL('../../.artifacts/',import.meta.url))
await mkdir(artifacts,{recursive:true})
try {
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false})
  await send('Page.navigate',{url:process.env.UI_BASE_URL||'http://localhost:5173'})
  await until(`document.querySelector('input[placeholder="Найти процессор"]')`)
  await evaluate(`document.querySelector('input[placeholder="Найти процессор"]').focus()`)
  await send('Input.insertText',{text:'fx6100'})
  await until(`Array.from(document.querySelectorAll('[role=option]')).some(x=>x.textContent.includes('FX-6100'))`)
  await evaluate(`Array.from(document.querySelectorAll('[role=option]')).find(x=>x.textContent.includes('FX-6100')).dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))`)
  assert.match(await evaluate(`document.querySelector('input[placeholder="Найти процессор"]').value`),/FX-6100/)
  const doc=await send('DOM.getDocument')
  const input=await send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'input[type=file]'})
  await send('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[fileURLToPath(new URL('./fixtures/hardware-report.json',import.meta.url))]})
  await until(`document.querySelector('.import-summary')`)
  assert.equal(await evaluate(`document.querySelector('input[placeholder="Например, 8"]').value`),'8')
  assert.equal(await evaluate(`document.querySelectorAll('.three-columns select')[0].value`),'DDR3')
  assert.equal(await evaluate(`document.querySelectorAll('.three-columns select')[1].value`),'')
  assert.match(await evaluate(`document.querySelector('input[placeholder="Найти видеокарту"]').value`),/1050 Ti/)
  assert.equal(await evaluate(`document.documentElement.scrollWidth > innerWidth`),false)
  const desktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})
  await writeFile(`${artifacts}/configuration-desktop.png`,Buffer.from(desktop.data,'base64'))
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  assert.equal(await evaluate(`document.documentElement.scrollWidth > innerWidth`),false)
  const mobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})
  await writeFile(`${artifacts}/configuration-mobile.png`,Buffer.from(mobile.data,'base64'))
  if(process.env.UI_AUTH_CHECK==='1') {
    const fill=async(expression,text)=>{await evaluate(`(()=>{const input=${expression};input.focus();input.select()})()`);await send('Input.insertText',{text})}
    const email=`browser-${Date.now()}@example.test`
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false})
    await evaluate(`document.querySelectorAll('.side-nav button')[2].click()`)
    await until(`document.querySelector('.auth-form')`)
    await evaluate(`document.querySelectorAll('.auth-tabs button')[1].click()`)
    await fill(`document.querySelector('[autocomplete=name]')`,'Browser Check')
    await fill(`document.querySelector('[autocomplete=email]')`,email)
    await fill(`document.querySelectorAll('[autocomplete=new-password]')[0]`,'browser-test-password')
    await fill(`document.querySelectorAll('[autocomplete=new-password]')[1]`,'browser-test-password')
    await evaluate(`document.querySelector('.auth-form .primary-btn').click()`)
    await until(`document.querySelector('.account-toolbar')`)
    await send('Page.reload')
    await until(`document.querySelectorAll('.side-nav button').length===3`)
    await evaluate(`document.querySelectorAll('.side-nav button')[2].click()`)
    await until(`document.querySelector('.account-toolbar')`)
    await evaluate(`document.querySelector('.account-toolbar button').click()`)
    await until(`document.querySelector('.auth-form')`)
    await fill(`document.querySelector('[autocomplete=email]')`,email)
    await fill(`document.querySelector('[autocomplete=current-password]')`,'browser-test-password')
    await evaluate(`document.querySelector('.auth-form .primary-btn').click()`)
    await until(`document.querySelector('.account-toolbar')`)
    console.log('Browser authentication passed: registration, persistent session, logout and password login.')
  }
  console.log('Browser check passed: searchable CPU, system report, DDR3 RAM, unknown channels, responsive width.')
} finally {ws.close()}
