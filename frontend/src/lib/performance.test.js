import test from 'node:test'
import assert from 'node:assert/strict'
import { fpsText, targetText, upgradeTargetText } from './performance.js'

test('a central prediction above 60 does not hide an uncertain 60 FPS target', () => {
  const outlook = { minimum: 45, maximum: 70 }
  assert.equal(fpsText(63, outlook), '45–70')
  assert.match(targetText(outlook, 60, true), /неопределённость/)
})

test('the whole range must clear the target before showing headroom', () => {
  assert.equal(targetText({ minimum: 60, maximum: 90 }, 60), 'Ориентир выше цели')
  assert.equal(targetText({ minimum: 30, maximum: 55 }, 60), 'Ориентир ниже цели')
})

test('saved legacy results can still be rendered without range metadata', () => {
  assert.equal(fpsText(63), '~63')
  assert.doesNotThrow(() => targetText(null, 60))
})

test('upgrade targets use the central prediction even when a range crosses the goal', () => {
  assert.match(upgradeTargetText(420,550),/не хватает 130 FPS/)
  assert.match(upgradeTargetText(550,550),/Цель достигнута/)
  assert.match(upgradeTargetText(600,550),/600 FPS/)
})
test('unknown FPS never renders null or fabricated missing performance',()=>{assert.equal(fpsText(null,null),'Нет данных');assert.equal(fpsText(undefined),'Нет данных');assert.equal(upgradeTargetText(null,60),'Недостаточно данных для FPS');assert.equal(targetText(null,60),'Диапазон не подтверждён')})
test('uncalibrated full-build estimate never confirms the FPS goal',()=>assert.match(targetText({minimum:200,maximum:300},60,null),/не подтверждена замерами/))
