import axios from 'axios'
import api from './index'
import { compressImageForUpload } from '@/utils/imageUpload'

export { compressImageForUpload }
export const getUploadPolicy = (data) => api.post('/uploads/policy', data, { timeout: 30000, _silentError: true })

export async function uploadImageToOss({ kind, file, entityId, onStage = () => {} }) {
  onStage('正在读取并处理图片…')
  const uploadFile = await compressImageForUpload(file)
  try {
    onStage('正在准备上传…')
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

    onStage('正在上传图片…')
    await axios.post(data.host, formData, { timeout: 120000 })
    return data.public_url
  } catch (error) {
    if (['ECONNABORTED', 'ETIMEDOUT'].includes(error.code)) {
      throw new Error('图片上传超时，请检查网络后重新选择图片重试')
    }
    throw error
  }
}
