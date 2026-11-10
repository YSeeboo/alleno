import test from 'node:test'
import assert from 'node:assert/strict'
import { compressImageForUpload } from '../src/utils/imageUpload.js'

function browser(t, { imageResult = 'load', blobResult = 'success', width = 4000, height = 3000 } = {}) {
  const images = []
  const canvases = []
  const revoked = []
  const drawings = []
  const replace = (key, value) => {
    const original = Object.getOwnPropertyDescriptor(globalThis, key)
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true })
    t.after(() => original ? Object.defineProperty(globalThis, key, original) : delete globalThis[key])
  }
  t.mock.method(URL, 'createObjectURL', () => 'blob:test-photo')
  t.mock.method(URL, 'revokeObjectURL', (url) => revoked.push(url))
  replace('Image', class {
    naturalWidth = width
    naturalHeight = height
    constructor() { images.push(this) }
    set src(value) {
      this.source = value
      if (value && imageResult !== 'hang') queueMicrotask(() => imageResult === 'load' ? this.onload?.() : this.onerror?.())
    }
  })
  replace('document', {
    createElement(tag) {
      assert.equal(tag, 'canvas')
      const canvas = {
        getContext: () => ({ fillRect() {}, drawImage: (...args) => drawings.push(args.slice(1)) }),
        toBlob(callback, type) {
          if (blobResult === 'hang') return
          if (blobResult === 'throw') throw new Error('encoder failed')
          callback(blobResult === 'empty' ? null : new Blob(['compressed'], { type }))
        },
      }
      canvases.push(canvas)
      return canvas
    },
  })
  return { images, canvases, revoked, drawings }
}

test('large camera images resize to 1600px and release decoded/canvas buffers', async (t) => {
  const state = browser(t)
  const file = new File(['camera-photo'], 'camera.jpeg', { type: 'image/jpeg' })
  const result = await compressImageForUpload(file)
  assert.equal(result.name, 'camera.jpg')
  assert.equal(result.type, 'image/jpeg')
  assert.deepEqual(state.drawings[0], [0, 0, 1600, 1200])
  assert.deepEqual(state.revoked, ['blob:test-photo'])
  assert.equal(state.images[0].source, '')
  assert.equal(state.canvases[0].width, 0)
  assert.equal(state.canvases[0].height, 0)
})

test('small photos are not enlarged or replaced by a larger encoding; GIF stays untouched', async (t) => {
  const state = browser(t, { width: 40, height: 30 })
  const file = new File(['a'], 'small.png', { type: 'image/png' })
  assert.equal(await compressImageForUpload(file), file)
  assert.deepEqual(state.drawings[0], [0, 0, 40, 30])
  const gif = new File(['gif'], 'animation.gif', { type: 'image/gif' })
  assert.equal(await compressImageForUpload(gif), gif)
  assert.equal(state.images.length, 1)
})

test('photo provider read failure and timeout report errors instead of staying silent', async (t) => {
  await t.test('read error', async (t) => {
    const state = browser(t, { imageResult: 'error' })
    await assert.rejects(compressImageForUpload(new File(['a'], 'photo.jpg', { type: 'image/jpeg' })), /图片读取失败/)
    assert.deepEqual(state.revoked, ['blob:test-photo'])
    assert.equal(state.images[0].source, '')
  })
  await t.test('stalled read', async (t) => {
    const state = browser(t, { imageResult: 'hang' })
    await assert.rejects(compressImageForUpload(new File(['a'], 'photo.jpg', { type: 'image/jpeg' }), { timeoutMs: 5 }), /图片读取超时/)
    assert.deepEqual(state.revoked, ['blob:test-photo'])
    assert.equal(state.images[0].onload, null)
  })
})

test('failed, throwing and stalled encoders all reject and release mobile image buffers', async (t) => {
  for (const [blobResult, message] of [['empty', /图片压缩失败/], ['throw', /encoder failed/], ['hang', /图片处理超时/]]) {
    await t.test(blobResult, async (t) => {
      const state = browser(t, { blobResult })
      await assert.rejects(compressImageForUpload(new File(['a'], 'photo.webp', { type: 'image/webp' }), { timeoutMs: 5 }), message)
      assert.equal(state.images[0].source, '')
      assert.equal(state.canvases[0].width, 0)
      assert.equal(state.canvases[0].height, 0)
    })
  }
})
