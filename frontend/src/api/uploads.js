import axios from 'axios'
import api from './index'

export const getUploadPolicy = (data) => api.post('/uploads/policy', data)

export async function uploadImageToOss({ kind, file, entityId }) {
  const { data } = await getUploadPolicy({
    kind,
    filename: file.name,
    content_type: file.type,
    entity_id: entityId,
  })

  const formData = new FormData()
  formData.append('key', data.key)
  formData.append('policy', data.policy)
  formData.append('OSSAccessKeyId', data.oss_access_key_id)
  formData.append('Signature', data.signature)
  formData.append('success_action_status', data.success_action_status)
  formData.append('Content-Type', file.type || 'image/jpeg')
  formData.append('file', file)

  await axios.post(data.host, formData)
  return data.public_url
}
