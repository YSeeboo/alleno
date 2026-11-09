<template>
  <div class="plating-detail">
    <div class="page-breadcrumb">生产 / 电镀发出 / {{ order?.id || '…' }}</div>
    <header class="pd-head">
      <div class="pd-title">
        <h2 class="page-title">电镀单 {{ order?.id || '…' }}</h2>
        <n-popselect v-if="order" :value="order.status" :options="statusOptions" trigger="click" :disabled="statusOptions.length === 0" @update:value="doChangeStatus">
          <button class="pd-status" :class="`pd-status--${order.archived_at ? 'archived' : order.status}`" :disabled="statusOptions.length === 0">
            {{ order.archived_at ? '历史归档' : statusLabel[order.status] }}{{ statusOptions.length ? ' ▾' : '' }}
          </button>
        </n-popselect>
      </div>
      <n-space size="small">
        <n-button v-if="summaryReturn" text size="small" @click="backToSummary">返回汇总</n-button>
        <n-button text size="small" @click="router.back()">← 返回</n-button>
      </n-space>
    </header>

    <n-spin :show="loading">
      <template v-if="order">
        <ProductionArchiveNotice :order="order" />
        <div class="pd-stepper" aria-label="单据业务进度">
          <template v-for="(stage, index) in stages" :key="stage">
            <div v-if="index" class="pd-step-line" :class="{ 'is-done': stageIndex >= index }"></div>
            <div class="pd-step" :class="{ 'is-current': stageIndex === index, 'is-done': stageIndex > index }">
              <span class="pd-step-dot">{{ stageIndex > index ? '✓' : index + 1 }}</span>
              <div><div class="pd-step-label">{{ statusLabel[stage] }}</div><div class="pd-step-sub">{{ stepDescription(stage) }}</div></div>
            </div>
          </template>
        </div>
        <section class="pd-stats" aria-label="单据统计">
          <div class="pd-stat"><div class="pd-stat-label">发出明细</div><div class="pd-stat-value">{{ items.length }}<small>项</small></div><div class="pd-stat-note">{{ detailSummary.partCount }} 种配件 · 含同款不同色</div></div>
          <div class="pd-stat"><div class="pd-stat-label">已结清明细</div><div class="pd-stat-value is-green">{{ detailSummary.settledCount }}<small>/ {{ items.length }} 项</small></div><div class="pd-stat-note">实收 + 已确认损耗核销</div></div>
          <div class="pd-stat"><div class="pd-stat-label">{{ order.archived_at ? '历史未收明细' : isPending() ? '待发出明细' : '待收明细' }}</div><div class="pd-stat-value is-amber">{{ detailSummary.remainingCount }}<small>项</small></div><div class="pd-stat-note">{{ order.archived_at ? '不进入当前待收列表' : '逐项保留真实未收数量' }}</div></div>
          <div class="pd-stat"><div class="pd-stat-label">已确认损耗</div><div class="pd-stat-value pd-stat-loss"><template v-if="detailSummary.losses.length"><span v-for="loss in detailSummary.losses" :key="loss.unit">{{ loss.qty }}<small>{{ loss.unit }}</small></span></template><template v-else>—</template></div><div class="pd-stat-note">不同单位不混加</div></div>
          <div class="pd-stat"><div class="pd-stat-label">发出总重量</div><div class="pd-stat-value">{{ detailSummary.weightKg ?? '—' }}<small v-if="detailSummary.weightKg != null">kg</small></div><div class="pd-stat-note">{{ detailSummary.weightKg == null ? '暂无填写重量' : '按填写重量换算汇总' }}</div></div>
        </section>
        <section class="pd-meta" aria-label="基本信息">
          <div class="pd-meta-item"><div class="pd-meta-label">电镀厂</div><div class="pd-meta-value">
            <template v-if="editingSupplier && isPending()">
              <n-space align="center" size="small">
                <n-select
                  v-model:value="editingSupplierValue"
                  :options="supplierSelectOptions"
                  filterable
                  tag
                  size="small"
                  placeholder="选择或输入电镀厂"
                  :style="{ width: isMobile ? '100%' : '200px' }"
                />
                <n-button size="small" type="primary" :loading="savingSupplier" @click="saveSupplierName">确认</n-button>
                <n-button size="small" :disabled="savingSupplier" @click="editingSupplier = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ order.supplier_name }}
              <n-button v-if="isPending()" text type="primary" size="small" style="margin-left: 6px;" @click="startEditSupplier">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </div></div>
          <div class="pd-meta-item"><div class="pd-meta-label">创建时间</div><div class="pd-meta-value">
            <template v-if="editingCreatedAt && !order.archived_at">
              <n-space align="center" size="small">
                <n-date-picker
                  v-model:value="editingCreatedAtTs"
                  type="date"
                  size="small"
                  :style="{ width: isMobile ? '100%' : '160px' }"
                />
                <n-button size="small" type="primary" :loading="savingCreatedAt" @click="saveCreatedAt">确认</n-button>
                <n-button size="small" :disabled="savingCreatedAt" @click="editingCreatedAt = false">取消</n-button>
              </n-space>
            </template>
            <template v-else>
              {{ fmt(order.created_at) }}
              <n-button v-if="!order.archived_at" text type="primary" size="small" style="margin-left: 6px;" @click="startEditCreatedAt">
                <template #icon><n-icon :component="CreateOutline" /></template>
              </n-button>
            </template>
          </div></div>
          <div class="pd-meta-item"><div class="pd-meta-label">完成时间</div><div class="pd-meta-value">{{ order.completed_at ? fmt(order.completed_at) : '—' }}</div></div>
          <div class="pd-meta-item pd-meta-note">
            <div class="pd-meta-label">备注</div>
            <div class="pd-meta-value" @keydown.capture="onOrderNoteKeydown">
              <n-input
                v-if="editingOrderNote && !order.archived_at"
                ref="orderNoteInputRef"
                v-model:value="editingOrderNoteValue"
                type="textarea"
                size="small"
                :autosize="{ minRows: 1, maxRows: 5 }"
                :readonly="savingOrderNote"
                :aria-busy="savingOrderNote || undefined"
                aria-label="电镀单备注"
                placeholder="输入备注，Enter 保存，Shift+Enter 换行"
                @blur="saveOrderNote"
              />
              <button v-else-if="!order.archived_at" type="button" class="pd-note-edit" aria-label="修改电镀单备注" title="点击修改备注" @click="startEditOrderNote">
                {{ order.note || '添加备注' }}
                <n-icon :component="CreateOutline" />
              </button>
              <span v-else class="pd-note-text">{{ order.note || '—' }}</span>
            </div>
          </div>
        </section>

        <section class="pd-section" aria-labelledby="plating-items-title">
          <div class="pd-section-head">
            <div class="pd-section-title"><h3 id="plating-items-title">电镀明细</h3><span class="pd-count">{{ items.length }} 项</span></div>
            <n-space size="small" align="center">
              <span class="pd-hint">{{ order.archived_at ? '历史归档 · 明细只读' : isPending() ? '点击对应内容直接修改，回车或点击空白处保存' : '配件与数量在发出后锁定' }}</span>
              <n-button v-if="items.length > 0 && !order.archived_at" size="small" @click="openBatchLinkModal">批量关联订单</n-button>
              <n-button v-if="isPending()" type="primary" size="small" secondary @click="openAddModal">+ 添加配件</n-button>
            </n-space>
          </div>
          <n-data-table v-if="items.length" class="pd-table" :columns="itemColumns" :data="items" :bordered="false" :row-key="(r) => r.id" :scroll-x="1755" />
          <n-empty v-else description="暂无明细" style="padding: 24px;" />
          <p class="pd-table-note">实收不含损耗；未收回 = 发出 − 实收 − 已确认损耗。不同单位不合计，可直接点击对应内容修改。</p>
        </section>
        <section class="pd-section" aria-labelledby="plating-images-title">
          <div class="pd-section-head"><div class="pd-section-title"><h3 id="plating-images-title">发货图片</h3><span class="pd-count">{{ totalDeliveryImageCount }} / 10</span></div><span class="pd-hint">发货凭证与现场照片</span></div>
            <div class="delivery-images-block">
              <div v-if="pendingDeliveryImages.length > 0" class="delivery-images-warning">
                <div class="delivery-images-warning-title">
                  有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到电镀单
                </div>
                <div class="delivery-images-pending-list">
                  <div
                    v-for="image in pendingDeliveryImages"
                    :key="`pending-${image}`"
                    class="delivery-pending-item"
                  >
                    <n-image
                      :src="image"
                      alt="待保存发货图片"
                      :width="56"
                      :height="56"
                      object-fit="cover"
                      class="delivery-pending-preview"
                    />
                    <div class="delivery-pending-actions">
                      <n-button
                        size="tiny"
                        type="warning"
                        ghost
                        :loading="retryingPendingImage === image"
                        :disabled="deliveryImagesSaving || !!order.archived_at"
                        @click="retryPendingDeliveryImage(image)"
                      >
                        重试保存
                      </n-button>
                      <n-button
                        size="tiny"
                        quaternary
                        :disabled="deliveryImagesSaving || retryingPendingImage === image || !!order.archived_at"
                        @click="dropPendingDeliveryImage(image)"
                      >
                        移除记录
                      </n-button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="deliveryImages.length > 0" class="delivery-images-grid">
                <div
                  v-for="(image, index) in deliveryImages"
                  :key="`${image}-${index}`"
                  class="delivery-image-card"
                >
                  <n-image
                    :src="image"
                    alt="发货图片"
                    :width="88"
                    :height="88"
                    object-fit="cover"
                    class="delivery-image-preview"
                  />
                  <n-button
                    class="delivery-image-delete"
                    v-if="!order.archived_at"
                    size="tiny"
                    type="error"
                    circle
                    :disabled="deliveryImagesSaving"
                    @click="removeDeliveryImage(index)"
                  >
                    ×
                  </n-button>
                </div>
                <button
                  v-if="canAddDeliveryImage"
                  class="delivery-image-add"
                  :disabled="deliveryImagesSaving"
                  @click="openDeliveryImageModal"
                >
                  +
                </button>
              </div>
              <button
                v-else-if="canAddDeliveryImage"
                class="delivery-image-add"
                :disabled="deliveryImagesSaving"
                @click="openDeliveryImageModal"
              >
                +
              </button>
              <div class="delivery-images-meta">
                {{ totalDeliveryImageCount }}/10 张
                <span v-if="pendingDeliveryImages.length > 0">（待保存 {{ pendingDeliveryImages.length }} 张）</span>
              </div>
            </div>
        </section>
        <p class="pd-footer-note">{{ footerNote }}</p>
      </template>
    </n-spin>

    <floating-action-bar v-if="order" aria-label="电镀单操作">
      <floating-action-button v-if="order.status !== 'pending'" @click="showReceiptList = true">查看回收单</floating-action-button>
      <floating-action-button variant="excel" :loading="downloadingExcel" @click="doDownloadExcel">导出Excel</floating-action-button>
      <floating-action-button variant="pdf" :loading="downloadingPdf" @click="doDownloadPdf">导出PDF</floating-action-button>
      <floating-action-button v-if="isPending()" variant="primary" :loading="sending" @click="doSend">确认发出</floating-action-button>
      <floating-action-button v-else-if="order.status === 'processing' && !order.archived_at" variant="primary" :disabled="!linkableItems.length" @click="chooseReceiptItem">关联回收单</floating-action-button>
    </floating-action-bar>

    <n-modal v-model:show="showReceiptList" preset="card" title="本单关联回收单" :style="{ width: isMobile ? '95vw' : '520px' }">
      <n-empty v-if="receiptLinksError" description="回收单加载失败，请重试"><template #extra><n-button size="small" @click="loadItemReceiptLinks">重试加载</n-button></template></n-empty>
      <n-space v-else-if="linkedReceiptIds.length" vertical>
        <n-button v-for="id in linkedReceiptIds" :key="id" text type="primary" @click="router.push(`/plating-receipts/${id}`)">{{ id }} →</n-button>
      </n-space>
      <n-empty v-else description="本单暂无关联回收单" />
    </n-modal>
    <n-modal v-model:show="showReceiptItemPicker" preset="card" title="选择要关联回收单的明细" :style="{ width: isMobile ? '95vw' : '560px' }">
      <div class="pd-receipt-picker">
        <button v-for="item in linkableItems" :key="item.id" class="pd-receipt-choice" @click="selectReceiptItem(item)">
          <strong>{{ item.part_name }}</strong><span>{{ item.receive_part_name || item.part_id }}</span><span>未收回 {{ platingReceiptQuantities(item).remaining }} {{ item.unit }}</span>
        </button>
      </div>
    </n-modal>

    <!-- Add Item Modal -->
    <n-modal v-model:show="addModalVisible" preset="card" title="添加电镀明细" :style="{ width: isMobile ? '95vw' : '500px' }">
      <form @submit.prevent="doAddItem">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="发出配件">
          <n-select
            v-model:value="addForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择发出配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item v-if="addForm.part_id" label="电镀颜色">
          <div>
            <n-space size="small" style="margin-bottom: 6px;">
              <span
                v-for="cv in commonColors"
                :key="cv.code"
                :style="{
                  display: 'inline-block',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: addFormColor === cv.code ? '#fff' : badgeOf[cv.code],
                  background: addFormColor === cv.code ? badgeOf[cv.code] : '#f5f5f5',
                  padding: '2px 10px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  border: `1px solid ${badgeOf[cv.code]}`,
                }"
                @click="toggleAddColor(cv.code)"
              >{{ cv.code }}</span>
              <span
                v-if="moreColors.length"
                :style="{
                  display: 'inline-block',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: '#666',
                  background: '#f5f5f5',
                  padding: '2px 10px',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  border: '1px dashed #aaa',
                }"
                @click="addColorShowMore = !addColorShowMore"
              >更多 {{ addColorShowMore ? '▴' : '▾' }}</span>
              <template v-if="addColorShowMore">
                <span
                  v-for="cv in moreColors"
                  :key="cv.code"
                  :style="{
                    display: 'inline-block',
                    fontSize: '11px',
                    fontWeight: 'bold',
                    color: addFormColor === cv.code ? '#fff' : badgeOf[cv.code],
                    background: addFormColor === cv.code ? badgeOf[cv.code] : '#f5f5f5',
                    padding: '2px 10px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    border: `1px solid ${badgeOf[cv.code]}`,
                  }"
                  @click="toggleAddColor(cv.code)"
                >{{ cv.code }}</span>
              </template>
            </n-space>
            <div v-if="addFormColor && addVariantInfo" style="font-size: 13px; color: #333;">
              <template v-if="addVariantInfo.part">
                <span>对应配件：{{ addVariantInfo.part.name }} ({{ addVariantInfo.part.id }})</span>
              </template>
              <template v-else-if="addVariantInfo.suggested_name">
                <span style="color: #999;">对应配件：{{ addVariantInfo.suggested_name }}</span>
                <n-button
                  size="tiny"
                  type="primary"
                  style="margin-left: 8px;"
                  :loading="addCreatingVariant"
                  @click="doCreateVariantInAdd"
                >新建</n-button>
              </template>
            </div>
            <div v-if="addFormColor && addVariantLoading" style="font-size: 13px; color: #999;">查询中...</div>
          </div>
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number v-model:value="addForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="重量">
          <div style="display: flex; gap: 8px; width: 100%;">
            <n-input-number
              v-model:value="addForm.weight"
              :min="0"
              :precision="2"
              :step="0.1"
              placeholder="可选"
              clearable
              style="flex: 1;"
            />
            <n-select
              v-model:value="addForm.weight_unit"
              :options="weightUnitOptions"
              style="width: 90px;"
            />
          </div>
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addSubmitting" @click="doAddItem">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>


    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="plating"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Single Link Modal: select order → select matching todo item → confirm -->
    <n-modal v-model:show="linkModalVisible" preset="card" title="关联订单" :style="{ width: isMobile ? '95vw' : '600px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="linkForm.orderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
            @update:value="onLinkOrderSelect"
          />
        </n-form-item>
        <n-form-item v-if="linkTodoItems.length > 0" label="匹配配件">
          <n-radio-group v-model:value="linkForm.todoItemId">
            <n-space vertical>
              <n-radio v-for="t in linkTodoItems" :key="t.id" :value="t.id">
                {{ t.part_name || t.part_id }} — 需要 {{ t.required_qty }}
              </n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
        <div v-if="linkForm.orderId && linkTodoItems.length === 0 && !linkTodoLoading" style="color: #999; padding: 8px 0;">
          该订单配件清单中没有匹配的配件
        </div>
        <n-spin v-if="linkTodoLoading" size="small" />
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="linkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="linkSubmitting" :disabled="!linkForm.todoItemId" @click="doCreateLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Batch Link Modal: select order → auto-match by part_id -->
    <n-modal v-model:show="batchLinkModalVisible" preset="card" title="批量关联订单" :style="{ width: isMobile ? '95vw' : '500px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="batchLinkOrderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
          />
        </n-form-item>
        <div style="color: #666; font-size: 13px; padding: 4px 0;">
          将自动按配件编号匹配该订单配件清单中的行，所有明细项都会参与匹配
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="batchLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="batchLinkSubmitting" :disabled="!batchLinkOrderId" @click="doBatchLink">确认批量关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Receipt Link Modal -->
    <n-modal v-model:show="receiptLinkModalVisible" preset="card" title="关联电镀回收单" :style="{ width: isMobile ? '95vw' : '520px' }">
      <div style="background: #f8f9fa; border-radius: 6px; padding: 12px; margin-bottom: 16px; font-size: 13px;">
        <div style="color: #999; font-size: 11px; margin-bottom: 4px;">当前配件</div>
        <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px;">
          <span><strong>{{ receiptLinkItemInfo?.part_id }}</strong> {{ receiptLinkItemInfo?.part_name }}</span>
          <span style="color: #666;">
            发出 {{ receiptLinkItemInfo?.qty }} · 实收 {{ receiptLinkItemInfo?.actual }} · 损耗 {{ receiptLinkItemInfo?.loss }} ·
            <strong style="color: #e67e22;">剩余 {{ receiptLinkItemInfo?.remaining }}</strong>
          </span>
        </div>
        <div v-if="receiptLinkItemInfo?.receive_part_name" style="font-size: 12px; color: #666; margin-top: 4px;">
          收回配件：{{ receiptLinkItemInfo.receive_part_name }}
        </div>
      </div>
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="选择回收单">
          <n-spin :show="receiptLinkLoading" style="width: 100%;">
            <div v-if="receiptLinkOptions.length === 0 && !receiptLinkLoading" style="color: #999; font-size: 13px; padding: 8px 0;">
              暂无可用的回收单（需同供应商、未付款）
            </div>
            <n-radio-group v-else v-model:value="receiptLinkForm.receiptId" style="width: 100%;">
              <div style="display: flex; flex-direction: column; gap: 6px;">
                <n-radio v-for="r in receiptLinkOptions" :key="r.id" :value="r.id" style="padding: 6px 0;">
                  <span style="font-weight: 500;">{{ r.id }}</span>
                  <span style="font-size: 12px; color: #888; margin-left: 8px;">
                    {{ r.vendor_name }} · {{ r.created_at?.slice(0, 10) }} · {{ r.item_count }} 项
                  </span>
                </n-radio>
              </div>
            </n-radio-group>
          </n-spin>
        </n-form-item>
        <n-form-item label="回收数量">
          <n-input-number
            v-model:value="receiptLinkForm.qty"
            :min="0.0001"
            :max="receiptLinkItemInfo?.remaining || 0"
            :precision="4"
            placeholder="回收数量"
            style="width: 100%;"
          />
          <span style="font-size: 11px; color: #999; margin-left: 8px; white-space: nowrap;">
            最多 {{ receiptLinkItemInfo?.remaining }}
          </span>
        </n-form-item>
        <n-form-item label="回收单价">
          <n-input-number
            v-model:value="receiptLinkForm.price"
            :min="0"
            :precision="7"
            placeholder="元"
            style="width: 100%;"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="receiptLinkModalVisible = false">取消</n-button>
          <n-button
            type="primary"
            :loading="receiptLinkSubmitting"
            :disabled="receiptLinkOptions.length === 0"
            @click="doLinkReceipt"
          >
            确认关联
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Confirm Loss Modal -->
    <n-modal v-model:show="showLossModal" preset="card" title="确认损耗" :style="{ width: isMobile ? '95vw' : '420px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="差额信息">
          <span v-if="lossTarget">实收 {{ platingReceiptQuantities(lossTarget).actual }} · 已确认损耗 {{ platingReceiptQuantities(lossTarget).loss }} / 发出 {{ lossTarget.qty }}，未收回 {{ platingReceiptQuantities(lossTarget).remaining }}</span>
        </n-form-item>
        <n-form-item label="损耗数量">
          <n-input-number v-model:value="lossForm.loss_qty" :min="0.01" :max="lossTarget ? lossTarget.qty - (lossTarget.received_qty || 0) : 0" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="扣款金额">
          <n-input-number v-model:value="lossForm.deduct_amount" :min="0" placeholder="不扣款留空" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="原因">
          <n-input v-model:value="lossForm.reason" placeholder="如：品质不良、加工损坏" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="lossForm.note" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showLossModal = false">取消</n-button>
          <n-button type="warning" :loading="lossSubmitting" @click="doConfirmLoss">确认损耗</n-button>
        </n-space>
      </template>
    </n-modal>

  </div>
