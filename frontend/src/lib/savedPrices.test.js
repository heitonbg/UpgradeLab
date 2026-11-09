import test from 'node:test'
import assert from 'node:assert/strict'
import { currentItemPrice, currentSavedTotal, savedItemState, money, reviewTime } from './savedPrices.js'
const now = Date.parse('2026-11-09T12:00:00Z')
const item = {state:'confirmed', confirmed_price:10000, valid_until:'2026-11-09T12:15:00Z'}
const review = {historical_total:8000, current_total:10000, items:[item]}
test('historical and changed current totals stay separate', () => {
  assert.equal(currentSavedTotal(review,now),10000)
  assert.equal(review.historical_total,8000)
})
test('open page stops claiming a confirmed price at TTL boundary', () => {
  assert.equal(currentSavedTotal(review,now+15*60000),null)
  assert.match(savedItemState(item,now+15*60000),/нет/)
})
test('deleted and unavailable offers have no current price', () => {
  for (const state of ['missing','unavailable']) assert.equal(currentItemPrice({...item,state},now),null)
})
test('manual estimate cannot become a confirmed total', () => {
  assert.equal(currentSavedTotal({...review,items:[{state:'manual'}]},now),null)
})
test('zero user cost is kept without a fake market observation', () => {
  assert.equal(currentItemPrice({state:'user_zero_cost'},now),0)
})
test('legacy and missing price reviews remain unknown', () => {
  assert.equal(currentSavedTotal(undefined,now),null)
  assert.equal(money(null),'Неизвестна')
})
test('feed observation preserves inclusive 24 hour boundary', () => {
  assert.equal(currentItemPrice({...item,state:'feed'},now+15*60000),10000)
  assert.equal(currentItemPrice({...item,state:'feed'},now+15*60000+1),null)
})
test('invalid expiry never confirms a price', () => {
  assert.equal(currentItemPrice({...item,valid_until:'broken'},now),null)
})

test('server clock plus elapsed time determines freshness on an open page', () => {
  const serverReview = {...review, evaluated_at:'2026-11-09T12:00:00Z'}
  assert.equal(currentSavedTotal(serverReview, reviewTime(serverReview,15*60000)),null)
  assert.equal(reviewTime(serverReview,1000),now+1000)
})
test('missing server evaluation time cannot extend freshness', () => {
  assert.equal(currentSavedTotal(review, reviewTime(review,0)),null)
})
