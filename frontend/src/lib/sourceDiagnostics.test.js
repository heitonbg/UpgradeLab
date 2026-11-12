import test from 'node:test'
import assert from 'node:assert/strict'
import { sourceSearchNotice, missingPartNotice } from './sourceDiagnostics.js'
test('cached outage is never described as a new request', () => {
  assert.match(sourceSearchNotice({search_cached:true,unavailable_sources:['dns']}), /кеш.*не выполнялись/)
})
test('partial data keeps its warning and suggests other sources', () => {
  assert.match(sourceSearchNotice({partial_result:true,unavailable_sources:['dns']}), /частичный.*другими/)
})
test('successful fresh search does not invent an outage', () => {
  assert.equal(sourceSearchNotice({search_cached:false,unavailable_sources:[]}), 'Поиск завершён.')
})

test('rejected PSU is not described as missing inventory', () => {
  assert.match(missingPartNotice({blocking_reason:'quality_rejected'}), /Предложения найдены.*не прошли/)
})
test('NVMe compatibility gap is not described as a budget shortage', () => {
  assert.match(missingPartNotice({blocking_reason:'compatibility'}), /совместимость/)
  assert.doesNotMatch(missingPartNotice({blocking_reason:'compatibility'}), /перераспределить/)
})
test('category allocation is clearly a plan', () => {
  assert.match(missingPartNotice({blocking_reason:'outside_budget'}), /плановой доли.*перераспределить/)
})
