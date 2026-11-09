import test from 'node:test'
import assert from 'node:assert/strict'
import { filterListings, listingPrice, listingCategory } from './marketplace.js'

const listings = [
  {id:1,title:'RTX 3060',price:'18 000 ₽',listing_type:'sale',condition:'Б/У',created_at:'2026-10-27T12:00:00'},
  {id:2,title:'Samsung SSD 870 EVO',price:'Договорная',listing_type:'sale',condition:'Новое',created_at:'2026-10-28T12:00:00'},
  {id:3,title:'Блок питания MSI',price:'Обмен',listing_type:'exchange',condition:'Новое',created_at:'2026-10-28T13:00:00'},
]
test('exchange and unspecified prices do not become zero-ruble sale offers',()=>{
  assert.equal(listingPrice(listings[1]),null)
  assert.equal(listingPrice(listings[2]),null)
  assert.equal(listingPrice(listings[0]),18000)
  assert.deepEqual(filterListings(listings,{max:'20000'}).map(l=>l.id),[1])
})
test('search, deal type, condition and category combine',()=>{
  assert.equal(listingCategory(listings[1]),'storage')
  assert.deepEqual(filterListings(listings,{deal:'exchange',condition:'new',category:'psu'}).map(l=>l.id),[3])
  assert.deepEqual(filterListings(listings,{search:' rTx ',deal:'sale',condition:'used'}).map(l=>l.id),[1])
  assert.deepEqual(filterListings(listings,{}).map(l=>l.id),[3,2,1])
  assert.deepEqual(listings.map(l=>l.id),[1,2,3])
})

test('city filtering excludes other cities and unknown location',()=>{
  const rows=[{...listings[0],id:1,city_id:'ru:kemerovo'},{...listings[0],id:2,city_id:'ru:kem'},{...listings[0],id:3}]
  assert.deepEqual(filterListings(rows,{city_id:'ru:kemerovo'}).map(row=>row.id),[1])
})
test('sold and withdrawn listings never remain in cached public results',()=>{
  assert.deepEqual(filterListings([{...listings[0],publication_status:'sold'},{...listings[1],publication_status:'withdrawn'}],{}),[])
})
test('broken condition is distinct from used and explicit category beats title guesses',()=>{
  const row={...listings[0],condition:'Неисправное',category:'GPU'}
  assert.deepEqual(filterListings([row],{condition:'used'}),[])
  assert.equal(filterListings([row],{condition:'broken'}).length,1)
  assert.equal(listingCategory(row),'gpu')
})
