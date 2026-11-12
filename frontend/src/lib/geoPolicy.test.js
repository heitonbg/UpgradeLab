import test from 'node:test'
import assert from 'node:assert/strict'
import {geoWithCity} from './geoPolicy.js'
test('choosing a city activates its visible local filter and preserves other form values',()=>assert.deepEqual(geoWithCity({geo_mode:'all',budget:80000},'ru:kemerovo'),{geo_mode:'local',budget:80000,city_id:'ru:kemerovo'}))
test('clearing a city cannot leave an invalid local or delivery request',()=>assert.equal(geoWithCity({geo_mode:'delivery',city_id:'ru:kemerovo'},null).geo_mode,'all'))
test('changing a selected city preserves an explicit delivery mode',()=>assert.equal(geoWithCity({geo_mode:'delivery'},'ru:kemerovo').geo_mode,'delivery'))