</template>

<script setup>
import ProductionArchiveNotice from '@/components/ProductionArchiveNotice.vue'
import FloatingActionBar from '@/components/FloatingActionBar.vue'
import FloatingActionButton from '@/components/FloatingActionButton.vue'
import { platingReceiptQuantities, summarizePlatingDetail, canLinkPlatingReceipt } from '@/utils/platingDetail'
import { ref, computed, onMounted, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { useSummaryReturn } from '@/composables/useSummaryReturn'
import { useSendWithStockSupplement } from '@/composables/useSendWithStockSupplement'
import {
  NSpin, NDataTable,
  NSpace, NButton, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage,
  NRadioGroup, NRadio, NDatePicker,
} from 'naive-ui'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getPlating, getPlatingItems, sendPlating, supplementAndSendPlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem,
  updatePlatingDeliveryImages, updatePlatingOrder,
  downloadPlatingExcel, downloadPlatingPdf,
  getPlatingAllItemOrders, deletePlatingItemOrderLink,
  getPlatingReceiptLinks, getAvailableReceipts, linkPlatingItemToReceipt,
} from '@/api/plating'
import { deletePlatingReceiptItem } from '@/api/platingReceipts'
import { confirmPlatingLoss } from '@/api/productionLoss'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { changeOrderStatus } from '@/api/kanban'
import { listParts, findOrCreateVariant, createPartVariant, getColorVariants } from '@/api/parts'
import { listOrders, getTodo, createLink, batchLink } from '@/api/orders'
import { renderImageThumb, renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()
const { returnQuery: summaryReturn, back: backToSummary } = useSummaryReturn()

const loading = ref(true)
const downloadingExcel = ref(false)
const downloadingPdf = ref(false)
const order = ref(null)
const items = ref([])
const stages = ['pending', 'processing', 'completed']
const stageIndex = computed(() => Math.max(0, stages.indexOf(order.value?.status)))
const detailSummary = computed(() => summarizePlatingDetail(items.value))
const showReceiptList = ref(false)
const showReceiptItemPicker = ref(false)
const linkedReceiptIds = computed(() => [...new Set(Object.values(itemReceiptLinks.value).flat().map((link) => link.receipt_id))])
const linkableItems = computed(() => items.value.filter((item) => canLinkPlatingReceipt(order.value, item)))
const footerNote = computed(() => {
  if (order.value?.archived_at) return '历史单据仅供查阅，未收数量保持原值，归档不代表完成。'
  if (isPending()) return '确认发出后将扣减库存，配件及发出数量将锁定。'
  if (order.value?.status === 'completed') return '本单已核销完成；完成不等于全部实收，损耗单独保留。'
  return `还有 ${detailSummary.value.remainingCount} 项明细待收回，实收与损耗独立记录。`
})
const stepDescription = (stage) => {
  if (stage === 'pending') return order.value?.created_at ? `${new Date(order.value.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} 创建` : '已创建'
  if (stage === 'processing') return stageIndex.value === 0 ? '等待确认发出' : order.value?.archived_at ? `原状态：${statusLabel[order.value.status]}` : '已发出，等待回收'
  return order.value?.completed_at ? fmt(order.value.completed_at) : order.value?.archived_at ? '归档不代表完成' : '待实收及损耗核销'
}
const chooseReceiptItem = () => {
  if (linkableItems.value.length === 1) return openReceiptLinkModal(linkableItems.value[0])
  showReceiptItemPicker.value = true
}
const selectReceiptItem = (item) => {
  showReceiptItemPicker.value = false
  openReceiptLinkModal(item)
}
const partMap = ref({})
const partOptions = ref([])
const allParts = ref([])
const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

// Confirm loss modal
const showLossModal = ref(false)
const lossTarget = ref(null)
const lossForm = ref({ loss_qty: 0, deduct_amount: null, reason: '', note: '' })
const lossSubmitting = ref(false)

const openLossModal = (item) => {
  lossTarget.value = item
  const gap = item.qty - (item.received_qty || 0)
  lossForm.value = { loss_qty: gap, deduct_amount: null, reason: '', note: '' }
  showLossModal.value = true
}

const doConfirmLoss = async () => {
  lossSubmitting.value = true
  try {
    const payload = { ...lossForm.value }
    if (!payload.deduct_amount) payload.deduct_amount = null
    if (!payload.reason) payload.reason = null
    if (!payload.note) payload.note = null
    await confirmPlatingLoss(route.params.id, lossTarget.value.id, payload)
    showLossModal.value = false
    message.success('损耗已确认')
    await loadData()
  } catch (err) {
    // error handled by interceptor
  } finally {
    lossSubmitting.value = false
  }
}

const editingSupplier = ref(false)
const editingSupplierValue = ref('')
const savingSupplier = ref(false)
const supplierSelectOptions = ref([])

const editingCreatedAt = ref(false)
const editingCreatedAtTs = ref(null)
const savingCreatedAt = ref(false)

const editingOrderNote = ref(false)
const editingOrderNoteValue = ref('')
const savingOrderNote = ref(false)
const orderNoteInputRef = ref(null)

const startEditOrderNote = () => {
  if (!order.value || order.value.archived_at || savingOrderNote.value) return
  editingOrderNoteValue.value = order.value.note || ''
  editingOrderNote.value = true
  nextTick(() => orderNoteInputRef.value?.focus())
}

const saveOrderNote = async () => {
  if (!editingOrderNote.value || savingOrderNote.value || !order.value || order.value.archived_at) return
  const note = editingOrderNoteValue.value.trim()
  if (note === (order.value.note || '').trim()) {
    editingOrderNote.value = false
    return
  }
  savingOrderNote.value = true
  try {
    const { data } = await updatePlatingOrder(route.params.id, { note: note || null })
    order.value.note = data.note
    editingOrderNote.value = false
    message.success(note ? '备注已保存' : '备注已清空')
  } catch (e) {
    message.error(e.response?.data?.detail || '备注保存失败，请重试')
  } finally {
    savingOrderNote.value = false
  }
}

const onOrderNoteKeydown = (event) => {
  if (!editingOrderNote.value || savingOrderNote.value || event.isComposing || event.keyCode === 229) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    editingOrderNote.value = false
  } else if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    event.stopPropagation()
    void saveOrderNote()
  }
}

