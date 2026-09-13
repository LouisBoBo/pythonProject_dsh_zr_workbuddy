'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')
const assert = require('assert')
const {
  stashUserFeatures,
  restoreUserFeatures,
  listFeatureIds,
} = require('../lib/persist-user-features')

function writeFeature(root, id, body) {
  const dir = path.join(root, 'apps', 'zr-workbuddy', 'features', id)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'index.js'), body || `export const name = "${id}"\n`)
  fs.writeFileSync(
    path.join(dir, 'manifest.json'),
    JSON.stringify({ id, name: id, purpose: 'test' }),
  )
}

function rmrf(dir) {
  fs.rmSync(dir, { recursive: true, force: true })
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'wb-persist-feat-'))
const live = path.join(tmp, 'live')
const bundle = path.join(tmp, 'bundle')
const persist = path.join(tmp, 'persist')

try {
  writeFeature(bundle, 'mes-ask', 'bundled')
  writeFeature(live, 'mes-ask', 'bundled')
  writeFeature(live, 'vendor-foo', 'user-installed')
  writeFeature(live, 'BadId', 'skip')

  const kept = stashUserFeatures({
    liveAppRoot: live,
    bundleAppRoot: bundle,
    persistDir: persist,
  })
  assert.deepStrictEqual(kept.sort(), ['vendor-foo'])
  assert.ok(fs.existsSync(path.join(persist, 'user-features', 'vendor-foo', 'index.js')))
  assert.ok(!fs.existsSync(path.join(persist, 'user-features', 'mes-ask')))
  assert.ok(!fs.existsSync(path.join(persist, 'user-features', 'BadId')))

  rmrf(path.join(live, 'apps', 'zr-workbuddy', 'features', 'vendor-foo'))
  const keptAfterUninstall = stashUserFeatures({
    liveAppRoot: live,
    bundleAppRoot: bundle,
    persistDir: persist,
  })
  assert.deepStrictEqual(keptAfterUninstall, [])
  assert.ok(!fs.existsSync(path.join(persist, 'user-features', 'vendor-foo')))

  writeFeature(live, 'vendor-foo', 'user-installed')
  stashUserFeatures({
    liveAppRoot: live,
    bundleAppRoot: bundle,
    persistDir: persist,
  })

  rmrf(path.join(live, 'apps', 'zr-workbuddy', 'features'))
  writeFeature(live, 'mes-ask', 'new-bundle')

  const restored = restoreUserFeatures({
    liveAppRoot: live,
    bundleAppRoot: bundle,
    persistDir: persist,
  })
  assert.deepStrictEqual(restored, ['vendor-foo'])
  assert.deepStrictEqual(listFeatureIds(path.join(live, 'apps', 'zr-workbuddy', 'features')).sort(), [
    'mes-ask',
    'vendor-foo',
  ])
  assert.ok(fs.readFileSync(path.join(live, 'apps', 'zr-workbuddy', 'features', 'vendor-foo', 'index.js'), 'utf8').includes('user-installed'))
  assert.ok(fs.readFileSync(path.join(live, 'apps', 'zr-workbuddy', 'features', 'mes-ask', 'index.js'), 'utf8').includes('new-bundle'))

  writeFeature(bundle, 'vendor-foo', 'now-shipped')
  const restored2 = restoreUserFeatures({
    liveAppRoot: live,
    bundleAppRoot: bundle,
    persistDir: persist,
  })
  assert.deepStrictEqual(restored2, [])
  assert.ok(!fs.existsSync(path.join(persist, 'user-features', 'vendor-foo')))

  const persist2 = path.join(tmp, 'persist2')
  const live2 = path.join(tmp, 'live2')
  const bundle2 = path.join(tmp, 'bundle2')
  writeFeature(bundle2, 'mes-ask', 'bundled')
  writeFeature(live2, 'mes-ask', 'bundled')
  writeFeature(live2, 'ok-feat', 'ok')
  const secret = path.join(tmp, 'secret-outside')
  fs.mkdirSync(secret)
  fs.writeFileSync(path.join(secret, 'index.js'), 'LEAK')
  const featRoot2 = path.join(live2, 'apps', 'zr-workbuddy', 'features')
  fs.symlinkSync(secret, path.join(featRoot2, 'evil-link'))
  fs.symlinkSync(secret, path.join(featRoot2, 'ok-feat', 'nested-link'))
  const keptNoLeak = stashUserFeatures({
    liveAppRoot: live2,
    bundleAppRoot: bundle2,
    persistDir: persist2,
  })
  assert.ok(keptNoLeak.includes('ok-feat'))
  assert.ok(!keptNoLeak.includes('evil-link'))
  assert.ok(!fs.existsSync(path.join(persist2, 'user-features', 'evil-link')))
  assert.ok(!fs.existsSync(path.join(persist2, 'user-features', 'ok-feat', 'nested-link')))

  writeFeature(live2, 'too-big', 'x')
  fs.writeFileSync(path.join(featRoot2, 'too-big', 'blob.bin'), Buffer.alloc(100))
  const persist3 = path.join(tmp, 'persist3')
  const keptTiny = stashUserFeatures({
    liveAppRoot: live2,
    bundleAppRoot: bundle2,
    persistDir: persist3,
    maxBytes: 20,
  })
  assert.ok(!keptTiny.includes('too-big'))

  console.log('ok: desktop persist user features')
} finally {
  rmrf(tmp)
}
