import test from 'node:test'
import assert from 'node:assert/strict'
import { sortOffers,priceOriginLabel,catalogQuery } from './catalogView.js'
test('sorting is deterministic without mutating fetched offers',()=>{const rows=[{id:2,name:'B',price_rub:200},{id:1,name:'A',price_rub:100}];assert.deepEqual(sortOffers(rows).map(x=>x.id),[1,2]);assert.equal(rows[0].id,2);assert.deepEqual(sortOffers(rows,'name').map(x=>x.id),[1,2])})
test('unknown observation date cannot be newest',()=>{assert.equal(sortOffers([{id:1,name:'A',observed_at:null},{id:2,name:'B',observed_at:'2026-11-09T12:00:00Z'}],'newest')[0].id,2)})
test('catalogue or seller evidence never becomes verified badge',()=>{assert.match(priceOriginLabel('seller_declared','2026-11-09'),/продавцом/);assert.match(priceOriginLabel('catalog_import','2026-11-09'),/прайс/);assert.match(priceOriginLabel('public_page',null),/не подтверждена/)})

test('reference price cannot receive verified badge',()=>{assert.match(priceOriginLabel('reference','2026-11-10'),/Справочная/);assert.doesNotMatch(priceOriginLabel('reference','2026-11-10'),/сверена/)})

test('all categories sends no empty enum filter to the real catalog API',()=>{
 const all=new URLSearchParams(catalogQuery('Ryzen 5','',2))
 assert.equal(all.has('category'),false)
 assert.equal(all.get('q'),'Ryzen 5')
 assert.equal(all.get('page'),'2')
 assert.equal(new URLSearchParams(catalogQuery('','CPU')).get('category'),'CPU')
})
