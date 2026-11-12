import test from 'node:test'
import assert from 'node:assert/strict'
import {buildTrust,distinctBuilds,variantHeading} from './buildPresentation.js'
test('reference prices remain analytical even with inconsistent readiness flags',()=>assert.equal(buildTrust({status:'complete',purchase_ready:true,prices_confirmed:true,parts:[{price_basis:'reference'}]}).kind,'reference'))
test('missing price confirmation cannot be displayed as verified',()=>assert.equal(buildTrust({status:'complete',purchase_ready:true}).kind,'draft'))
test('complete confirmed purchase receives a factual price-check label',()=>assert.equal(buildTrust({status:'complete',purchase_ready:true,prices_confirmed:true,parts:[]}).kind,'verified'))
test('same full configuration is not offered three times under different titles',()=>{const parts=[{type:'CPU',id:1,price:100},{type:'GPU',id:2,price:200}];assert.equal(distinctBuilds([{parts,title:'A'},{parts:[...parts].reverse(),title:'B'},{parts,title:'C'}]).length,1)})
test('different actual source offers are preserved',()=>assert.equal(distinctBuilds([{parts:[{type:'GPU',offer_id:1,price:100}]},{parts:[{type:'GPU',offer_id:2,price:100}]}]).length,2))
test('value title does not claim an unproven cheapest configuration',()=>assert.equal(variantHeading({variant_key:'value'}),'Цена и возможности'))
import {compatibilityLabel} from './buildPresentation.js'
test('missing compatibility evidence never claims a compatible PC',()=>assert.equal(compatibilityLabel({technical_compatibility_confirmed:true}),'Совместимость требует проверки'))
test('known incompatibility takes precedence over contradictory readiness',()=>assert.match(compatibilityLabel({technical_compatibility_confirmed:true,compatibility_status:'incompatible'}),/Есть несовместимость/))
test('only explicit compatible evidence gets the checked label',()=>assert.match(compatibilityLabel({technical_compatibility_confirmed:true,compatibility_status:'compatible'}),/характеристикам проверена/))
import {buildMetric} from './buildPresentation.js'
test('CPU work displays the existing hardware proxy instead of a hidden game forecast',()=>{const metric=buildMetric({workload:'cpu_work',selection_score:21000,fps:999});assert.equal(metric.label,'CPU Mark');assert.equal(metric.kind,'cpu');assert.match(metric.value,/21/);assert.ok(!metric.value.includes('999'))})
test('missing CPU work score never falls back to unrelated FPS',()=>assert.equal(buildMetric({workload:'cpu_work',fps:999}).value,'Нет данных'))
test('gaming still displays the given FPS range',()=>assert.equal(buildMetric({fps:63,fps_outlook:{minimum:45,maximum:70}}).value,'45–70'))
