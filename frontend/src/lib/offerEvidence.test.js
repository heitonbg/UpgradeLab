import test from 'node:test'
import assert from 'node:assert/strict'
import { offerEvidence, compatibilityNotice } from './offerEvidence.js'
test('seller declarations are distinct from verified store prices',()=>{
  const text=offerEvidence({offer_type:'seller',price_trust:'seller_declared',geography:{}})
  assert.match(text,/Частный продавец.*заявлена продавцом/);assert.doesNotMatch(text,/сверена/)
})
test('unknown delivery does not imply free delivery',()=>{
  assert.match(offerEvidence({geography:{delivery_match:true,delivery_cost_rub:null}}),/стоимость неизвестна/)
  assert.match(offerEvidence({geography:{}}),/География неизвестна.*не подтверждена/)
})
test('known zero delivery is displayed separately from unknown cost',()=>{
  assert.match(offerEvidence({geography:{delivery_match:true,delivery_cost_rub:0}}),/Доставка: 0/)
})
test('unknown and incompatible technical states stay distinct',()=>{
  assert.match(compatibilityNotice({status:'unknown'}),/Недостаточно/)
  assert.match(compatibilityNotice({status:'incompatible'}),/несовместимость/)
  assert.match(compatibilityNotice({status:'compatible'}),/подтверждена/)
})
