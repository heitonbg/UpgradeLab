import test from 'node:test'
import assert from 'node:assert/strict'
import { storeSearchDefaults } from './storeSearchDefaults.js'

test('store search inherits selected sources and geography', () => {
  assert.deepEqual(storeSearchDefaults(['regard'], {
    city_id: 42,
    geo_mode: 'city_delivery',
    max_price: 25000,
  }), {
    sources: ['regard'],
    geo: { city_id: 42, geo_mode: 'city_delivery', max_price: 25000 },
  })
})

test('store search accepts geography nested in a saved calculator config', () => {
  assert.deepEqual(storeSearchDefaults(['upgradelab'], {
    geo: { city_id: 7, geo_mode: 'city', max_price: null },
  }), {
    sources: ['upgradelab'],
    geo: { city_id: 7, geo_mode: 'city', max_price: null },
  })
})

test('store search keeps safe defaults when no prior choices exist', () => {
  assert.deepEqual(storeSearchDefaults(undefined, undefined), {
    sources: ['regard', 'upgradelab'],
    geo: { city_id: null, geo_mode: 'all', max_price: null },
  })
})
