import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../src/api/uploads.js', import.meta.url), 'utf8')
let nextId = 0
async function loadApi(t, { policyError, ossError } = {}) {
  const requests = []
  globalThis.__uploadPolicyTest = { async post(...args) {
    requests.push(['policy', ...args])
    if (policyError) throw policyError
    return { data: { host: 'https://example.invalid/upload', key: 'test/image.gif', policy: 'test',
      oss_access_key_id: 'test', signature: 'test', success_action_status: '200', public_url: 'https://example.invalid/image.gif' } }
  } }
  globalThis.__uploadOssTest = { async post(...args) {
    requests.push(['oss', ...args])
    if (ossError) throw ossError
    return { status: 200 }
  } }
  t.after(() => { delete globalThis.__uploadPolicyTest; delete globalThis.__uploadOssTest })
  const code = source
    .replace("import axios from 'axios'", 'const axios = globalThis.__uploadOssTest')
    .replace("import api from './index'", 'const api = globalThis.__uploadPolicyTest')
    .replace("'@/utils/imageUpload'", JSON.stringify(new URL('../src/utils/imageUpload.js', import.meta.url).href))
  const module = await import(`data:text/javascript;base64,${Buffer.from(code + `\n// ${nextId++}`).toString('base64')}`)
  return { ...module, requests }
}

test('upload reports each stage, preserves OSS policy fields and bounds both requests', async (t) => {
  const { uploadImageToOss, requests } = await loadApi(t)
  const stages = []
  const file = new File(['GIF89a'], 'photo.gif', { type: 'image/gif' })
  const url = await uploadImageToOss({ kind: 'part', entityId: 12, file, onStage: (stage) => stages.push(stage) })
  assert.equal(url, 'https://example.invalid/image.gif')
  assert.deepEqual(stages, ['正在读取并处理图片…', '正在准备上传…', '正在上传图片…'])
  assert.equal(requests.length, 2)
  assert.deepEqual(requests[0].slice(1), ['/uploads/policy', {
    kind: 'part', filename: 'photo.gif', content_type: 'image/gif', entity_id: '12',
  }, { timeout: 30000, _silentError: true }])
  assert.equal(requests[1][1], 'https://example.invalid/upload')
  const form = requests[1][2]
  assert.equal(form.get('file'), file)
  assert.equal(form.get('Content-Type'), 'image/gif')
  assert.equal(form.get('key'), 'test/image.gif')
  assert.equal(form.get('Signature'), 'test')
  assert.deepEqual(requests[1][3], { timeout: 120000 })
})

test('policy and OSS timeouts surface a clear retryable error rather than hanging forever', async (t) => {
  for (const stage of ['policyError', 'ossError']) {
    await t.test(stage, async (t) => {
      const { uploadImageToOss, requests } = await loadApi(t, { [stage]: Object.assign(new Error('timeout'), { code: 'ECONNABORTED' }) })
      await assert.rejects(uploadImageToOss({ kind: 'part', file: new File(['GIF89a'], 'photo.gif', { type: 'image/gif' }) }), /图片上传超时.*重新选择图片重试/)
      assert.equal(requests.length, stage === 'policyError' ? 1 : 2)
    })
  }
})

test('other upload failures remain available to the dialog for detailed feedback', async (t) => {
  const failure = Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' })
  const { uploadImageToOss } = await loadApi(t, { ossError: failure })
  await assert.rejects(uploadImageToOss({ kind: 'part', file: new File(['GIF89a'], 'photo.gif', { type: 'image/gif' }) }), (error) => error === failure)
})
