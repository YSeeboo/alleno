const MAX_UPLOAD_DIMENSION = 1600
const IMAGE_PROCESSING_TIMEOUT = 20000

const loadImageFromFile = (file, timeoutMs) => new Promise((resolve, reject) => {
  const objectUrl = URL.createObjectURL(file)
  const image = new Image()
  const finish = (error) => {
    clearTimeout(timer)
    image.onload = null
    image.onerror = null
    URL.revokeObjectURL(objectUrl)
    if (error) {
      image.src = ''
      reject(error)
    } else {
      resolve(image)
    }
  }
  const timer = setTimeout(() => finish(new Error('图片读取超时，请重新选择本地图片或拍照上传')), timeoutMs)
  image.onload = () => finish()
  image.onerror = () => finish(new Error('图片读取失败，请重新选择图片，或使用 JPG / PNG 格式'))
  image.src = objectUrl
})

const canvasToBlob = (canvas, mimeType, quality, timeoutMs) => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('图片处理超时，请尝试较小的图片或重新拍照')), timeoutMs)
  try {
    canvas.toBlob((blob) => {
      clearTimeout(timer)
      if (blob) resolve(blob)
      else reject(new Error('图片压缩失败，请重新选择图片'))
    }, mimeType, quality)
  } catch (error) {
    clearTimeout(timer)
    reject(error)
  }
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

export async function compressImageForUpload(file, { timeoutMs = IMAGE_PROCESSING_TIMEOUT } = {}) {
  if (!file || !file.type?.startsWith('image/')) return file
  if (file.type === 'image/gif') return file

  const image = await loadImageFromFile(file, timeoutMs)
  let canvas
  try {
    const width = image.naturalWidth || image.width
    const height = image.naturalHeight || image.height
    if (!width || !height) return file

    const scale = Math.min(1, MAX_UPLOAD_DIMENSION / Math.max(width, height))
    canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const context = canvas.getContext('2d')
    if (!context) return file

    const targetMimeType = normalizeUploadMimeType(file)
    if (targetMimeType === 'image/jpeg') {
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, canvas.width, canvas.height)
    }
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const compressedBlob = await canvasToBlob(canvas, targetMimeType, 0.75, timeoutMs)
    if (compressedBlob.size >= file.size && scale === 1) return file

    return new File([compressedBlob], createCompressedFilename(file.name, targetMimeType), {
      type: targetMimeType,
      lastModified: Date.now(),
    })
  } finally {
    // Release large camera-photo buffers between consecutive uploads on phones.
    image.src = ''
    if (canvas) canvas.width = canvas.height = 0
  }
}
