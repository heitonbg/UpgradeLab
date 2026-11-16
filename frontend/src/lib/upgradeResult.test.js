import test from 'node:test'
import assert from 'node:assert/strict'
import { upgradePrice, gainPresentation } from './upgradeResult.js'

test('unlimited budget displays existing store quote without replacing it by reference',()=>{
 const result={budget:null,upgrade_name:'RTX 5070',avg_price:50000,upgrade_price:{avg_price:49990,price_origin:'catalog_import',price_date:'2026-11-16',price_source:'Регард'}}
 assert.equal(upgradePrice(result).amount,49990)
 assert.equal(upgradePrice(result).quote.price_origin,'catalog_import')
 assert.deepEqual(upgradePrice({...result,budget:70000}),upgradePrice(result))
})
test('unknown price remains unknown and missing selection hides summary',()=>{
 assert.equal(upgradePrice({upgrade_name:'RTX 5090',upgrade_price:{},avg_price:null}).amount,null)
 assert.equal(upgradePrice({}).visible,false)
})
test('cross-method percentage is an explicitly approximate difference',()=>{
 const value=gainPresentation({current_fps:48,upgraded_fps:123,fps_result:{gain_type:null}})
 assert.equal(value.percent,156.25);assert.equal(value.delta,75)
 assert.equal(value.title,'Разница оценок');assert.match(value.note,/Разные методы/)
})
test('comparable model gains, losses and zero baseline retain honest meaning',()=>{
 assert.equal(gainPresentation({current_fps:100,upgraded_fps:90,fps_result:{gain_type:'same_model_estimate'}}).percent,-10)
 assert.equal(gainPresentation({current_fps:0,upgraded_fps:90}).percent,null)
 assert.equal(gainPresentation({current_fps:100,upgraded_fps:null}).delta,null)
})
