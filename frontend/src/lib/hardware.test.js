import test from 'node:test'
import assert from 'node:assert/strict'
import { matchHardware, parseSystemReport, searchHardware } from './hardware.js'

const items = [
  {id:1,name:'AMD FX-6100 Six-Core'},
  {id:2,name:'AMD FX-6300 Six-Core'},
  {id:3,name:'AMD Ryzen 5 3600'},
  {id:4,name:'GeForce RTX 3060'},
  {id:5,name:'GeForce RTX 3060 Ti'},
]

test('compact CPU query finds a hyphenated model',()=>{
  assert.deepEqual(searchHardware(items,'fx6100').map(x=>x.id),[1])
  assert.equal(matchHardware(items,'AMD FX(tm)-6100 Six-Core Processor').id,1)
  assert.equal(matchHardware(items,'AMD Ryzen 5 3600 6-Core Processor').id,3)
})
test('GPU matching preserves Ti and rejects unknown models',()=>{
  assert.equal(matchHardware(items,'NVIDIA GeForce RTX 3060').id,4)
  assert.equal(matchHardware(items,'NVIDIA GeForce RTX 3060 Ti').id,5)
  assert.equal(matchHardware(items,'NVIDIA GeForce RTX 3060 Super'),null)
  assert.equal(matchHardware(items,''),null)
})
test('report preserves physical RAM type and does not invent dual channel',()=>{
  const report=parseSystemReport(JSON.stringify({cpus:[{name:'AMD FX-6100'}],gpus:[],memory:{capacity_gb:8,type:'DDR3',channels:null,module_count:2}}))
  assert.equal(report.memory.type,'DDR3')
  assert.equal(report.memory.capacity_gb,8)
  assert.equal(report.memory.channels,null)
})
test('legacy report imports capacity without selecting an arbitrary DDR kit',()=>{
  const report=parseSystemReport('=== CPU ===\nМодель: AMD FX-6100\n=== Оперативная память ===\nВсего: 7,96 ГБ')
  assert.equal(report.memory.capacity_gb,8)
  assert.equal(report.memory.type,null)
  assert.equal(report.memory.channels,null)
})
