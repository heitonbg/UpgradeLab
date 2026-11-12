import test from 'node:test'
import assert from 'node:assert/strict'
import { marketDataState,marketCountLabel,validPriceRange } from './marketState.js'
import { createCityLoader,validateCities } from './cityLoader.js'
test('failed loading never advertises a verified zero',()=>{assert.equal(marketDataState({loading:false,error:Error(),count:0}),'error');assert.equal(marketCountLabel('error',0),'Объявления не загружены')})
test('empty and failed data are distinct',()=>{assert.equal(marketDataState({loading:false,error:null,count:0}),'empty');assert.match(marketCountLabel('empty',0),/0/)})
test('previous listings remain partial while refresh fails',()=>{assert.equal(marketDataState({loading:false,error:Error(),count:8}),'partial');assert.match(marketCountLabel('partial',8),/последней/)})
test('loading with previous data is a refresh',()=>{assert.equal(marketDataState({loading:true,error:null,count:8}),'refreshing')})
test('price range accepts empty and zero but rejects negative or reversed',()=>{for(const [a,b] of [['',''],['0','100'],['100','100']])assert.ok(validPriceRange(a,b));for(const [a,b] of [['-1',''],['100','50'],['x','10']])assert.equal(validPriceRange(a,b),false)})
test('city failure can retry and concurrent loads share a request',async()=>{let calls=0;const loader=createCityLoader(async()=>{calls++;if(calls===1)throw Error('offline');return [{city_id:'real',name:'Город',region:'Регион'}]});await assert.rejects(loader.load());const [a,b]=await Promise.all([loader.load(),loader.load()]);assert.equal(calls,2);assert.equal(a,b);await loader.load(true);assert.equal(calls,3)})
test('malformed city response does not become fabricated choices',()=>{for(const value of [{detail:'offline'},[{}],null])assert.throws(()=>validateCities(value));assert.deepEqual(validateCities([]),[])})