const startEditCreatedAt = () => {
  editingCreatedAtTs.value = isoToTs(order.value?.created_at)
  editingCreatedAt.value = true
}

const saveCreatedAt = async () => {
  const dateStr = tsToDateStr(editingCreatedAtTs.value)
  if (!dateStr) { message.warning('请选择日期'); return }
  savingCreatedAt.value = true
  try {
    await updatePlatingOrder(route.params.id, { created_at: dateStr })
    await loadData()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

const loadSupplierOptions = async () => {
  try {
    const { data } = await listSuppliers({ type: 'plating' })
    supplierSelectOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
  } catch (_) {}
}

const startEditSupplier = () => {
  editingSupplierValue.value = order.value?.supplier_name || ''
  editingSupplier.value = true
  loadSupplierOptions()
}

const saveSupplierName = async () => {
  const trimmed = (editingSupplierValue.value || '').trim()
  if (!trimmed) { message.warning('电镀厂名称不能为空'); return }
  if (trimmed === order.value?.supplier_name) { editingSupplier.value = false; return }
  savingSupplier.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !supplierSelectOptions.value.some((o) => o.value === trimmed)
    if (isNew) {
      try { await createSupplier({ name: trimmed, type: 'plating' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    await updatePlatingOrder(route.params.id, { supplier_name: trimmed })
    await loadData()
    message.success('电镀厂名称已更新')
    editingSupplier.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingSupplier.value = false
  }
}

const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const deliveryImages = computed(() => order.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => !order.value?.archived_at && totalDeliveryImageCount.value < 10)
const statusOptions = computed(() => {
  if (!order.value || order.value.archived_at) return []
  const s = order.value.status
  if (s === 'pending') return [{ label: '进行中', value: 'processing' }]
  if (s === 'processing') return [
    { label: '待发出', value: 'pending' },
  ]
  if (s === 'completed') return [{ label: '进行中', value: 'processing' }]
  return []
})
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '包', value: '包' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const weightUnitOptions = [
  { label: 'kg', value: 'kg' },
  { label: 'g', value: 'g' },
]

const colorVariantList = ref([])
let addVariantRequestSeq = 0

const badgeOf      = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.code, c.badge])))
const methodOf     = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.code, c.method])))
const codeOfMethod = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.method, c.code])))
const codeOfLabel  = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.label, c.code])))
const codeOfSuffix = computed(() => Object.fromEntries(colorVariantList.value.map(c => ['_' + c.label, c.code])))
const commonColors = computed(() => colorVariantList.value.filter(c => c.common))
const moreColors   = computed(() => colorVariantList.value.filter(c => !c.common))
const expandedColorRows = ref(new Set())
function toggleColorRow(id) { const s = new Set(expandedColorRows.value); s.has(id) ? s.delete(id) : s.add(id); expandedColorRows.value = s }
const addColorShowMore = ref(false)

