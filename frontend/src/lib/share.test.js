import test from 'node:test'
import assert from 'node:assert/strict'
import { buildShareUrl, listingShareUrl, shareLink, sharedBuildUrl } from './share.js'

test('shared configuration opens configurator with the exact manual parts',()=>{
 globalThis.window={location:{href:'https://upgrade.example/?tab=home'}}
 const config={v:1,parts:[{category:'Оперативная память',name:'DDR4 16 ГБ',price:5500,url:'https://example.test/ram',image_url:''}]}
 const url=new URL(buildShareUrl(config))
 assert.equal(url.searchParams.get('tab'),'configurator')
 assert.deepEqual(JSON.parse(new URLSearchParams(url.hash.slice(1)).get('config')),config)
 delete globalThis.window
})

test('listing share link opens marketplace and selects its public listing ID',()=>{
 globalThis.window={location:{href:'https://upgrade.example/?tab=home'}}
 const url=new URL(listingShareUrl(42))
 assert.equal(url.searchParams.get('tab'),'marketplace')
 assert.equal(url.searchParams.get('listing'),'42')
 delete globalThis.window
})

test('sharing copies directly even when native share is available',async()=>{
 let native=0,copied='';Object.defineProperty(globalThis,'navigator',{value:{share:()=>{native++},clipboard:{writeText:async url=>{copied=url}}},configurable:true})
 assert.equal(await shareLink('https://example.test/build'),'copied');assert.equal(native,0);assert.equal(copied,'https://example.test/build');delete globalThis.navigator
})
test('saved link routes to custom configurator and drops unrelated URL state',()=>{
 globalThis.window={location:{href:'https://example.test/?reset=private',origin:'https://example.test',pathname:'/'}}
 const url=new URL(sharedBuildUrl('abc'));assert.equal(url.searchParams.get('tab'),'calculator');assert.equal(url.searchParams.get('scenario'),'custom');assert.equal(url.searchParams.get('shared'),'abc');assert.equal(url.searchParams.has('reset'),false);delete globalThis.window
})
