import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
const css=readFileSync(new URL('../tokens.css',import.meta.url),'utf8')
const color=name=>css.match(new RegExp('--'+name+':\\s*(#[a-f0-9]{6});','i'))[1]
const lum=hex=>{const channels=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return channels.reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0)}
const ratio=(a,b)=>{const x=lum(color(a)),y=lum(color(b));return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
test('shared text and input-boundary tokens meet contrast thresholds',()=>{for(const text of ['text-primary','text-secondary','text-muted'])assert.ok(ratio(text,'surface')>=4.5,text);assert.ok(ratio('on-accent','accent')>=4.5,'button text');assert.ok(ratio('control-border','input-surface')>=3,'input boundary')})