const getPartColorCode = (part) => {
  if (!part) return null
  if (part.color && codeOfLabel.value[part.color]) return codeOfLabel.value[part.color]
  for (const [suffix, code] of Object.entries(codeOfSuffix.value)) {
    if (part.name?.endsWith(suffix)) return code
  }
  return null
}

const getColorBadge = (partName) => {
  if (!partName) return null
  for (const [suffix, code] of Object.entries(codeOfSuffix.value)) {
    if (partName.endsWith(suffix)) return code
  }
  return null
}

// Inline editing
const inlineEditing = ref({}) // key: `${row.id}_${field}`, value: current editing value
const inlineSaving = ref({})
const inlineInputs = new Map()

const inlineKey = (rowId, field) => `${rowId}_${field}`

const startInline = (row, field) => {
  if (!isPending()) return
  inlineEditing.value[inlineKey(row.id, field)] = row[field] ?? null
  nextTick(() => inlineInputs.get(inlineKey(row.id, field))?.focus())
}

const cancelInline = (rowId, field) => {
  delete inlineEditing.value[inlineKey(rowId, field)]
}

const saveInline = async (row, field, value) => {
  if (!isPending()) return
  const key = inlineKey(row.id, field)
  if (inlineSaving.value[key]) return
  const oldValue = row[field] ?? null
  if (value === oldValue) { cancelInline(row.id, field); return }
  inlineSaving.value[key] = true
  try {
    const body = { [field]: value }
    // Changing part_id invalidates receive_part_id — clear it
    if (field === 'part_id') {
      body.receive_part_id = null
    }
    await updatePlatingItem(route.params.id, row.id, body)
    await loadData()
    message.success('已保存')
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    delete inlineSaving.value[key]
    cancelInline(row.id, field)
  }
}

const renderInlineSelect = (row, field, options, { renderLabel, placeholder } = {}) => {
  const key = inlineKey(row.id, field)
  const isEditing = key in inlineEditing.value
  if (!isEditing) return null // caller handles display
  return h(NSelect, {
    ref: (input) => { if (input) inlineInputs.set(key, input); else inlineInputs.delete(key) },
    value: inlineEditing.value[key],
    options,
    filterable: true,
    clearable: field === 'receive_part_id',
    placeholder: placeholder || '请选择',
    size: 'small',
    style: 'min-width: 0; width: 100%;',
    defaultExpanded: true,
    renderLabel: renderLabel || undefined,
    'onUpdate:value': (v) => { saveInline(row, field, v) },
    onBlur: () => { cancelInline(row.id, field) },
  })
}

// Add Item Modal
const addModalVisible = ref(false)
const addSubmitting = ref(false)
const addForm = ref({ part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', weight: null, weight_unit: 'kg', note: '' })
const addFormColor = ref(null)
const addVariantInfo = ref(null)
const addVariantLoading = ref(false)
const addCreatingVariant = ref(false)

const editingNoteItemId = ref(null)
const editingNoteValue = ref('')
const savingNoteItemId = ref(null)
const noteInputRef = ref(null)

const loadData = async () => {
  const id = route.params.id
  const [oRes, iRes] = await Promise.all([getPlating(id), getPlatingItems(id)])
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
    receive_part_name: i.receive_part_id ? (partMap.value[i.receive_part_id]?.name || i.receive_part_id) : null,
  }))
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !deliveryImages.value.includes(image))
  if (!isPending()) {
    stopEditNote()
  }
}

const { sending, doSend } = useSendWithStockSupplement({
  orderId: computed(() => route.params.id),
  sendApi: sendPlating,
  supplementApi: supplementAndSendPlating,
  onSuccess: loadData,
  message,
  dialog,
})

const doDownloadExcel = async () => {
  await downloadExportFile('xlsx', downloadingExcel, downloadPlatingExcel, 'Excel 下载失败')
}

const doDownloadPdf = async () => {
  await downloadExportFile('pdf', downloadingPdf, downloadPlatingPdf, 'PDF 下载失败')
}

const downloadExportFile = async (extension, loadingRef, request, errorText) => {
  if (!order.value || loadingRef.value) return
  loadingRef.value = true
  try {
    const { data, headers } = await request(order.value.id)
    const url = window.URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = buildExportFilename(order.value, extension)
      || extractDownloadFilename(headers?.['content-disposition'])
      || `发出_${order.value.id}.${extension}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (_) {
    message.error(errorText)
  } finally {
    loadingRef.value = false
  }
}

const extractDownloadFilename = (contentDisposition) => {
  if (!contentDisposition) return ''
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i)
  return plainMatch?.[1] || ''
}

const buildExportFilename = (currentOrder, extension) => {
  if (!currentOrder) return ''
  const supplierName = sanitizeFilenamePart(currentOrder.supplier_name) || '未命名电镀厂'
  const shortDate = formatShortDate(currentOrder.created_at)
  return `发出_${supplierName}_${shortDate}.${extension}`
}

const sanitizeFilenamePart = (value) => {
  if (!value) return ''
  return String(value)
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[. ]+$/g, '')
}

const formatShortDate = (value) => {
  if (!value) return '000000'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '000000'
  const year = String(date.getFullYear() % 100).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

const doChangeStatus = (newStatus) => {
  const currentLabel = statusLabel[order.value?.status] || order.value?.status
  const newLabel = statusLabel[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${order.value?.supplier_name}」的订单「${order.value?.id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      const loadingMsg = message.loading('正在更新状态...', { duration: 0 })
      try {
        await changeOrderStatus({ order_id: order.value.id, order_type: 'plating', new_status: newStatus })
        loadingMsg.destroy()
        message.success(`状态已更新为${newLabel}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        // errors shown by axios interceptor
        await loadData()
      }
    },
  })
}

