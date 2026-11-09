import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeContact, contactPreview } from './contacts.js'
import {citySuggestions,cityLabel} from './cities.js'
test('all Telegram examples have one destination',()=>{
  for(const value of ['iwrawww','@iwrawww','t.me/iwrawww','https://t.me/iwrawww']) assert.equal(normalizeContact(value).href,'https://t.me/iwrawww')
})
test('all Russian phone examples have one destination',()=>{
  for(const value of ['+79961234567','79961234567','89961234567','7(996)1234567','+7 (996) 123-45-67','8 (996) 123-45-67','9961234567']) assert.equal(normalizeContact(value).href,'tel:+79961234567')
})
test('partial phone cannot be submitted as complete contact',()=>{
  for(const value of ['+7996','7(996)']) assert.ok(contactPreview(value).error)
})
test('unsafe and lookalike links are rejected',()=>{
  for(const value of ['javascript:alert(1)','https://t.me.evil/iwrawww','https://user@t.me/iwrawww']) assert.throws(()=>normalizeContact(value,'telegram'))
})
test('unrecognized legacy contact remains text without link',()=>assert.equal(contactPreview('Спрашивать продавца').contact,null))
const cities=[{city_id:'a',name:'Кемь',region:'Карелия'},{city_id:'b',name:'Кемерово',region:'Кузбасс'},
{city_id:'c',name:'Советск',region:'Кировская область'},{city_id:'d',name:'Советск',region:'Тульская область'}]
test('Russian prefix finds distinct city IDs',()=>assert.deepEqual(citySuggestions(cities,'Кем').map(c=>c.city_id),['a','b']))
test('namesakes have distinct labels and IDs',()=>assert.notEqual(cityLabel(cities[2]),cityLabel(cities[3])))
