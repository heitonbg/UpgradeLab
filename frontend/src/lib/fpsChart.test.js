import test from 'node:test'
import assert from 'node:assert/strict'
import { fpsChartData } from './fpsChart.js'
test('chart preserves computed values and target',()=>{const d=fpsChartData(42,78,60);assert.deepEqual(d.points,[['Текущая система',42],['После апгрейда',78]]);assert.equal(d.max,80);assert.equal(d.target,60)})
test('invalid values never turn into fictitious FPS',()=>{assert.deepEqual(fpsChartData(null,NaN,undefined).points,[]);assert.equal(fpsChartData(null,NaN,undefined).target,null)})
test('zero FPS is retained without division by zero',()=>{assert.equal(fpsChartData(0,0,0).points.length,2);assert.equal(fpsChartData(0,0,0).max,10)})
test('negative and infinite predictions are excluded',()=>{assert.deepEqual(fpsChartData(-1,Infinity,60).points,[])})