const openAddModal = () => {
  addForm.value = { part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', weight: null, weight_unit: 'kg', note: '' }
  addFormColor.value = null
  addVariantInfo.value = null
  addVariantLoading.value = false
  addCreatingVariant.value = false
  addModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  addForm.value.unit = found?.unit || '个'
  addForm.value.receive_part_id = null
  addFormColor.value = null
  addVariantInfo.value = null
  addVariantLoading.value = false
  ++addVariantRequestSeq
  if (val) {
    const part = allParts.value.find((p) => p.id === val)
    const existingCode = getPartColorCode(part)
    // Default: use existing color if variant, otherwise G
    toggleAddColor(existingCode || 'G')
  }
}

const toggleAddColor = async (code) => {
  if (addFormColor.value === code) {
    addFormColor.value = null
    addVariantInfo.value = null
    addForm.value.receive_part_id = null
    addForm.value.plating_method = '金'
    return
  }
  addFormColor.value = code
  addForm.value.plating_method = methodOf.value[code] || '金'
  addForm.value.receive_part_id = null
  addVariantInfo.value = null
  addVariantLoading.value = true
  const seq = ++addVariantRequestSeq
  try {
    const { data } = await findOrCreateVariant(addForm.value.part_id, { color_code: code })
    if (addFormColor.value !== code || addVariantRequestSeq !== seq) return // stale
    addVariantInfo.value = data
    addForm.value.receive_part_id = data.part?.id || null
  } catch (e) {
    if (addFormColor.value === code && addVariantRequestSeq === seq) {
      message.error(e.response?.data?.detail || '查询变体失败')
    }
  } finally {
    if (addFormColor.value === code && addVariantRequestSeq === seq) {
      addVariantLoading.value = false
    }
  }
}

const doCreateVariantInAdd = () => {
  const suggestedName = addVariantInfo.value?.suggested_name
  dialog.info({
    title: '确认新建',
    content: `当前没有 ${suggestedName}，确定新建吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      addCreatingVariant.value = true
      try {
        const { data: newPart } = await createPartVariant(addForm.value.part_id, { color_code: addFormColor.value })
        addForm.value.receive_part_id = newPart.id
        addVariantInfo.value = { part: newPart, created: true }
        // Refresh parts list
        const { data: parts } = await listParts()
        allParts.value = parts
        parts.forEach((p) => { partMap.value[p.id] = p })
        partOptions.value = parts.map((p) => ({
          label: `${p.id} ${p.name}`,
          value: p.id,
          code: p.id,
          name: p.name,
          image: p.image,
          unit: p.unit,
        }))
        message.success('变体创建成功')
      } catch (e) {
        message.error(e.response?.data?.detail || '创建变体失败')
      } finally {
        addCreatingVariant.value = false
      }
    },
  })
}

const inlineColorSeq = ref({}) // key: row.id, value: request sequence number

const toggleInlineColor = async (row, code) => {
  const currentBadge = getColorBadge(row.receive_part_name) || codeOfMethod.value[row.plating_method] || null
  if (currentBadge === code) {
    // Deselect: clear receive_part_id
    try {
      await updatePlatingItem(route.params.id, row.id, { receive_part_id: null, plating_method: null })
      await loadData()
    } catch (e) {
      message.error(e.response?.data?.detail || '更新失败')
    }
    return
  }
  // Find or create variant with stale-response protection
  const seq = (inlineColorSeq.value[row.id] || 0) + 1
  inlineColorSeq.value[row.id] = seq
  const isStale = () => inlineColorSeq.value[row.id] !== seq
  try {
    const { data } = await findOrCreateVariant(row.part_id, { color_code: code })
    if (isStale()) return
    if (data.part) {
      // Variant exists, update directly
      await updatePlatingItem(route.params.id, row.id, {
        receive_part_id: data.part.id,
        plating_method: methodOf.value[code] || '金',
      })
      if (!isStale()) await loadData()
    } else {
      if (isStale()) return
      // Variant doesn't exist, confirm creation
      dialog.info({
        title: '确认新建',
        content: `当前没有 ${data.suggested_name}，确定新建吗？`,
        positiveText: '确认',
        negativeText: '取消',
        onPositiveClick: async () => {
          if (isStale()) return
          try {
            const { data: newPart } = await createPartVariant(row.part_id, { color_code: code })
            await updatePlatingItem(route.params.id, row.id, {
              receive_part_id: newPart.id,
              plating_method: methodOf.value[code] || '金',
            })
            // Refresh parts list and table
            const { data: parts } = await listParts()
            allParts.value = parts
            parts.forEach((p) => { partMap.value[p.id] = p })
            partOptions.value = parts.map((p) => ({
              label: `${p.id} ${p.name}`,
              value: p.id,
              code: p.id,
              name: p.name,
              image: p.image,
              unit: p.unit,
            }))
            await loadData()
            message.success('变体创建成功')
          } catch (e) {
            message.error(e.response?.data?.detail || '创建变体失败')
          }
        },
      })
    }
  } catch (e) {
    if (!isStale()) message.error(e.response?.data?.detail || '查询变体失败')
  }
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  if (addVariantLoading.value) { message.warning('正在查询变体，请稍候'); return }
  if (addFormColor.value && !addForm.value.receive_part_id) { message.warning('变体配件未就绪，请重新选择颜色'); return }
  addSubmitting.value = true
  try {
    await addPlatingItem(route.params.id, addForm.value)
    message.success('明细已添加')
    addModalVisible.value = false
    await loadData()
  } finally {
    addSubmitting.value = false
  }
}

const doDeleteItem = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除配件 ${row.part_name || row.part_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

const isPending = () => !order.value?.archived_at && order.value?.status === 'pending'
const normalizeNote = (value) => (value || '').trim()
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!order.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updatePlatingDeliveryImages(order.value.id, nextImages)
    order.value = data
    pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !data.delivery_images.includes(image))
    message.success(successText)
    return data
  } finally {
    deliveryImagesSaving.value = false
  }
}

const openDeliveryImageModal = () => {
  if (!canAddDeliveryImage.value) {
    message.warning('发货图片最多上传 10 张')
    return
  }
  showDeliveryImageModal.value = true
}

const handleDeliveryImageUploaded = async (url) => {
  if (!url) return
  if (!canAddDeliveryImage.value) {
    message.warning('发货图片最多上传 10 张')
    return
  }
  try {
    await persistDeliveryImages(mergeDeliveryImages(deliveryImages.value, [url]), '发货图片已上传')
  } catch (_) {
    if (!pendingDeliveryImages.value.includes(url)) {
      pendingDeliveryImages.value.push(url)
    }
    message.warning('图片已上传，但写入电镀单失败，可点击“重试保存”继续')
  }
}

const removeDeliveryImage = (index) => {
  if (!order.value) return
  dialog.warning({
    title: '确认删除图片',
    content: '删除后不可恢复，确认继续吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      const nextImages = deliveryImages.value.filter((_, currentIndex) => currentIndex !== index)
      await persistDeliveryImages(nextImages, '发货图片已删除')
    },
  })
}

const retryPendingDeliveryImage = async (image) => {
  if (!pendingDeliveryImages.value.includes(image)) return
  retryingPendingImage.value = image
  try {
    await persistDeliveryImages(
      mergeDeliveryImages(deliveryImages.value, pendingDeliveryImages.value),
      '待保存图片已写入电镀单',
    )
  } catch (_) {
    message.warning('重试保存失败，请稍后再试')
  } finally {
    retryingPendingImage.value = ''
  }
}

const dropPendingDeliveryImage = (image) => {
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((item) => item !== image)
  message.success('已移除待保存记录')
}

const focusEditingNoteInput = () => {
  nextTick(() => {
    noteInputRef.value?.focus?.()
  })
}

const startEditNote = (row) => {
  if (!isPending()) return
  editingNoteItemId.value = row.id
  editingNoteValue.value = row.note || ''
  focusEditingNoteInput()
}

const stopEditNote = (itemId = null) => {
  if (itemId !== null && editingNoteItemId.value !== itemId) return
  editingNoteItemId.value = null
  editingNoteValue.value = ''
}

const saveNote = async (row) => {
  if (editingNoteItemId.value !== row.id || savingNoteItemId.value === row.id) return

  const itemId = row.id
  const nextNote = normalizeNote(editingNoteValue.value)
  const currentNote = normalizeNote(row.note)
  if (nextNote === currentNote) {
    stopEditNote(itemId)
    return
  }

  savingNoteItemId.value = itemId
  try {
    const { data } = await updatePlatingItem(route.params.id, itemId, { note: nextNote })
    row.note = data.note || ''
    message.success(nextNote ? '备注已保存' : '备注已清空')
    stopEditNote(itemId)
  } finally {
    if (savingNoteItemId.value === itemId) {
      savingNoteItemId.value = null
    }
  }
}

const onNoteInputKeydown = (event, row) => {
  if (event.key !== 'Enter') return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void saveNote(row)
}

const renderNoteCell = (row) => {
  const isEditing = editingNoteItemId.value === row.id
  const isSaving = savingNoteItemId.value === row.id
  const noteText = row.note || ''

  if (isEditing) {
    return h(NInput, {
      ref: noteInputRef,
      value: editingNoteValue.value,
      size: 'small',
      placeholder: '输入备注后按回车或点击空白处保存',
      disabled: isSaving,
      autofocus: true,
      'onUpdate:value': (value) => { editingNoteValue.value = value },
      onBlur: () => { void saveNote(row) },
      onKeydown: (event) => onNoteInputKeydown(event, row),
    })
  }

  if (!noteText) {
    if (!isPending()) {
      return h('span', { style: 'color: #999;' }, '-')
    }
    return h(
      NButton,
      {
        text: true,
        type: 'primary',
        size: 'small',
        onClick: () => startEditNote(row),
      },
      {
        icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
        default: () => '添加备注',
      },
    )
  }

  return h(
    'span',
    {
      title: noteText,
      style: [
        'display: inline-block',
        'max-width: 220px',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'white-space: nowrap',
        'vertical-align: bottom',
        isPending() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: isPending() ? () => startEditNote(row) : undefined,
    },
    noteText,
  )
}

// --- Receipt Link ---
const itemReceiptLinks = ref({}) // itemId -> [{receipt_id, receipt_item_id, qty, price}]
const receiptLinksError = ref(false)
const receiptLinkModalVisible = ref(false)
const receiptLinkForm = ref({ itemId: null, receiptId: null, qty: null, price: null })
const receiptLinkOptions = ref([])
const receiptLinkLoading = ref(false)
const receiptLinkSubmitting = ref(false)
const receiptLinkItemInfo = ref(null)

const loadItemReceiptLinks = async () => {
  receiptLinksError.value = false
  try {
    const { data } = await getPlatingReceiptLinks(route.params.id)
    const map = {}
    for (const [key, val] of Object.entries(data)) {
      map[Number(key)] = val
    }
    itemReceiptLinks.value = map
  } catch (_) {
    itemReceiptLinks.value = {}
    receiptLinksError.value = true
  }
}

const openReceiptLinkModal = async (row) => {
  if (!canLinkPlatingReceipt(order.value, row)) return
  receiptLinkForm.value = { itemId: row.id, receiptId: null, qty: null, price: null }
  const { actual, loss, remaining } = platingReceiptQuantities(row)
  receiptLinkItemInfo.value = {
    part_id: row.part_id,
    part_name: row.part_name,
    qty: row.qty,
    actual,
    loss,
    remaining,
    receive_part_name: row.receive_part_name,
  }
  receiptLinkOptions.value = []
  receiptLinkModalVisible.value = true
  receiptLinkLoading.value = true
  try {
    const { data } = await getAvailableReceipts(route.params.id, row.id)
    receiptLinkOptions.value = data
  } catch (_) {
    receiptLinkOptions.value = []
  } finally {
    receiptLinkLoading.value = false
  }
}

const doLinkReceipt = async () => {
  const { itemId, receiptId, qty, price } = receiptLinkForm.value
  if (!receiptId) { message.warning('请选择回收单'); return }
  if (!qty || qty <= 0) { message.warning('请输入回收数量'); return }
  if (price == null || price < 0) { message.warning('请输入回收单价'); return }
  const remaining = receiptLinkItemInfo.value?.remaining || 0
  if (qty > remaining) { message.warning(`回收数量不能超过剩余可收数量 ${remaining}`); return }
  receiptLinkSubmitting.value = true
  try {
    await linkPlatingItemToReceipt(route.params.id, itemId, {
      receipt_id: receiptId,
      qty,
      price,
    })
    message.success('关联回收单成功')
    receiptLinkModalVisible.value = false
    await Promise.all([loadItemReceiptLinks(), loadData()])
  } catch (e) {
    message.error(e.response?.data?.detail || '关联回收单失败')
  } finally {
    receiptLinkSubmitting.value = false
  }
}

const doUnlinkReceipt = (itemId, link) => {
  dialog.warning({
    title: '确认取消关联',
    content: `取消关联回收单「${link.receipt_id}」将回滚对应的库存变更，是否继续？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingReceiptItem(link.receipt_id, link.receipt_item_id)
        message.success('已取消关联')
        await Promise.all([loadItemReceiptLinks(), loadData()])
      } catch (e) {
        message.error(e.response?.data?.detail || '取消关联失败')
      }
    },
  })
}

