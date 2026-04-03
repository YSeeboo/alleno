import axios from 'axios'
import api from './index'

export const getUploadPolicy = (data) => api.post('/uploads/policy', data)

const MAX_UPLOAD_DIMENSION = 1600
const JPEG_QUALITY = 0.75
const WEBP_QUALITY = 0.75

const loadImageFromFile = (file) => new Promise((resolve, reject) => {
  const objectUrl = URL.createObjectURL(file)
  const image = new Image()
  image.onload = () => {
    URL.revokeObjectURL(objectUrl)
    resolve(image)
  }
  image.onerror = () => {
    URL.revokeObjectURL(objectUrl)
    reject(new Error('图片读取失败'))
  }
  image.src = objectUrl
})

const canvasToBlob = (canvas, mimeType, quality) => new Promise((resolve, reject) => {
  canvas.toBlob((blob) => {
    if (!blob) {
      reject(new Error('图片压缩失败'))
      return
    }
    resolve(blob)
  }, mimeType, quality)
})

const normalizeUploadMimeType = (file) => {
  if (file.type === 'image/png') return 'image/png'
  if (file.type === 'image/webp') return 'image/webp'
  return 'image/jpeg'
}

const createCompressedFilename = (filename, mimeType) => {
  const baseName = (filename || 'upload').replace(/\.[^.]+$/, '')
  if (mimeType === 'image/png') return `${baseName}.png`
  if (mimeType === 'image/webp') return `${baseName}.webp`
  return `${baseName}.jpg`
}

export async function compressImageForUpload(file) {
  if (!file || !file.type?.startsWith('image/')) return file
  if (file.type === 'image/gif') return file

  const image = await loadImageFromFile(file)
  const width = image.naturalWidth || image.width
  const height = image.naturalHeight || image.height
  if (!width || !height) return file

  const scale = Math.min(1, MAX_UPLOAD_DIMENSION / Math.max(width, height))
  const targetWidth = Math.max(1, Math.round(width * scale))
  const targetHeight = Math.max(1, Math.round(height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = targetWidth
  canvas.height = targetHeight

  const context = canvas.getContext('2d')
  if (!context) return file

  const targetMimeType = normalizeUploadMimeType(file)
  if (targetMimeType === 'image/jpeg') {
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, targetWidth, targetHeight)
  }
  context.drawImage(image, 0, 0, targetWidth, targetHeight)

  const quality = targetMimeType === 'image/webp' ? WEBP_QUALITY : JPEG_QUALITY
  const compressedBlob = await canvasToBlob(canvas, targetMimeType, quality)
  if (compressedBlob.size >= file.size && scale === 1) {
    return file
  }

  return new File(
    [compressedBlob],
    createCompressedFilename(file.name, targetMimeType),
    {
      type: targetMimeType,
      lastModified: Date.now(),
    },
  )
}

export async function uploadImageToOss({ kind, file, entityId }) {
  const uploadFile = await compressImageForUpload(file)
  const { data } = await getUploadPolicy({
    kind,
    filename: uploadFile.name,
    content_type: uploadFile.type,
    entity_id: entityId != null ? String(entityId) : undefined,
  })

  const formData = new FormData()
  formData.append('key', data.key)
  formData.append('policy', data.policy)
  formData.append('OSSAccessKeyId', data.oss_access_key_id)
  formData.append('Signature', data.signature)
  formData.append('success_action_status', data.success_action_status)
  formData.append('Content-Type', uploadFile.type || 'image/jpeg')
  formData.append('file', uploadFile)

  await axios.post(data.host, formData)
  return data.public_url
}
