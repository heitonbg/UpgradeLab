import test from 'node:test'
import assert from 'node:assert/strict'
import { SPEC_FIELDS,deliveryDraft,deliveryPayload,deliveryText,technicalText } from './listingDetails.js'
test('all eight categories have distinct field schemas',()=>{assert.deepEqual(Object.keys(SPEC_FIELDS).sort(),['CPU','GPU','case','cooler','memory','motherboard','psu','storage'].sort());assert.ok(SPEC_FIELDS.CPU.some(f=>f[0]==='integrated_graphics'))})
test('legacy absent delivery remains unknown',()=>{assert.equal(deliveryDraft(null),null);assert.equal(deliveryPayload(null),null);assert.match(deliveryText(null),/неизвестны/)})
test('unknown delivery is not free',()=>{const d=deliveryDraft({mode:'russia',cost_rub:null});assert.equal(deliveryPayload(d).cost_rub,null);assert.match(deliveryText(d),/уточняется/)})
test('explicit free and paid shipping are distinct',()=>{for(const price of [0,700])assert.equal(deliveryPayload(deliveryDraft({mode:'russia',cost_rub:price})).cost_rub,price)})
test('server trust and UI metadata never sent back',()=>{assert.deepEqual(deliveryPayload(deliveryDraft({mode:'cities',city_ids:['fixture'],cost_rub:700,kind:'store_confirmed',checked_at:'future',city_labels:{fixture:'City'}})),{mode:'cities',city_ids:['fixture'],cost_rub:700,terms:''})})
test('fractional, negative and missing fixed price rejected',()=>{for(const price of [1.5,-1,'',null])assert.throws(()=>deliveryPayload({mode:'russia',cost_mode:'fixed',cost_rub:price}))})
test('cities need targets and pickup discards hidden shipping fields',()=>{assert.throws(()=>deliveryPayload({mode:'cities',city_ids:[]}));assert.deepEqual(deliveryPayload({mode:'pickup',city_ids:['old'],cost_mode:'fixed',cost_rub:700}),{mode:'pickup',city_ids:[],cost_rub:null,terms:''})})
test('technical hints distinguish contradictions from missing evidence',()=>{assert.match(technicalText({state:'contradictory'}),/Противоречивые/);assert.match(technicalText({optimizer_eligible:false}),/Недостаточно/);assert.match(technicalText({optimizer_eligible:true}),/предварительного/)})
