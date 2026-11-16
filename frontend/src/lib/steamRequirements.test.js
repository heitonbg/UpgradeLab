import test from 'node:test'
import assert from 'node:assert/strict'
import {enrichSelectedGame} from './steamRequirements.js'

test('100 concurrent selections share a single POST and one completion poll',async()=>{
  let posts=0,gets=0,notifications=0
  const send=async(url,options)=>{if(options?.method==='POST'){posts++;return {status:'queued',version:null}}gets++;return {status:'available',version:'v1',game_id:'known'}}
  const values=await Promise.all(Array.from({length:100},()=>enrichSelectedGame('Test deduplicated',{send,sleep:async()=>{},notify:()=>notifications++})))
  assert.equal(posts,1);assert.equal(gets,1);assert.equal(notifications,1);assert.ok(values.every(v=>v.version==='v1'))
  await enrichSelectedGame('Test deduplicated',{send})
  assert.equal(posts,1);assert.equal(gets,1)
})

test('missing recommended is negative cached without polling',async()=>{
  let calls=0
  const send=async()=>{calls++;return {status:'no_recommended',version:'minimum-only'}}
  await enrichSelectedGame('Test no recommended',{send,sleep:()=>assert.fail('must not poll')})
  await enrichSelectedGame('Test no recommended',{send})
  assert.equal(calls,1)
})

test('worker offline has bounded polling and returns fallback state',async()=>{
  let calls=0,sleeps=0
  const result=await enrichSelectedGame('Test offline worker',{send:async()=>{calls++;return {status:'queued',refresh_pending:true}},sleep:async()=>{sleeps++}})
  assert.equal(calls,13);assert.equal(sleeps,12);assert.equal(result.status,'queued')
})

test('HTTP failure releases in-flight state so a later selection can retry',async()=>{
  await assert.rejects(enrichSelectedGame('Test retry',{send:async()=>{throw Error('offline')}}),/offline/)
  const result=await enrichSelectedGame('Test retry',{send:async()=>({status:'local_ready'}),sleep:async()=>{}})
  assert.equal(result.status,'local_ready')
})
