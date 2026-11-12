import test from 'node:test'
import assert from 'node:assert/strict'
import {publicSourceIds,PUBLIC_SOURCES} from './publicSources.js'
test('public source catalogue contains exactly the two enabled sources',()=>assert.deepEqual(PUBLIC_SOURCES.map(([id])=>id),['regard','upgradelab']))
test('legacy null cannot silently enable archive prices',()=>assert.deepEqual(publicSourceIds(null),['regard','upgradelab']))
test('legacy saved and hot-reload source arrays cannot re-enable hidden shops',()=>assert.deepEqual(publicSourceIds(['avito','dns','regard','upgradelab','ozon','regard']),['regard','upgradelab']))
test('an explicit empty choice remains empty for form validation',()=>assert.deepEqual(publicSourceIds([]),[]))
test('unsupported-only choice requires an explicit new selection',()=>assert.deepEqual(publicSourceIds(['avito']),[]))