// --- Order Link ---
const orderOptions = ref([])
const itemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]

const linkModalVisible = ref(false)
const linkForm = ref({ itemId: null, partId: null, orderId: null, todoItemId: null })
const linkTodoItems = ref([])
const linkTodoLoading = ref(false)
const linkSubmitting = ref(false)

const batchLinkModalVisible = ref(false)
const batchLinkOrderId = ref(null)
const batchLinkSubmitting = ref(false)

const loadOrderOptions = async () => {
  try {
    const { data } = await listOrders()
    orderOptions.value = data.map((o) => ({
      label: `${o.id} — ${o.customer_name}`,
      value: o.id,
    }))
  } catch (_) {}
}

const loadItemOrderLinks = async () => {
  try {
    const { data } = await getPlatingAllItemOrders(route.params.id)
    // data is {item_id: [...]} with integer keys serialized as strings
    const map = {}
    for (const [key, val] of Object.entries(data)) {
      map[Number(key)] = val
    }
    itemOrderLinks.value = map
  } catch (_) {
    itemOrderLinks.value = {}
  }
}

const openLinkModal = (row) => {
  linkForm.value = { itemId: row.id, partId: row.part_id, orderId: null, todoItemId: null }
  linkTodoItems.value = []
  linkModalVisible.value = true
  loadOrderOptions()
}

const onLinkOrderSelect = async (orderId) => {
  linkForm.value.todoItemId = null
  linkTodoItems.value = []
  if (!orderId) return
  linkTodoLoading.value = true
  try {
    const { data } = await getTodo(orderId)
    // Filter to matching part_id
    linkTodoItems.value = data.filter((t) => t.part_id === linkForm.value.partId)
    if (linkTodoItems.value.length === 1) {
      linkForm.value.todoItemId = linkTodoItems.value[0].id
    }
  } catch (_) {
    linkTodoItems.value = []
  } finally {
    linkTodoLoading.value = false
  }
}

const doCreateLink = async () => {
  if (!linkForm.value.todoItemId) return
  linkSubmitting.value = true
  try {
    await createLink(linkForm.value.orderId, {
      order_todo_item_id: linkForm.value.todoItemId,
      plating_order_item_id: linkForm.value.itemId,
    })
    message.success('关联成功')
    linkModalVisible.value = false
    await loadItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    linkSubmitting.value = false
  }
}

const openBatchLinkModal = () => {
  batchLinkOrderId.value = null
  batchLinkModalVisible.value = true
  loadOrderOptions()
}

const doBatchLink = async () => {
  if (!batchLinkOrderId.value) return
  batchLinkSubmitting.value = true
  try {
    const allItemIds = items.value.map((i) => i.id)
    const { data } = await batchLink(batchLinkOrderId.value, {
      order_id: batchLinkOrderId.value,
      plating_order_item_ids: allItemIds,
    })
    const msg = [`成功关联 ${data.linked} 项`]
    if (data.skipped.length > 0) {
      msg.push(`跳过: ${data.skipped.join(', ')}`)
    }
    message.success(msg.join('，'))
    batchLinkModalVisible.value = false
    await loadItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '批量关联失败')
  } finally {
    batchLinkSubmitting.value = false
  }
}

const doUnlinkPlatingItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingItemOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadItemOrderLinks()
      } catch (_) {}
    },
  })
}

const renderOrderLinkCell = (row) => {
  const links = itemOrderLinks.value[row.id] || []
  if (order.value?.archived_at) return links.map((link) => link.order_id).join('、') || '—'
  if (links.length === 0) {
    return h(NButton, {
      size: 'small',
      text: true,
      type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny',
        quaternary: true,
        type: 'error',
        style: 'padding: 0 2px;',
        onClick: () => doUnlinkPlatingItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '+' }),
  ])
}

const renderReceiptLinkCell = (row) => {
  if (row.status === '未送出') {
    return h('span', { style: 'color: #ccc;' }, '—')
  }
  const links = itemReceiptLinks.value[row.id] || []
  const { actual, loss, qty, remaining } = platingReceiptQuantities(row)

  if (links.length === 0) {
    if (!canLinkPlatingReceipt(order.value, row)) return '—'
    return h(NButton, {
      size: 'small',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '关联回收单' })
  }

  const children = []
  children.push(...links.map((link) => {
    const badge = [
      h('span', {
        style: 'cursor: pointer; text-decoration: underline;',
        onClick: () => router.push(`/plating-receipts/${link.receipt_id}?highlight=${link.receipt_item_id}`),
      }, link.receipt_id),
    ]
    if (canLinkPlatingReceipt(order.value, row)) {
      badge.push(h(NButton, {
        size: 'tiny',
        quaternary: true,
        type: 'error',
        style: 'padding: 0 2px;',
        onClick: () => doUnlinkReceipt(row.id, link),
      }, { default: () => '×' }))
    }
    return h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, badge)
  }))

  if (canLinkPlatingReceipt(order.value, row)) {
    children.push(h(NButton, {
      size: 'tiny',
      text: true,
      type: 'primary',
      onClick: () => openReceiptLinkModal(row),
    }, { default: () => '+' }))
  }

  const hint = `实收 ${actual} / ${qty}${loss ? ` · 损耗 ${loss}` : ''}${remaining === 0 ? ' · 已结清' : ''}`
  children.push(h('div', { style: 'font-size: 11px; color: #999; margin-top: 2px; width: 100%;' }, hint))

  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, children)
}

