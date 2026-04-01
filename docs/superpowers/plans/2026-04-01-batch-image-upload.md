# 导入配件后批量补图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After part import, show a batch image upload modal for parts without images, supporting paste-to-upload.

**Architecture:** Minimal backend change (add `image` field to import response). Frontend adds a new `BatchImageUpload` modal component triggered after successful import.

**Tech Stack:** Vue 3 + Naive UI, existing `uploadImageToOss` and `PATCH /parts/{id}` APIs

**Spec:** `docs/superpowers/specs/2026-04-01-batch-image-upload-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `services/part_import.py` | Add `image` field to import results |
| `schemas/part.py` | Add `image` to `PartImportResultItem` if schema exists |
| `frontend/src/components/BatchImageUpload.vue` | New component: batch image upload modal |
| `frontend/src/views/parts/PartList.vue` | Trigger batch upload modal after import |
| `tests/test_api_parts.py` | Verify import response includes `image` field |

---

## Task 1: Backend — Add `image` to Import Response

**Files:**
- Modify: `services/part_import.py` (line ~112, results.append)
- Modify: `schemas/part.py` (if PartImportResultItem schema exists)
- Test: `tests/test_api_parts.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api_parts.py`:

```python
def test_import_response_includes_image(client, db):
    """Import response results should include image field."""
    from io import BytesIO
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["名称", "类目", "入库数量"])
    ws.append(["测试吊坠", "吊坠", 10])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = client.post(
        "/api/parts/import?filename=test.xlsx",
        content=buf.read(),
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert "image" in data["results"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_parts.py::test_import_response_includes_image -v`
Expected: FAIL (KeyError or assertion error — `image` not in result)

- [ ] **Step 3: Add `image` to import results**

In `services/part_import.py`, find the `results.append({...})` block (around line 112) and add the `image` field:

```python
results.append({
    "row_number": plan["row"].row_number,
    "part_id": part.id,
    "name": part.name,
    "image": part.image,
    "action": action,
    "stock_added": qty,
})
```

If there is a Pydantic schema for the import result items in `schemas/part.py`, add `image: str | None = None` to it.

- [ ] **Step 4: Run test**

Run: `pytest tests/test_api_parts.py::test_import_response_includes_image -v`
Expected: PASS

- [ ] **Step 5: Run all import-related tests**

Run: `pytest tests/test_api_parts.py -v -k "import"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add services/part_import.py schemas/part.py tests/test_api_parts.py
git commit -m "feat: include image field in part import response"
```

---

## Task 2: Frontend — BatchImageUpload Component

**Files:**
- Create: `frontend/src/components/BatchImageUpload.vue`

- [ ] **Step 1: Create the component**

```vue
<template>
  <n-modal
    :show="show"
    preset="card"
    title="批量上传配件图片"
    style="width: 680px; max-height: 80vh;"
    :mask-closable="false"
    @update:show="$emit('update:show', $event)"
  >
    <div style="max-height: 60vh; overflow-y: auto;">
      <n-table size="small" :bordered="false">
        <thead>
          <tr>
            <th style="width: 120px;">配件编号</th>
            <th>配件名称</th>
            <th style="width: 100px; text-align: center;">图片</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="part in parts" :key="part.part_id">
            <td>{{ part.part_id }}</td>
            <td>{{ part.name }}</td>
            <td style="text-align: center;">
              <!-- Uploaded image -->
              <div v-if="uploadedImages[part.part_id]" style="position: relative; display: inline-block;">
                <n-image
                  :src="uploadedImages[part.part_id]"
                  width="64"
                  height="64"
                  object-fit="cover"
                  style="border-radius: 4px;"
                />
                <n-button
                  circle
                  size="tiny"
                  type="error"
                  style="position: absolute; top: -6px; right: -6px;"
                  @click="removeImage(part.part_id)"
                >
                  <template #icon><n-icon :component="CloseIcon" /></template>
                </n-button>
              </div>
              <!-- Upload area -->
              <div
                v-else
                :class="['upload-area', { 'upload-focus': focusedPartId === part.part_id, 'upload-loading': uploadingPartId === part.part_id }]"
                tabindex="0"
                @click="setFocus(part.part_id)"
                @focus="setFocus(part.part_id)"
                @paste="handlePaste($event, part.part_id)"
              >
                <n-spin v-if="uploadingPartId === part.part_id" size="small" />
                <span v-else style="font-size: 11px; color: #999;">点击后粘贴</span>
              </div>
            </td>
          </tr>
        </tbody>
      </n-table>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button type="primary" @click="$emit('update:show', false)">完成</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import { Close as CloseIcon } from '@vicons/ionicons5'
import { uploadImageToOss } from '@/api/uploads'
import { updatePart } from '@/api/parts'

const props = defineProps({
  show: Boolean,
  parts: { type: Array, default: () => [] },  // [{ part_id, name }]
})

const emit = defineEmits(['update:show', 'done'])

const message = useMessage()
const uploadedImages = ref({})
const focusedPartId = ref(null)
const uploadingPartId = ref(null)

function setFocus(partId) {
  focusedPartId.value = partId
}

async function handlePaste(event, partId) {
  if (uploadingPartId.value) return
  const file = [...(event.clipboardData?.items || [])]
    .find(item => item.type?.startsWith('image/'))
    ?.getAsFile()
  if (!file) return
  event.preventDefault()

  uploadingPartId.value = partId
  try {
    const url = await uploadImageToOss({
      kind: 'part',
      file,
      entityId: partId,
    })
    await updatePart(partId, { image: url })
    uploadedImages.value[partId] = url
    message.success(`${partId} 图片上传成功`)
  } catch (err) {
    message.error(`${partId} 上传失败: ${err.message || '未知错误'}`)
  } finally {
    uploadingPartId.value = null
  }
}

async function removeImage(partId) {
  try {
    await updatePart(partId, { image: null })
    delete uploadedImages.value[partId]
  } catch (err) {
    message.error(`删除失败: ${err.message || '未知错误'}`)
  }
}
</script>

<style scoped>
.upload-area {
  width: 64px;
  height: 64px;
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s;
  outline: none;
}
.upload-area:hover {
  border-color: #1890ff;
}
.upload-focus {
  border-color: #1890ff;
  border-style: solid;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}
.upload-loading {
  border-color: #1890ff;
}
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds (component not yet used, but should compile)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BatchImageUpload.vue
git commit -m "feat: add BatchImageUpload component for paste-to-upload"
```

---

## Task 3: Frontend — Integrate into PartList Import Flow

**Files:**
- Modify: `frontend/src/views/parts/PartList.vue`

- [ ] **Step 1: Import component and add state**

In the `<script setup>` section of `PartList.vue`, add:

```javascript
import BatchImageUpload from '@/components/BatchImageUpload.vue'

const showBatchImageUpload = ref(false)
const batchImageParts = ref([])
```

- [ ] **Step 2: Modify import success flow**

Find the `doImport` function (around line 512). After the success message, replace `closeImportModal()` with:

```javascript
const { data } = await importPartsExcel(importFile.value)
message.success(`导入成功：新增 ${data.created_count} 条，更新 ${data.updated_count} 条，入库 ${data.stock_entry_count} 条`)

// Filter parts without images
const partsWithoutImage = data.results.filter(r => !r.image)
if (partsWithoutImage.length > 0) {
  const doUpload = await new Promise(resolve => {
    dialog.info({
      title: '上传图片',
      content: `有 ${partsWithoutImage.length} 个配件没有图片，是否现在上传？`,
      positiveText: '是',
      negativeText: '否',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
    })
  })
  if (doUpload) {
    batchImageParts.value = partsWithoutImage
    showBatchImageUpload.value = true
  }
}
closeImportModal()
loadAllPartsForSelect()
await load()
```

- [ ] **Step 3: Add component to template**

Add at the bottom of the `<template>` section, alongside existing modals:

```html
<BatchImageUpload
  v-model:show="showBatchImageUpload"
  :parts="batchImageParts"
  @done="load"
/>
```

- [ ] **Step 4: Also reload list when batch upload modal closes**

Add a watcher or handle the `update:show` event to reload parts when the modal closes:

```javascript
watch(showBatchImageUpload, (val) => {
  if (!val) {
    load()
  }
})
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/parts/PartList.vue
git commit -m "feat: trigger batch image upload after part import"
```

---

## Task 4: Verify + Cleanup

- [ ] **Step 1: Run backend tests**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual verification**

Start backend and frontend, import a test Excel file:
- Verify import success shows "是否上传图片" prompt
- Verify clicking "是" shows batch upload modal with correct parts
- Verify paste upload works
- Verify delete button works
- Verify "完成" closes modal and refreshes list

- [ ] **Step 4: Commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup for batch image upload feature"
```