const editableColumns = [
  {
    title: '电镀颜色',
    key: 'plating_color_inline',
    width: 120,
    render: (row) => {
      const currentBadge = getColorBadge(row.receive_part_name) || codeOfMethod.value[row.plating_method] || null
      const pending = isPending()
      if (!pending) return row.plating_method || '—'
      const makeChip = (cv) => {
        const isActive = currentBadge === cv.code
        const badge = badgeOf.value[cv.code]
        return h('span', {
          style: {
            display: 'inline-block',
            fontSize: '11px',
            fontWeight: 'bold',
            color: isActive ? '#fff' : badge,
            background: isActive ? badge : '#f5f5f5',
            padding: '2px 8px',
            borderRadius: '4px',
            cursor: pending ? 'pointer' : 'default',
            opacity: pending ? 1 : 0.5,
            border: `1px solid ${badge}`,
          },
          onClick: pending ? () => toggleInlineColor(row, cv.code) : undefined,
        }, cv.code)
      }
      const chips = commonColors.value.map(makeChip)
      if (moreColors.value.length > 0) {
        if (expandedColorRows.value.has(row.id)) {
          chips.push(...moreColors.value.map(makeChip))
        } else {
          chips.push(h('span', {
            style: { fontSize: '11px', cursor: 'pointer', color: '#2080f0', userSelect: 'none' },
            onClick: () => toggleColorRow(row.id),
          }, '⋯'))
        }
      }
      return h('div', { style: 'display: flex; gap: 4px; align-items: center; flex-wrap: wrap;' }, chips)
    },
  },
  {
    title: '发出数量',
    key: 'qty',
    width: 100,
    render: (row) => {
      const key = inlineKey(row.id, 'qty')
      if (key in inlineEditing.value) {
        return h(NInputNumber, {
          ref: (input) => { if (input) inlineInputs.set(key, input); else inlineInputs.delete(key) },
          value: inlineEditing.value[key],
          min: 1,
          precision: 0,
          step: 1,
          size: 'small',
          style: 'width: 90px;',
          disabled: !!inlineSaving.value[key],
          'onUpdate:value': (v) => {
            // Unmounting on Escape can emit a final update; don't reopen a cancelled edit.
            if (key in inlineEditing.value) inlineEditing.value[key] = v
          },
          onBlur: () => { finishQuantityEdit(row) },
          onKeydownCapture: (e) => {
            // Cancel before Naive UI handles Escape by blurring the input.
            if (e.key !== 'Escape' || e.isComposing || e.keyCode === 229) return
            e.preventDefault()
            e.stopPropagation()
            cancelInline(row.id, 'qty')
          },
          onKeydown: (e) => {
            if (e.isComposing || e.keyCode === 229) return
            if (e.key === 'Enter') { e.preventDefault(); finishQuantityEdit(row) }
          },
        })
      }
      if (!isPending()) return row.qty
      return h('span', { style: 'cursor: pointer; color: #2080f0;', onClick: () => startInline(row, 'qty') }, row.qty)
    },
  },
  {
    title: '单位',
    key: 'unit',
    width: 80,
    render: (row) => {
      const key = inlineKey(row.id, 'unit')
      if (key in inlineEditing.value) {
        return renderInlineSelect(row, 'unit', unitOptions)
      }
      const text = row.unit || '-'
      if (!isPending()) return text
      return h('span', { style: 'cursor: pointer; color: #2080f0;', onClick: () => startInline(row, 'unit') }, text)
    },
  },
  {
    title: '重量',
    key: 'weight',
    width: 140,
    render: (row) => {
      if (!isPending()) {
        return row.weight != null ? `${row.weight} ${row.weight_unit || 'g'}` : '—'
      }
      const weightKey = inlineKey(row.id, 'weight')
      const unitKey = inlineKey(row.id, 'weight_unit')
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NInputNumber, {
          value: weightKey in inlineEditing.value ? inlineEditing.value[weightKey] : (row.weight ?? null),
          size: 'small',
          style: 'width:80px',
          min: 0,
          placeholder: '重量',
          onFocus: () => { if (!(weightKey in inlineEditing.value)) inlineEditing.value[weightKey] = row.weight ?? null },
          'onUpdate:value': (v) => { inlineEditing.value[weightKey] = v },
          onBlur: () => { saveInline(row, 'weight', inlineEditing.value[weightKey]) },
        }),
        h(NSelect, {
          value: row.weight_unit || 'g',
          size: 'small',
          style: 'width:55px',
          options: [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }],
          'onUpdate:value': (v) => { saveInline(row, 'weight_unit', v) },
        }),
      ])
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row) => {
      if (order.value?.archived_at) return '历史归档（只读）'
      const pending = isPending()
      const btns = []

      if (pending) {
        btns.push(h(NButton, {
          size: 'small',
          type: 'error',
          onClick: () => doDeleteItem(row),
        }, { default: () => '删除' }))
      }

      if (!pending) {
        btns.push(h(
          NTooltip,
          { trigger: 'hover' },
          {
            trigger: () =>
              h(NButton, {
                size: 'small',
                type: 'error',
                disabled: true,
              }, { default: () => '删除' }),
            default: () => '当前单子进行中/已完成，不允许删除',
          },
        ))
      }

      // Confirm loss button: show when item has gap and status is "电镀中"
      if (canLinkPlatingReceipt(order.value, row)) {
        btns.push(h(NButton, {
          size: 'small',
          type: 'warning',
          onClick: () => openLossModal(row),
        }, { default: () => '确认损耗' }))
      }

      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

const renderField = (key, row) => editableColumns.find((column) => column.key === key)?.render?.(row)
const finishQuantityEdit = (row) => {
  const key = inlineKey(row.id, 'qty')
  if (!(key in inlineEditing.value)) return
  const value = inlineEditing.value[key]
  if (value == null || !Number.isInteger(value) || value < 1) {
    cancelInline(row.id, 'qty')
    return
  }
  void saveInline(row, 'qty', value)
}

const itemColumns = [
  {
    title: '发出 / 收回配件', key: 'part', width: 290,
    render: (row) => {
      if (inlineKey(row.id, 'part_id') in inlineEditing.value) {
        return renderInlineSelect(row, 'part_id', partOptions.value, { renderLabel: renderOptionWithImage, placeholder: '选择发出配件' })
      }
      const badge = getColorBadge(row.receive_part_name) || codeOfMethod.value[row.plating_method]
      return h('div', { class: 'pd-part' }, [
        renderImageThumb(row.part_image, row.part_name, 36),
        h('div', { class: 'pd-part-body' }, [
          h('div', { class: 'pd-part-name' }, [
            isPending() ? h('button', { class: 'pd-part-edit', onClick: () => startInline(row, 'part_id'), 'aria-label': `修改发出配件 ${row.part_name}` }, row.part_name) : row.part_name,
            ...(badge ? [h('span', { class: 'pd-color-tag', style: { color: badgeOf.value[badge] || '#8B9096' } }, badge)] : []),
            ...(partMap.value[row.part_id]?.is_composite ? [h('span', { class: 'pd-color-tag' }, '组合')] : []),
          ]),
          h('div', { class: 'pd-part-code' }, row.part_id),
          h('div', { class: 'pd-part-receive' }, `收回：${row.receive_part_name || '同发出配件'}`),
          ...(row.receive_part_id ? [h('div', { class: 'pd-part-code' }, row.receive_part_id)] : []),
        ]),
      ])
    },
  },
  { title: '电镀颜色', key: 'plating_color_inline', width: 150, render: (row) => renderField('plating_color_inline', row) },
  { title: '发出数量', key: 'qty', width: 110, render: (row) => h('div', { class: 'pd-qty' }, [renderField('qty', row)]) },
  { title: '单位', key: 'unit', width: 90, render: (row) => renderField('unit', row) },
  {
    title: '实际收回', key: 'actual', width: 145,
    render: (row) => {
      const q = platingReceiptQuantities(row)
      return h('div', [
        h('div', { class: 'pd-actual' }, [String(q.actual), h('small', `/ ${row.qty} ${row.unit || ''}`)]),
        h('div', { class: 'pd-progress', role: 'img', 'aria-label': `实收 ${q.actual}，损耗 ${q.loss}，发出 ${q.qty} ${row.unit || ''}` }, [
          h('span', { class: 'pd-progress-received', style: { width: `${q.receivedPercent}%` } }),
          h('span', { class: 'pd-progress-loss', style: { width: `${q.lossPercent}%` } }),
        ]),
      ])
    },
  },
  { title: '未收回', key: 'remaining', width: 90, render: (row) => h('span', { class: 'pd-qty' }, [String(platingReceiptQuantities(row).remaining), h('small', row.unit)]) },
  { title: '损耗', key: 'loss', width: 85, render: (row) => h('span', { class: row.loss_qty ? 'pd-loss' : 'pd-hint' }, row.loss_qty ? `${row.loss_qty} ${row.unit || ''}` : '—') },
  { title: '重量', key: 'weight', width: 165, render: (row) => renderField('weight', row) },
  { title: '备注', key: 'note', width: 200, render: renderNoteCell },
  {
    title: '关联单据', key: 'links', width: 200,
    render: (row) => h('div', { class: 'pd-references' }, [
      renderOrderLinkCell(row),
      renderReceiptLinkCell(row),
    ]),
  },
  { title: '状态', key: 'status', width: 90, render: (row) => h('span', { class: ['pd-item-status', row.status === '未送出' ? 'is-gray' : platingReceiptQuantities(row).remaining === 0 ? 'is-green' : 'is-amber'] }, platingReceiptQuantities(row).remaining === 0 && row.loss_qty ? '已核销' : row.status) },
  { title: '操作', key: 'actions', width: 140, render: (row) => renderField('actions', row) },
]

onMounted(async () => {
  try {
    // Load parts/colors and data in parallel; order links also in parallel with loadData
    const [{ data: parts }, colorsRes] = await Promise.all([listParts(), getColorVariants()])
    allParts.value = parts
    parts.forEach((p) => { partMap.value[p.id] = p })
    partOptions.value = parts.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    colorVariantList.value = colorsRes.data
    await Promise.all([loadData(), loadItemOrderLinks(), loadItemReceiptLinks()])
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.plating-detail { min-width: 0; }
.pd-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin: 8px 0 20px; }
.pd-title { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.pd-title .page-title { margin: 0; }
.pd-status { border: 0; border-radius: 20px; padding: 4px 11px; font: inherit; font-size: 11px; font-weight: 600; background: #EBEDF0; color: #7C858C; cursor: pointer; }
.pd-status:disabled { cursor: default; }
.pd-status--processing { background: #FBF0DC; color: #B7791F; }
.pd-status--completed { background: #E6F2EC; color: #1E7A5A; }
.pd-stepper { display: flex; align-items: center; margin: 24px 0; }
.pd-step { display: flex; align-items: center; gap: 9px; flex-shrink: 0; }
.pd-step-dot { width: 23px; height: 23px; flex-shrink: 0; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 600; color: #A5ADB5; background: #E6E9EC; }
.pd-step-label { font-size: 12px; font-weight: 600; color: #A1A8AF; }
.pd-step-sub { font-size: 10px; color: #8B9096; margin-top: 2px; }
.pd-step.is-current .pd-step-dot, .pd-step.is-done .pd-step-dot { background: #1E7A5A; color: #fff; }
.pd-step.is-current .pd-step-dot { box-shadow: 0 0 0 4px #E1EDE7; }
.pd-step.is-current .pd-step-label, .pd-step.is-done .pd-step-label { color: #1A1D21; }
.pd-step-line { flex: 1; height: 2px; background: #E5E8EB; margin: 0 20px; }
.pd-step-line.is-done { background: #1E7A5A; }
.pd-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); background: #fff; border: 1px solid #ECEDEF; border-radius: 9px; overflow: hidden; }
.pd-stat { padding: 14px 17px; border-right: 1px solid #ECEDEF; }
.pd-stat:last-child { border-right: 0; }
.pd-stat-label, .pd-meta-label { font-size: 10px; color: #8B9096; margin-bottom: 4px; }
.pd-stat-value { font-size: 25px; font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.pd-stat-value small { font-size: 12px; color: #8B9096; font-weight: 500; margin-left: 4px; }
.pd-stat-loss { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.pd-stat-loss span { white-space: nowrap; }
.pd-stat-note { font-size: 10px; color: #A4ABB1; margin-top: 4px; }
.pd-stat-value.is-green { color: #1E7A5A; }
.pd-stat-value.is-amber { color: #B7791F; }
.pd-meta { display: grid; grid-template-columns: minmax(160px, 1.1fr) minmax(170px, 1fr) minmax(130px, .9fr) minmax(160px, 1.5fr); gap: 18px; padding: 20px 0 26px; }
.pd-meta-item { min-width: 0; }
.pd-meta-value { font-size: 12px; min-height: 20px; overflow-wrap: anywhere; }
.pd-meta-value :deep(.n-space) { max-width: 100%; }
.pd-note-edit { display: inline-flex; align-items: baseline; gap: 6px; max-width: 100%; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; cursor: pointer; }
.pd-note-edit :deep(.n-icon) { flex-shrink: 0; color: #1E7A5A; }
.pd-note-edit:hover { color: #1E7A5A; }
.pd-note-edit:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 3px; border-radius: 3px; }
.pd-note-text { white-space: pre-wrap; }
.pd-section { margin-bottom: 24px; }
.pd-section-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; border-bottom: 1px solid #ECEDEF; padding-bottom: 9px; margin-bottom: 12px; }
.pd-section-title { display: flex; align-items: center; gap: 8px; }
.pd-section-title h3 { margin: 0; font-size: 11px; color: #8B9096; letter-spacing: .8px; font-weight: 700; }
.pd-count { font-size: 10px; border-radius: 4px; padding: 1px 6px; color: #879199; background: #E9ECEF; }
.pd-hint, .pd-table-note { font-size: 10px; color: #939DA5; }
.pd-table-note { margin: 9px 0 0; }
.pd-table { border: 1px solid #ECEDEF; border-radius: 9px; overflow: hidden; }
.pd-table :deep(th.n-data-table-th) { background: #FAFBFB; color: #8B9096; font-size: 10px; font-weight: 600; }
.pd-table :deep(td.n-data-table-td) { padding: 14px 12px; font-size: 12px; }
.pd-table :deep(.pd-part) { display: flex; align-items: center; gap: 9px; }
.pd-table :deep(.pd-part-body) { min-width: 0; }
.pd-table :deep(.pd-part-name) { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 12px; font-weight: 600; }
.pd-table :deep(.pd-part-edit) { border: 0; padding: 0; background: transparent; color: #1E7A5A; font: inherit; cursor: pointer; text-align: left; }
.pd-table :deep(.pd-color-tag) { font-size: 9px; border-radius: 3px; padding: 1px 5px; background: #F3F4F5; }
.pd-table :deep(.pd-part-code) { color: #A5ADB4; font-size: 10px; margin-top: 1px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.pd-table :deep(.pd-part-receive) { font-size: 10px; color: #939C96; margin-top: 2px; }
.pd-table :deep(.pd-qty) { font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.pd-table :deep(.pd-qty small), .pd-table :deep(.pd-actual small) { color: #A4ACB3; font-size: 10px; font-weight: 400; margin-left: 4px; }
.pd-table :deep(.pd-actual) { color: #1E7A5A; font-weight: 600; font-variant-numeric: tabular-nums; }
.pd-table :deep(.pd-progress) { display: flex; width: 90px; height: 4px; border-radius: 3px; overflow: hidden; background: #EEF0F2; margin-top: 6px; }
.pd-table :deep(.pd-progress-received) { background: #4B9E7C; }
.pd-table :deep(.pd-progress-loss) { background: #D7AE64; }
.pd-table :deep(.pd-loss) { color: #B7791F; }
.pd-table :deep(.pd-references) { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.pd-table :deep(.pd-references .n-button) { color: #718278; font-size: 10px; }
.pd-table :deep(.pd-item-status) { display: inline-block; border-radius: 12px; font-size: 10px; padding: 2px 7px; white-space: nowrap; }
.pd-table :deep(.pd-item-status.is-green) { color: #1E7A5A; background: #E6F2EC; }
.pd-table :deep(.pd-item-status.is-amber) { color: #B7791F; background: #FBF0DC; }
.pd-table :deep(.pd-item-status.is-gray) { color: #929AA2; background: #F0F2F4; }
.pd-footer-note { color: #939EA5; font-size: 11px; }
.pd-receipt-picker { display: flex; flex-direction: column; gap: 8px; }
.pd-receipt-choice { display: flex; flex-direction: column; align-items: flex-start; text-align: left; gap: 4px; padding: 12px; border: 1px solid #ECEDEF; border-radius: 8px; background: #FAFBFB; cursor: pointer; font: inherit; overflow-wrap: anywhere; }
.pd-receipt-choice span { color: #8B9096; font-size: 12px; }
.pd-receipt-choice:hover { border-color: #1E7A5A; background: #F1F7F3; }
@media (max-width: 1200px) { .pd-meta { grid-template-columns: 1fr 1fr; } .pd-stat { padding: 12px; } }
@media (max-width: 760px) {
  .pd-title .page-title { font-size: 22px; }
  .plating-detail > .page-breadcrumb { padding-left: 32px; }
  .pd-stepper { align-items: flex-start; }
  .pd-step { gap: 6px; }
  .pd-step-dot { width: 19px; height: 19px; font-size: 10px; }
  .pd-step-label { font-size: 11px; }
  .pd-step-sub { font-size: 9px; max-width: 68px; }
  .pd-step-line { min-width: 8px; margin: 9px 8px 0; }
  .pd-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .pd-stat { border-bottom: 1px solid #ECEDEF; }
  .pd-stat:nth-child(3) { border-right: 0; }
  .pd-stat:nth-child(4), .pd-stat:nth-child(5) { border-bottom: 0; }
  .pd-stat:nth-child(5) { grid-column: span 2; }
  .pd-stat-value { font-size: 22px; }
  .pd-stat-note { font-size: 9px; }
  .pd-meta { gap: 14px; }
  .pd-meta-note { grid-column: 1 / -1; }
}
@media (max-width: 360px) { .pd-step { gap: 5px; } .pd-step-sub { max-width: 48px; } .pd-step-line { margin-left: 5px; margin-right: 5px; } }
.delivery-images-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.delivery-images-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.delivery-images-warning {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #f3d08a;
  background: #fff8e8;
}

.delivery-images-warning-title {
  color: #8a5a17;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.delivery-images-pending-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.delivery-pending-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.delivery-pending-preview {
  display: block;
  border-radius: 10px;
  overflow: hidden;
}

.delivery-pending-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.delivery-image-card {
  position: relative;
  width: 88px;
  height: 88px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #E0E4E7;
  background: #F6F7F8;
}

.delivery-image-preview {
  display: block;
}

.delivery-image-delete {
  position: absolute;
  top: 6px;
  right: 6px;
}

.delivery-image-add {
  width: 88px;
  height: 88px;
  border: 1px dashed #D1D9D4;
  border-radius: 8px;
  background: #F7FAF8;
  color: #98AA9F;
  font-size: 30px;
  line-height: 1;
  cursor: pointer;
}

.delivery-image-add:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.delivery-images-meta {
  color: #939DA5;
  font-size: 10px;
}
</style>
