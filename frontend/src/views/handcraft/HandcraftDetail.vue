<template>
  <div>
    <!-- ── Page header ─────────────────────────────────────── -->
    <n-button text size="small" class="page-back" @click="router.back()">← 返回</n-button>
    <div class="page-breadcrumb">生产 / 手工单 / {{ order?.id || '…' }}</div>

    <div class="hc-head">
      <div class="hc-head__left">
        <h2 class="page-title" style="margin-bottom: 0;">手工单 {{ order?.id || '…' }}</h2>
        <span
          v-if="order"
          class="hc-status-pill"
          :class="{
            'hc-status-pill--emerald': order.status === 'completed',
            'hc-status-pill--amber':   order.status === 'processing',
            'hc-status-pill--gray':    order.status === 'pending',
          }"
        >{{ statusLabel[order.status] }}</span>
      </div>
    </div>

    <!-- ── Status stepper ──────────────────────────────────── -->
    <div v-if="order" class="hc-stepper">
      <div class="hc-step" :class="stepClass('pending')">
        <span class="hc-step__dot">{{ order.status !== 'pending' ? '✓' : '1' }}</span>
        <div>
          <div class="hc-step__lab">待发出</div>
          <div class="hc-step__sub">{{ fmt(order.created_at) }}</div>
        </div>
      </div>
      <div class="hc-bar" :class="order.status !== 'pending' ? 'hc-bar--on' : 'hc-bar--off'"></div>
      <div class="hc-step" :class="stepClass('processing')">
        <span class="hc-step__dot">{{ order.status === 'completed' ? '✓' : '2' }}</span>
        <div>
          <div class="hc-step__lab">进行中</div>
          <div class="hc-step__sub">{{ order.status !== 'pending' ? '已发出' : '待发出' }}</div>
        </div>
      </div>
      <div class="hc-bar" :class="order.status === 'completed' ? 'hc-bar--on' : 'hc-bar--off'"></div>
      <div class="hc-step" :class="stepClass('completed')">
        <span class="hc-step__dot">3</span>
        <div>
          <div class="hc-step__lab">已完成</div>
          <div class="hc-step__sub">{{ order.status === 'completed' ? (order.completed_at ? fmt(order.completed_at) : '已完成') : '待产出全部收回' }}</div>
        </div>
      </div>
    </div>

    <!-- ── Summary stat cards ──────────────────────────────── -->
    <div v-if="order" class="hc-stats">
      <div class="hc-stat">
        <div class="hc-stat__k">产出项</div>
        <div class="hc-stat__v">
          {{ jewelryItems.length }}<small> 种 · {{ totalJewelryQty }} 件</small>
        </div>
      </div>
      <div class="hc-stat">
        <div class="hc-stat__k">发出配件</div>
        <div class="hc-stat__v">
          {{ items.length }}<small> 种</small>
        </div>
      </div>
      <div class="hc-stat">
        <div class="hc-stat__k">产出已收回</div>
        <div class="hc-stat__v">
          {{ totalReceivedQty }}<small> / {{ totalJewelryQty }}</small>
        </div>
      </div>
      <div class="hc-stat">
        <div class="hc-stat__k">差额 / 损耗</div>
        <div class="hc-stat__v">{{ totalLossQty }}</div>
      </div>
      <div v-if="order.receipt_code" class="hc-stat">
        <div class="hc-stat__k">回执码</div>
        <div
          class="hc-stat__v hc-stat__v--mono hc-receipt-copy"
          style="font-size: 20px; letter-spacing: 1px;"
          title="点击复制"
          @click="copyReceiptCode"
        >{{ order.receipt_code }}</div>
      </div>
    </div>

    <!-- ── Meta strip ──────────────────────────────────────── -->
    <div v-if="order" class="hc-meta">
      <div class="hc-meta__item">
        <div class="hc-meta__k">手工商家</div>
        <div class="hc-meta__v">
          <template v-if="editingSupplier && order.status === 'pending'">
            <n-space align="center" size="small">
              <n-select
                v-model:value="editingSupplierName"
                :options="supplierOptions"
                filterable
                tag
                placeholder="选择或输入手工商家名称"
                size="small"
                style="width: 180px;"
              />
              <n-button size="small" type="primary" :loading="savingSupplier" @click="saveSupplier">确认</n-button>
              <n-button size="small" :disabled="savingSupplier" @click="editingSupplier = false">取消</n-button>
            </n-space>
          </template>
          <template v-else>
            {{ order.supplier_name }}
            <n-button v-if="order.status === 'pending'" text type="primary" size="small" style="margin-left: 4px;" @click="startEditSupplier">
              <template #icon><n-icon :component="CreateOutline" /></template>
            </n-button>
          </template>
        </div>
      </div>
      <div class="hc-meta__item">
        <div class="hc-meta__k">创建时间</div>
        <div class="hc-meta__v">
          <template v-if="editingCreatedAt">
            <n-space align="center" size="small">
              <n-date-picker
                v-model:value="editingCreatedAtTs"
                type="date"
                size="small"
                style="width: 150px;"
              />
              <n-button size="small" type="primary" :loading="savingCreatedAt" @click="saveCreatedAt">确认</n-button>
              <n-button size="small" :disabled="savingCreatedAt" @click="editingCreatedAt = false">取消</n-button>
            </n-space>
          </template>
          <template v-else>
            {{ fmt(order.created_at) }}
            <n-button text type="primary" size="small" style="margin-left: 4px;" @click="startEditCreatedAt">
              <template #icon><n-icon :component="CreateOutline" /></template>
            </n-button>
          </template>
        </div>
      </div>
      <div v-if="order.completed_at" class="hc-meta__item">
        <div class="hc-meta__k">完成时间</div>
        <div class="hc-meta__v">{{ fmt(order.completed_at) }}</div>
      </div>
      <div v-if="order.note" class="hc-meta__item">
        <div class="hc-meta__k">备注</div>
        <div class="hc-meta__v">{{ order.note }}</div>
      </div>
    </div>

    <n-spin :show="loading">
      <!-- ── 产出项 section ────────────────────────────────────── -->
      <div v-if="jewelryItems.length > 0" class="hc-sec">
        <div class="hc-sec-h">
          <span class="t">产出项</span>
          <span class="acts">
            <button
              v-if="order?.status === 'pending'"
              class="hc-sbtn hc-sbtn--primary"
              @click="openBatchLinkModal"
            >🔗 批量关联订单</button>
          </span>
        </div>
        <n-data-table :columns="jewelryColumns" :data="jewelryItems" :bordered="false" />
      </div>

      <!-- ── 客户分拣 — BreakdownMatrix has its own "客户分拣" header, no wrapper title needed ── -->
      <div
        v-if="breakdownGroups.length > 0 || items.length > 0"
        class="hc-sec hc-sec--no-title"
      >
        <BreakdownMatrix
          :hc-id="route.params.id"
          :hc-status="order?.status || 'pending'"
          :groups="breakdownGroups"
          @saved="onBreakdownSaved"
        />
      </div>

      <!-- ── 发货图片 section ──────────────────────────────────────── -->
      <div v-if="order" class="hc-sec">
        <div class="hc-sec-h"><span class="t">发货图片</span></div>
        <div class="delivery-images-block">
          <div v-if="pendingDeliveryImages.length > 0" class="delivery-images-warning">
            <div class="delivery-images-warning-title">
              有 {{ pendingDeliveryImages.length }} 张图片已上传，但还没保存到手工单
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
                    :disabled="deliveryImagesSaving"
                    @click="retryPendingDeliveryImage(image)"
                  >
                    重试保存
                  </n-button>
                  <n-button
                    size="tiny"
                    quaternary
                    :disabled="deliveryImagesSaving || retryingPendingImage === image"
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
            v-else
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
      </div>

      <!-- ── 发出配件 section ───────────────────────────────────── -->
      <div class="hc-sec">
        <div class="hc-sec-h">
          <span class="t">发出配件</span>
          <span class="acts">
            <button
              v-if="items.length > 0"
              class="hc-sbtn"
              :disabled="cuttingStatsLoading"
              @click="openCuttingStatsModal"
            >裁剪统计</button>
            <button
              v-if="items.length > 0"
              class="hc-sbtn"
              :class="order?.status === 'pending' ? 'hc-sbtn--primary' : ''"
              @click="openPickingSimulation"
            >配货模拟</button>
            <button
              v-if="order?.status === 'pending'"
              class="hc-sbtn hc-sbtn--primary"
              @click="openAddModal"
            >＋ 添加配件</button>
          </span>
        </div>
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
      </div>

      <!-- ── 补货配件 section ───────────────────────────────────── -->
      <div v-if="order" class="hc-sec">
        <div class="hc-sec-h">
          <span class="t">补货配件</span>
          <span class="acts">
            <n-tag size="small" type="warning" :bordered="false">待补 {{ pendingRestockCount }}</n-tag>
            <n-tag size="small" type="default" :bordered="false">已补 {{ doneRestockCount }}</n-tag>
            <button class="hc-sbtn hc-sbtn--primary" @click="openManualRestockModal">＋ 手动添加</button>
          </span>
        </div>
        <n-data-table
          :columns="restockColumns"
          :data="restockRows"
          :loading="restockLoading"
          :bordered="false"
          size="small"
          :row-class-name="restockRowClass"
        />
      </div>
    </n-spin>

    <n-modal v-model:show="addModalVisible" preset="card" title="添加配件明细" :style="{ width: isMobile ? '95vw' : '560px' }">
      <n-tabs v-model:value="addModalTab" type="line" animated>
        <n-tab-pane name="single" tab="单条添加">
          <form @submit.prevent="doAddItem">
            <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
              <n-form-item label="配件">
                <n-select
                  v-model:value="addForm.part_id"
                  :options="partOptions"
                  :render-label="renderOptionWithImage"
                  filterable
                  clearable
                  placeholder="选择配件"
                  @update:value="onAddPartSelect"
                />
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
        </n-tab-pane>

        <n-tab-pane name="recent" tab="最近导入">
          <RecentImportsPicker
            :existing-items="items"
            @change="onRecentChange"
          />
        </n-tab-pane>
      </n-tabs>

      <template #footer>
        <n-space justify="space-between" style="width: 100%;">
          <span v-if="addModalTab === 'recent' && recentAttachPayload.rows.length > 0" style="font-size: 12px; color: #6b7280;">
            新增 <strong>{{ recentAttachPayload.newCount }}</strong> 项 ·
            累加 <strong>{{ recentAttachPayload.updateCount }}</strong> 项 ·
            共 <strong>{{ recentAttachPayload.totalQty }}</strong> 件
          </span>
          <span v-else style="font-size: 12px; color: #9ca3af;">
            <span v-if="addModalTab === 'recent'">请勾选要加入的项</span>
          </span>

          <n-space>
            <n-button @click="addModalVisible = false">取消</n-button>
            <n-button
              v-if="addModalTab === 'single'"
              type="primary"
              :loading="addSubmitting"
              @click="doAddItem"
            >确认添加</n-button>
            <n-button
              v-else
              type="primary"
              :loading="attachSubmitting"
              :disabled="recentAttachPayload.rows.length === 0 || recentAttachPayload.hasZeroQty"
              @click="attachRecentBatch"
            >
              {{
                recentAttachPayload.hasZeroQty
                  ? '勾选项含数量 0'
                  : `加入 ${recentAttachPayload.rows.length} 项`
              }}
            </n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="editModalVisible" preset="card" title="修改配件明细" :style="{ width: isMobile ? '95vw' : '500px' }">
      <form @submit.prevent="doEditItem">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editForm.unit" :options="unitOptions" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="editSubmitting" @click="doEditItem">保存修改</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showDeliveryImageModal"
      kind="handcraft"
      :entity-id="order?.id"
      suppress-success
      @uploaded="handleDeliveryImageUploaded"
    />

    <!-- Single Link Modal for part items -->
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
          <n-button type="primary" :loading="linkSubmitting" :disabled="!linkForm.todoItemId" @click="doCreatePartLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Jewelry Link Modal: just select order -->
    <n-modal v-model:show="jewelryLinkModalVisible" preset="card" title="关联订单（产出）" :style="{ width: isMobile ? '95vw' : '500px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="选择订单">
          <n-select
            v-model:value="jewelryLinkOrderId"
            :options="orderOptions"
            filterable
            placeholder="搜索订单号或客户名"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="jewelryLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="jewelryLinkSubmitting" :disabled="!jewelryLinkOrderId" @click="doCreateJewelryLink">确认关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Batch Link Modal -->
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
          将自动按配件编号匹配该订单配件清单中的行
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="batchLinkModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="batchLinkSubmitting" :disabled="!batchLinkOrderId" @click="doBatchLink">确认批量关联</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Cutting stats modal -->
    <n-modal v-model:show="cuttingStatsVisible" preset="card" title="裁剪统计" :style="{ width: isMobile ? '95vw' : '720px' }">
      <n-spin :show="cuttingStatsLoading">
        <n-data-table
          v-if="cuttingStatsData.length > 0"
          :columns="cuttingStatsColumns"
          :data="cuttingStatsData"
          :bordered="false"
          size="small"
          :row-key="row => row.part_id"
        />
        <n-empty v-else-if="!cuttingStatsLoading" description="暂无裁剪统计数据" />
      </n-spin>
      <template #footer>
        <n-space justify="end">
          <n-button @click="cuttingStatsVisible = false">关闭</n-button>
          <n-button type="primary" :loading="cuttingStatsPdfLoading" :disabled="!cuttingStatsData.some(i => i.qty > 0)" @click="doCuttingStatsPdfExport">导出 PDF</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Confirm Loss Modal -->
    <n-modal v-model:show="showLossModal" preset="card" title="确认损耗" :style="{ width: isMobile ? '95vw' : '420px' }">
      <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="80">
        <n-form-item label="差额信息">
          <span v-if="lossTarget">已收回 {{ lossTarget.received_qty || 0 }} / 发出 {{ lossTarget.qty }}，差额 {{ lossTarget.qty - (lossTarget.received_qty || 0) }}</span>
        </n-form-item>
        <n-form-item label="损耗数量">
          <n-input-number v-model:value="lossForm.loss_qty" :min="lossTargetType === 'jewelry' ? 1 : 0.01" :precision="lossTargetType === 'jewelry' ? 0 : undefined" :max="lossTarget ? lossTarget.qty - (lossTarget.received_qty || 0) : 0" style="width: 100%;" />
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

    <n-modal v-model:show="manualRestockShow" preset="card" title="手动添加补货项" style="max-width: 480px;">
      <n-form>
        <n-form-item label="配件" required>
          <n-select
            v-model:value="manualRestockPartId"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择配件"
          />
        </n-form-item>
        <n-form-item label="差额">
          <n-input-number
            v-model:value="manualRestockShortfall"
            :min="0"
            :precision="2"
            placeholder="可选"
            clearable
            style="width: 100%;"
          />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="manualRestockNote" type="textarea" :rows="2" placeholder="选填" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="manualRestockShow = false">取消</n-button>
          <n-button type="primary" :loading="manualRestockSaving" @click="saveManualRestock">提交</n-button>
        </n-space>
      </template>
    </n-modal>

    <HandcraftPickingSimulationModal
      :show="pickingModalShow"
      :order-id="String(route.params.id)"
      :status="order?.status || 'pending'"
      @update:show="(v) => { pickingModalShow = v; if (!v) loadData() }"
      @restock-changed="loadRestock"
    />

    <!-- ── Floating action bar ────────────────────────────────── -->
    <floating-action-bar v-if="order">
      <n-button
        quaternary
        style="color:#C0C6CD"
        @click="router.push(`/handcraft-receipts?supplier_name=${encodeURIComponent(order.supplier_name)}`)"
      >
        查看回收单
      </n-button>
      <n-button
        quaternary
        class="hc-export-btn--excel"
        style="color:#C0C6CD"
        :loading="downloadingExcel"
        @click="doDownloadExcel"
      >
        导出Excel
      </n-button>
      <n-button
        quaternary
        class="hc-export-btn--pdf"
        style="color:#C0C6CD"
        :loading="downloadingPdf"
        @click="doDownloadPdf"
      >
        导出PDF
      </n-button>
      <n-button
        v-if="order.status === 'pending'"
        type="primary"
        :loading="sending"
        @click="doSend"
      >
        确认发出
      </n-button>
    </floating-action-bar>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { useSendWithStockSupplement } from '@/composables/useSendWithStockSupplement'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon, NImage,
  NRadioGroup, NRadio, NDatePicker, NTabs, NTabPane,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft, supplementAndSendHandcraft,
  addHandcraftPart, updateHandcraftPart, deleteHandcraftPart,
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry, updateHandcraft,
  updateHandcraftDeliveryImages, downloadHandcraftExcel, downloadHandcraftPdf,
  getHandcraftPartOrders, deleteHandcraftPartOrderLink,
  getHandcraftJewelryOrders, deleteHandcraftJewelryOrderLink,
  getHandcraftCuttingStats, downloadHandcraftCuttingStatsPdf,
  getHandcraftPicking,
  getHandcraftJewelryBreakdown,
} from '@/api/handcraft'
import BreakdownMatrix from '@/components/BreakdownMatrix.vue'
import { tsToDateStr, isoToTs } from '@/utils/date'
import { confirmHandcraftLoss } from '@/api/productionLoss'
import { changeOrderStatus } from '@/api/kanban'
import { listParts, updatePart } from '@/api/parts'
import {
  listHandcraftRestock,
  createRestock,
  markRestockDone,
  deleteRestock,
  updateRestockShortfall,
} from '@/api/restock'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { listJewelries } from '@/api/jewelries'
import { listOrders, getTodo, createLink, batchLink } from '@/api/orders'
import { renderNamedImage, renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import HandcraftPickingSimulationModal from '@/components/picking/HandcraftPickingSimulationModal.vue'
import FloatingActionBar from '@/components/FloatingActionBar.vue'
import RecentImportsPicker from '@/components/RecentImportsPicker.vue'
import { attachPartsToOrder } from '@/api/handcraftActions'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()

const loading = ref(true)
const downloadingExcel = ref(false)
const downloadingPdf = ref(false)
const order = ref(null)
const collapsed = reactive({
  basic: false,
  jewelry: false,
  parts: false,
  restock: false,
})
const editingCreatedAt = ref(false)
const editingCreatedAtTs = ref(null)
const savingCreatedAt = ref(false)

const editingSupplier = ref(false)
const editingSupplierName = ref(null)
const savingSupplier = ref(false)
const supplierOptions = ref([])

const startEditSupplier = () => {
  editingSupplierName.value = order.value?.supplier_name
  editingSupplier.value = true
}

const saveSupplier = async () => {
  const name = editingSupplierName.value?.trim()
  if (!name) { message.warning('请输入手工商家名称'); return }
  if (name === order.value?.supplier_name) { editingSupplier.value = false; return }
  savingSupplier.value = true
  try {
    const isNew = !supplierOptions.value.some((o) => o.value === name)
    if (isNew) {
      try { await createSupplier({ name, type: 'handcraft' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    await updateHandcraft(route.params.id, { supplier_name: name })
    await loadData()
    message.success('手工商家已更新')
    editingSupplier.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingSupplier.value = false
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
    await updateHandcraft(route.params.id, { created_at: dateStr })
    await loadData()
    message.success('创建时间已更新')
    editingCreatedAt.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '更新失败')
  } finally {
    savingCreatedAt.value = false
  }
}

const items = ref([])
const partMap = ref({})
const partOptions = ref([])
const showDeliveryImageModal = ref(false)
const deliveryImagesSaving = ref(false)
const pendingDeliveryImages = ref([])
const retryingPendingImage = ref('')

// Confirm loss modal
const showLossModal = ref(false)
const lossTarget = ref(null)
const lossTargetType = ref('part') // "part" or "jewelry"
const lossForm = ref({ loss_qty: 0, deduct_amount: null, reason: '', note: '' })
const lossSubmitting = ref(false)

const openLossModal = (item, itemType) => {
  lossTarget.value = item
  lossTargetType.value = itemType
  const gap = item.qty - (item.received_qty || 0)
  lossForm.value = { loss_qty: gap, deduct_amount: null, reason: '', note: '' }
  showLossModal.value = true
}

const doConfirmLoss = async () => {
  lossSubmitting.value = true
  try {
    const payload = {
      ...lossForm.value,
      item_type: lossTargetType.value,
    }
    if (!payload.deduct_amount) payload.deduct_amount = null
    if (!payload.reason) payload.reason = null
    if (!payload.note) payload.note = null
    await confirmHandcraftLoss(route.params.id, lossTarget.value.id, payload)
    showLossModal.value = false
    message.success('损耗已确认')
    await loadData()
  } catch (err) {
    // error handled by interceptor
  } finally {
    lossSubmitting.value = false
  }
}

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }

// ── Stepper helper ─────────────────────────────────────────────
// Returns the CSS modifier class for each stepper step based on order.status.
// Status order: pending → processing → completed
const STATUS_ORDER = ['pending', 'processing', 'completed']
const stepClass = (step) => {
  if (!order.value) return 'hc-step--todo'
  const cur = STATUS_ORDER.indexOf(order.value.status)
  const idx = STATUS_ORDER.indexOf(step)
  if (idx < cur) return 'hc-step--done'
  if (idx === cur) return 'hc-step--cur'
  return 'hc-step--todo'
}

// ── Stat-card computeds ────────────────────────────────────────
const totalJewelryQty = computed(() =>
  jewelryItems.value.reduce((s, j) => s + Number(j.qty || 0), 0),
)
const totalReceivedQty = computed(() =>
  jewelryItems.value.reduce((s, j) => s + (Number(j.received_qty || 0) - Number(j.loss_qty || 0)), 0),
)
const totalLossQty = computed(() =>
  jewelryItems.value.reduce((s, j) => s + Number(j.loss_qty || 0), 0),
)
const deliveryImages = computed(() => order.value?.delivery_images || [])
const totalDeliveryImageCount = computed(() => deliveryImages.value.length + pendingDeliveryImages.value.length)
const canAddDeliveryImage = computed(() => totalDeliveryImageCount.value < 10)
const statusOptions = computed(() => {
  if (!order.value) return []
  const s = order.value.status
  if (s === 'pending') return [{ label: '进行中', value: 'processing' }]
  if (s === 'processing') return [
    { label: '待发出', value: 'pending' },
    { label: '已完成', value: 'completed' },
  ]
  if (s === 'completed') return [{ label: '进行中', value: 'processing' }]
  return []
})
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const weightUnitOptions = [
  { label: 'kg', value: 'kg' },
  { label: 'g', value: 'g' },
]

const addModalVisible = ref(false)
const addSubmitting = ref(false)
const addForm = ref({ part_id: null, qty: 1, unit: '个', weight: null, weight_unit: 'kg', note: '' })
const addModalTab = ref(null) // set by openAddModal based on whether batches exist
const recentAttachPayload = ref({ rows: [], newCount: 0, updateCount: 0, totalQty: 0, hasZeroQty: false })
const attachSubmitting = ref(false)

const onRecentChange = (payload) => {
  recentAttachPayload.value = payload
}

const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ id: null, qty: 1, unit: '个' })
const editingCellKey = ref('')
const editingCellValue = ref('')
const savingCellKey = ref('')
const cellInputRef = ref(null)

const loadParts = async () => {
  const { data: parts } = await listParts()
  partMap.value = Object.fromEntries(parts.map((part) => [part.id, part]))
  partOptions.value = parts.map((p) => ({
    label: `${p.id} ${p.name}`,
    value: p.id,
    code: p.id,
    name: p.name,
    image: p.image,
    unit: p.unit,
  }))
}

// Picking-derived weights (handcraft_picking_weight table), keyed by part_item_id.
// Each value is a list of rows: { part_item_id, atom_part_id, weight, weight_unit, ... }.
const pickingPartsByItemId = ref({})

const loadPickingWeights = async () => {
  try {
    const resp = await getHandcraftPicking(route.params.id)
    const map = {}
    for (const g of resp.data.groups || []) {
      for (const r of g.rows || []) {
        if (!map[r.part_item_id]) map[r.part_item_id] = []
        map[r.part_item_id].push(r)
      }
    }
    pickingPartsByItemId.value = map
  } catch {
    // non-fatal: weight column will fall back to dashes
    pickingPartsByItemId.value = {}
  }
}

const toKg = (w, unit) => {
  if (w == null) return 0
  return unit === 'g' ? Number(w) / 1000 : Number(w)
}

// --- Restock records ---
const restockRows = ref([])
const restockLoading = ref(false)

async function loadRestock() {
  if (!order.value?.id) return
  restockLoading.value = true
  try {
    const { data } = await listHandcraftRestock(order.value.id)
    restockRows.value = data
  } finally {
    restockLoading.value = false
  }
}

const pendingRestockCount = computed(() =>
  restockRows.value.filter((r) => r.status === 'pending').length
)
const doneRestockCount = computed(() =>
  restockRows.value.filter((r) => r.status === 'done').length
)

function restockRowClass(row) {
  return row.status === 'done' ? 'restock-row-done' : ''
}

const restockColumns = computed(() => [
  {
    title: '配件',
    key: 'part_id',
    render: (row) => {
      const p = partMap.value[row.part_id]
      return p ? `${row.part_id} · ${p.name}` : row.part_id
    },
  },
  {
    title: '来源',
    key: 'source',
    render: (row) => {
      const label = row.source === 'picking' ? '配货模拟' : '手动添加'
      const date = new Date(row.created_at).toLocaleDateString()
      return `${label} · ${date}`
    },
  },
  {
    title: '差额',
    key: 'shortfall_qty',
    width: 120,
    render: (row) => row.status === 'done'
      ? (row.shortfall_qty != null ? String(row.shortfall_qty) : '—')
      : h(NInputNumber, {
          value: row.shortfall_qty != null ? Number(row.shortfall_qty) : null,
          size: 'small',
          min: 0,
          showButton: false,
          placeholder: '—',
          style: 'width: 90px;',
          onUpdateValue: (v) => onShortfallChange(row, v),
        }),
  },
  {
    title: '状态',
    key: 'status',
    render: (row) => h(NTag, {
      size: 'small',
      type: row.status === 'done' ? 'success' : 'warning',
      bordered: false,
    }, { default: () => row.status === 'done' ? '✓ 已补过' : '⏳ 待补货' }),
  },
  { title: '备注', key: 'note', render: (row) => row.note || '—' },
  {
    title: '操作',
    key: 'actions',
    render: (row) => row.status === 'done'
      ? `${new Date(row.completed_at).toLocaleDateString()} 完成`
      : h(NSpace, { size: 'small' }, {
        default: () => [
          h(NButton, { size: 'small', type: 'success', onClick: () => markDoneRow(row) }, { default: () => '点击完成' }),
          h(NButton, { size: 'small', text: true, onClick: () => cancelRow(row) }, { default: () => '取消' }),
        ],
      }),
  },
])

async function markDoneRow(row) {
  try {
    await markRestockDone(row.id)
    await loadRestock()
  } catch (err) {
    message.error(err.response?.data?.detail || '操作失败')
  }
}

async function onShortfallChange(row, v) {
  const prev = row.shortfall_qty
  // Optimistic local update so the input keeps the typed value during the round-trip.
  row.shortfall_qty = v
  try {
    await updateRestockShortfall(row.id, v)
  } catch (err) {
    row.shortfall_qty = prev
    message.error(err.response?.data?.detail || '保存差额失败')
  }
}

async function cancelRow(row) {
  try {
    await deleteRestock(row.id)
    await loadRestock()
  } catch (err) {
    message.error(err.response?.data?.detail || '操作失败')
  }
}

const manualRestockShow = ref(false)
const manualRestockPartId = ref(null)
const manualRestockShortfall = ref(null)
const manualRestockNote = ref('')
const manualRestockSaving = ref(false)

function openManualRestockModal() {
  manualRestockPartId.value = null
  manualRestockShortfall.value = null
  manualRestockNote.value = ''
  manualRestockShow.value = true
}

async function saveManualRestock() {
  if (!manualRestockPartId.value) {
    message.warning('请选择配件')
    return
  }
  manualRestockSaving.value = true
  try {
    const { data: rec } = await createRestock({
      part_id: manualRestockPartId.value,
      handcraft_order_id: order.value.id,
      source: 'manual',
      note: manualRestockNote.value || null,
    })
    if (manualRestockShortfall.value != null) {
      await updateRestockShortfall(rec.id, manualRestockShortfall.value)
    }
    manualRestockShow.value = false
    await loadRestock()
  } catch (err) {
    message.error(err.response?.data?.detail || '添加失败')
  } finally {
    manualRestockSaving.value = false
  }
}

const loadData = async () => {
  const id = route.params.id
  const results = await Promise.all([loadParts(), getHandcraft(id), getHandcraftParts(id)])
  const oRes = results[1]
  const iRes = results[2]
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
    color: partMap.value[i.part_id]?.color || '',
  }))
  pendingDeliveryImages.value = pendingDeliveryImages.value.filter((image) => !order.value.delivery_images.includes(image))
  if (!isPending()) {
    stopEditingCell()
  }
  // Refresh picking weights map so the parts table 重量 column reads from
  // handcraft_picking_weight (the new system of record post-Task 7).
  await loadPickingWeights()
  await loadRestock()
}

const { sending, doSend } = useSendWithStockSupplement({
  orderId: computed(() => route.params.id),
  sendApi: sendHandcraft,
  supplementApi: supplementAndSendHandcraft,
  onSuccess: loadData,
  message,
  dialog,
})

const doDownloadExcel = async () => {
  await downloadExportFile('xlsx', downloadingExcel, downloadHandcraftExcel, 'Excel 下载失败')
}

const doDownloadPdf = async () => {
  await downloadExportFile('pdf', downloadingPdf, downloadHandcraftPdf, 'PDF 下载失败')
}

const downloadExportFile = async (extension, loadingRef, request, errorText) => {
  if (!order.value) return
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
  } catch (err) {
    let detail = errorText
    // Server errors arrive as Blob (responseType="blob"); pull the JSON detail.
    if (err?.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const parsed = JSON.parse(text)
        if (parsed?.detail) detail = parsed.detail
      } catch { /* fall back to errorText */ }
    } else if (err?.response?.data?.detail) {
      detail = err.response.data.detail
    }
    message.error(detail)
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
  const supplierName = sanitizeFilenamePart(currentOrder.supplier_name) || '未命名手工厂'
  const shortDate = formatShortDate(currentOrder.created_at)
  // PDF filename gets a `_<receipt_code>` suffix so suppliers can match the
  // file back to the receipt — mirrors services/plating_export.py
  // build_export_filename. Excel keeps the old format (backend doesn't pass
  // receipt_code to it either, by design).
  const code = (currentOrder.receipt_code || '').trim()
  const suffix = code && extension === 'pdf' ? `_${code}` : ''
  return `发出_${supplierName}_${shortDate}${suffix}.${extension}`
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

// --- Picking simulation ---
const pickingModalShow = ref(false)
function openPickingSimulation() {
  pickingModalShow.value = true
}

// --- Cutting stats ---
const cuttingStatsVisible = ref(false)
const cuttingStatsLoading = ref(false)
const cuttingStatsData = ref([])
const cuttingStatsPdfLoading = ref(false)

const cuttingStatsColumns = [
  { title: '编号', key: 'part_id', width: 160 },
  {
    title: '配件',
    key: 'part_name',
    render(row) {
      const children = []
      if (row.part_image) {
        children.push(h('img', {
          src: row.part_image,
          style: 'width: 32px; height: 32px; object-fit: cover; border-radius: 4px; margin-right: 8px; vertical-align: middle;',
        }))
      }
      children.push(h('span', { style: 'vertical-align: middle;' }, row.part_name))
      if (row.sources && row.sources.length > 1) {
        children.push(
          h(NTooltip, { trigger: 'hover' }, {
            trigger: () => h('span', {
              style: 'display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: #f0a020; color: #fff; font-size: 11px; font-weight: 700; text-align: center; line-height: 16px; margin-left: 6px; vertical-align: middle; cursor: default;',
            }, '!'),
            default: () => row.sources.map((s) =>
              h('div', { key: s.label }, `${s.label} × ${s.qty}`),
            ),
          }),
        )
      }
      return h('span', { style: 'display: inline-flex; align-items: center;' }, children)
    },
  },
  {
    title: '裁剪长度',
    key: 'cut_length_cm',
    width: 100,
    render(row) { return `${row.cut_length_cm}cm` },
  },
  { title: '裁剪数量', key: 'qty', width: 90 },
  {
    title: '总长度',
    key: 'total_length',
    width: 100,
    render(row) {
      const meters = row.cut_length_cm * row.qty / 100
      const rounded = Math.ceil(parseFloat((meters * 10).toFixed(6))) / 10
      return h('span', { style: 'color: #7b2ff2; font-weight: 600;' }, `${rounded}m`)
    },
  },
]

async function openCuttingStatsModal() {
  cuttingStatsVisible.value = true
  cuttingStatsLoading.value = true
  try {
    const { data } = await getHandcraftCuttingStats(order.value.id)
    cuttingStatsData.value = data.items || []
  } catch (_) {
    message.error('获取裁剪统计失败')
    cuttingStatsData.value = []
  } finally {
    cuttingStatsLoading.value = false
  }
}

async function doCuttingStatsPdfExport() {
  cuttingStatsPdfLoading.value = true
  try {
    const { data } = await downloadHandcraftCuttingStatsPdf(order.value.id)
    const url = window.URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `裁剪统计_${order.value.id}.pdf`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (_) {
    message.error('PDF 下载失败')
  } finally {
    cuttingStatsPdfLoading.value = false
  }
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
        await changeOrderStatus({ order_id: order.value.id, order_type: 'handcraft', new_status: newStatus })
        loadingMsg.destroy()
        message.success(`状态已更新为${newLabel}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        await loadData()
      }
    },
  })
}

const openAddModal = () => {
  addForm.value = { part_id: null, qty: 1, unit: '个', weight: null, weight_unit: 'kg', note: '' }
  addModalTab.value = 'single'
  addModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    addForm.value.unit = found.unit
  } else {
    addForm.value.unit = '个'
  }
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addSubmitting.value = true
  try {
    await addHandcraftPart(route.params.id, addForm.value)
    message.success('明细已添加')
    addModalVisible.value = false
    await loadData()
  } finally {
    addSubmitting.value = false
  }
}

const attachRecentBatch = async () => {
  const payload = recentAttachPayload.value
  if (payload.rows.length === 0 || payload.hasZeroQty) return

  attachSubmitting.value = true
  try {
    const parts = payload.rows.map((row) => ({
      part_id: row.part_id,
      qty: row.qty,
      unit: row.unit,
    }))
    const { okNew, okUpd, failures } = await attachPartsToOrder(route.params.id, parts)

    failures.forEach((f) => {
      message.error(`${f.part_id} 加入失败：${f.detail}`)
    })

    if (okNew + okUpd > 0) {
      message.success(`已新增 ${okNew} 项，累加 ${okUpd} 项${failures.length > 0 ? `（${failures.length} 项失败）` : ''}`)
      addModalVisible.value = false
      await loadData()
    }
  } catch (err) {
    if (err?.code === 'NOT_PENDING') {
      message.error(err.message)
    } else {
      throw err
    }
  } finally {
    attachSubmitting.value = false
  }
}

const openEditModal = (row) => {
  editForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
  }
  editModalVisible.value = true
}

const doEditItem = async () => {
  editSubmitting.value = true
  try {
    const { id, ...body } = editForm.value
    await updateHandcraftPart(route.params.id, id, body)
    message.success('修改已保存')
    editModalVisible.value = false
    await loadData()
  } finally {
    editSubmitting.value = false
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
        await deleteHandcraftPart(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
      }
    },
  })
}

const doDeleteJewelryItem = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除产出 ${row.display_name || row.display_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftJewelry(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (e) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

const isPending = () => order.value?.status === 'pending'
const normalizeEditableValue = (value) => (value || '').trim()
const mergeDeliveryImages = (...groups) => [...new Set(groups.flat().filter(Boolean))]

const persistDeliveryImages = async (nextImages, successText) => {
  if (!order.value) return
  deliveryImagesSaving.value = true
  try {
    const { data } = await updateHandcraftDeliveryImages(order.value.id, nextImages)
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
    message.warning('图片已上传，但写入手工单失败，可点击“重试保存”继续')
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
      '待保存图片已写入手工单',
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

const cellKeyOf = (field, row) => `${field}:${row.id}`

const focusEditingCellInput = () => {
  nextTick(() => {
    cellInputRef.value?.focus?.()
  })
}

const startEditCell = (field, row) => {
  if (!isPending()) return
  editingCellKey.value = cellKeyOf(field, row)
  editingCellValue.value = row[field] || ''
  focusEditingCellInput()
}

const stopEditingCell = (field = null, row = null) => {
  if (field && row && editingCellKey.value !== cellKeyOf(field, row)) return
  editingCellKey.value = ''
  editingCellValue.value = ''
}

const saveCell = async (field, row) => {
  const currentCellKey = cellKeyOf(field, row)
  if (editingCellKey.value !== currentCellKey || savingCellKey.value === currentCellKey) return

  const nextValue = normalizeEditableValue(editingCellValue.value)
  const currentValue = normalizeEditableValue(row[field])
  if (nextValue === currentValue) {
    stopEditingCell(field, row)
    return
  }

  savingCellKey.value = currentCellKey
  try {
    if (field === 'color') {
      const { data } = await updatePart(row.part_id, { color: nextValue || null })
      partMap.value = {
        ...partMap.value,
        [row.part_id]: data,
      }
      items.value.forEach((item) => {
        if (item.part_id === row.part_id) {
          item.color = data.color || ''
        }
      })
    } else {
      const { data } = await updateHandcraftPart(route.params.id, row.id, { [field]: nextValue })
      row[field] = data[field] || ''
    }
    message.success(nextValue ? `${field === 'color' ? '颜色' : '备注'}已保存` : `${field === 'color' ? '颜色' : '备注'}已清空`)
    stopEditingCell(field, row)
  } finally {
    if (savingCellKey.value === currentCellKey) {
      savingCellKey.value = ''
    }
  }
}

const onCellInputKeydown = (event, field, row) => {
  if (event.key !== 'Enter') return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void saveCell(field, row)
}

const renderEditableCell = (field, row, emptyLabel) => {
  const currentCellKey = cellKeyOf(field, row)
  const isEditing = editingCellKey.value === currentCellKey
  const isSaving = savingCellKey.value === currentCellKey
  const text = row[field] || ''

  if (isEditing) {
    return h(NInput, {
      ref: cellInputRef,
      value: editingCellValue.value,
      size: 'small',
      placeholder: '输入内容后按回车或点击空白处保存',
      disabled: isSaving,
      autofocus: true,
      'onUpdate:value': (value) => { editingCellValue.value = value },
      onBlur: () => { void saveCell(field, row) },
      onKeydown: (event) => onCellInputKeydown(event, field, row),
    })
  }

  if (!text) {
    if (!isPending()) {
      return h('span', { style: 'color: #999;' }, '-')
    }
    return h(
      NButton,
      {
        text: true,
        type: 'primary',
        size: 'small',
        onClick: () => startEditCell(field, row),
      },
      {
        icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
        default: () => emptyLabel,
      },
    )
  }

  return h(
    'span',
    {
      title: text,
      style: [
        'display: inline-block',
        'max-width: 220px',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'white-space: nowrap',
        'vertical-align: bottom',
        isPending() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: isPending() ? () => startEditCell(field, row) : undefined,
    },
    text,
  )
}

// --- Jewelry items ---
const jewelryItems = ref([])
const jewelryMap = ref({})
const breakdownGroups = ref([])

const loadJewelries = async () => {
  try {
    const { data } = await getHandcraftJewelries(route.params.id)
    jewelryItems.value = data.map((j) => {
      if (j.part_id) {
        return {
          ...j,
          output_type: '配件',
          display_id: j.part_id,
          display_name: j.part_name || partMap.value[j.part_id]?.name || j.part_id,
          display_image: j.part_image || partMap.value[j.part_id]?.image || '',
        }
      }
      return {
        ...j,
        output_type: '饰品',
        display_id: j.jewelry_id,
        display_name: j.jewelry_name || jewelryMap.value[j.jewelry_id]?.name || j.jewelry_id,
        display_image: j.jewelry_image || jewelryMap.value[j.jewelry_id]?.image || '',
      }
    })
  } catch (_) {
    jewelryItems.value = []
  }
}

const loadBreakdown = async () => {
  try {
    const { data } = await getHandcraftJewelryBreakdown(route.params.id)
    breakdownGroups.value = data || []
  } catch (_) {
    breakdownGroups.value = []
  }
}

// --- Order Link (parts) ---
const orderOptions = ref([])
const partItemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]
const jewelryItemOrderLinks = ref({}) // itemId -> [{order_id, customer_name, link_id}]

const linkModalVisible = ref(false)
const linkForm = ref({ itemId: null, partId: null, orderId: null, todoItemId: null })
const linkTodoItems = ref([])
const linkTodoLoading = ref(false)
const linkSubmitting = ref(false)

const jewelryLinkModalVisible = ref(false)
const jewelryLinkItemId = ref(null)
const jewelryLinkOrderId = ref(null)
const jewelryLinkSubmitting = ref(false)

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

const loadPartItemOrderLinks = async () => {
  const map = {}
  await Promise.all(items.value.map(async (item) => {
    try {
      const { data } = await getHandcraftPartOrders(route.params.id, item.id)
      map[item.id] = data
    } catch (_) {
      map[item.id] = []
    }
  }))
  partItemOrderLinks.value = map
}

const loadJewelryItemOrderLinks = async () => {
  const map = {}
  await Promise.all(jewelryItems.value.map(async (item) => {
    try {
      const { data } = await getHandcraftJewelryOrders(route.params.id, item.id)
      map[item.id] = data
    } catch (_) {
      map[item.id] = []
    }
  }))
  jewelryItemOrderLinks.value = map
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

const doCreatePartLink = async () => {
  if (!linkForm.value.todoItemId) return
  linkSubmitting.value = true
  try {
    await createLink(linkForm.value.orderId, {
      order_todo_item_id: linkForm.value.todoItemId,
      handcraft_part_item_id: linkForm.value.itemId,
    })
    message.success('关联成功')
    linkModalVisible.value = false
    await loadPartItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    linkSubmitting.value = false
  }
}

const openJewelryLinkModal = (row) => {
  jewelryLinkItemId.value = row.id
  jewelryLinkOrderId.value = null
  jewelryLinkModalVisible.value = true
  loadOrderOptions()
}

const doCreateJewelryLink = async () => {
  if (!jewelryLinkOrderId.value || !jewelryLinkItemId.value) return
  jewelryLinkSubmitting.value = true
  try {
    await createLink(jewelryLinkOrderId.value, {
      order_id: jewelryLinkOrderId.value,
      handcraft_jewelry_item_id: jewelryLinkItemId.value,
    })
    message.success('关联成功')
    jewelryLinkModalVisible.value = false
    await loadJewelryItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '关联失败')
  } finally {
    jewelryLinkSubmitting.value = false
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
      handcraft_part_item_ids: allItemIds,
    })
    const msg = [`成功关联 ${data.linked} 项`]
    if (data.skipped.length > 0) {
      msg.push(`跳过: ${data.skipped.join(', ')}`)
    }
    message.success(msg.join('，'))
    batchLinkModalVisible.value = false
    await loadPartItemOrderLinks()
  } catch (e) {
    message.error(e.response?.data?.detail || '批量关联失败')
  } finally {
    batchLinkSubmitting.value = false
  }
}

const doUnlinkPartItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftPartOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadPartItemOrderLinks()
      } catch (_) {}
    },
  })
}

const doUnlinkJewelryItem = (itemId, link) => {
  dialog.warning({
    title: '解除关联',
    content: `确认解除与订单「${link.order_id}」的关联？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftJewelryOrderLink(route.params.id, itemId, link.link_id)
        message.success('已解除关联')
        await loadJewelryItemOrderLinks()
      } catch (_) {}
    },
  })
}

const renderPartOrderLinkCell = (row) => {
  const links = partItemOrderLinks.value[row.id] || []
  if (links.length === 0) {
    return h(NButton, {
      size: 'small', text: true, type: 'primary',
      onClick: () => openLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny', quaternary: true, type: 'error', style: 'padding: 0 2px;',
        onClick: () => doUnlinkPartItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openLinkModal(row) }, { default: () => '+' }),
  ])
}

const renderJewelryOrderLinkCell = (row) => {
  const links = jewelryItemOrderLinks.value[row.id] || []
  if (links.length === 0) {
    return h(NButton, {
      size: 'small', text: true, type: 'primary',
      onClick: () => openJewelryLinkModal(row),
    }, { default: () => '关联订单' })
  }
  return h('div', { style: 'display: flex; flex-wrap: wrap; gap: 4px; align-items: center;' }, [
    ...links.map((link) => h('span', {
      style: 'display: inline-flex; align-items: center; gap: 2px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 4px; padding: 1px 6px; font-size: 12px;',
    }, [
      h('span', null, link.order_id),
      h(NButton, {
        size: 'tiny', quaternary: true, type: 'error', style: 'padding: 0 2px;',
        onClick: () => doUnlinkJewelryItem(row.id, link),
      }, { default: () => '×' }),
    ])),
    h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openJewelryLinkModal(row) }, { default: () => '+' }),
  ])
}

const partStatusLabel = { '未送出': '未送出', '制作中': '制作中', '已收回': '已收回' }
const partStatusBadge = { '未送出': 'badge-gray', '制作中': 'badge-blue', '已收回': 'badge-green' }

// Buffer rule mirrors backend services/handcraft.py::HANDCRAFT_BUFFER_RULES.
// Keep in sync if the backend rule changes.
const BUFFER_RULES = {
  small:  { ratio: 0.02, floor: 50 },
  medium: { ratio: 0.01, floor: 15 },
}

const resolveBufferRule = (part) => {
  const tier = part?.size_tier || 'small'
  const tierRule = BUFFER_RULES[tier] || BUFFER_RULES.small
  const ratio = part?.buffer_ratio_override != null
    ? Number(part.buffer_ratio_override)
    : tierRule.ratio
  const floor = part?.buffer_floor_override != null
    ? Number(part.buffer_floor_override)
    : tierRule.floor
  const isOverridden = part?.buffer_ratio_override != null || part?.buffer_floor_override != null
  return { tier, ratio, floor, isOverridden }
}

// Quantize float to 4 decimals — matches backend Numeric(10,4) precision.
// Used on theoretical AND t * ratio, since `100 * 0.01 = 1.0000000000000002`
// would otherwise drift past `ceil`.
const quantize4 = (n) => Math.round(n * 10000) / 10000

const computeSuggestedQty = (row) => {
  const theo = row?.bom_qty
  if (!theo || theo <= 0 || !row?.part_id) return null
  const part = partMap.value[row.part_id]
  const { ratio, floor } = resolveBufferRule(part)
  const t = quantize4(theo)
  const buffer = Math.ceil(Math.max(floor, quantize4(t * ratio)))
  return Math.ceil(t) + buffer
}

const buildSuggestedTooltip = (row) => {
  const theo = row?.bom_qty
  if (!theo || theo <= 0 || !row?.part_id) return ''
  const part = partMap.value[row.part_id]
  const { tier, ratio, floor, isOverridden } = resolveBufferRule(part)
  const t = quantize4(theo)
  const tr = quantize4(t * ratio)
  const buffer = Math.ceil(Math.max(floor, tr))
  const ratioCalc = tr.toFixed(2)
  const winner = floor >= tr ? 'floor 兜底' : '百分比放大'
  const tierLabel = tier === 'small' ? '小件' : '中件'
  const sourceLabel = isOverridden ? `${tierLabel}（自定义）` : `${tierLabel}规则`
  const suggested = computeSuggestedQty(row)
  const ratioDisplay = (ratio * 100).toFixed(2).replace(/\.?0+$/, '')
  return `${sourceLabel}: max(${floor}, 理论×${ratioDisplay}%) | 计算: max(${floor}, ${ratioCalc}) = ${buffer} (${winner}) | 建议: ceil(${t}) + ${buffer} = ${suggested}`
}

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 160 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, partMap.value[row.part_id]?.is_composite ? '组合' : null),
  },
  {
    title: '颜色',
    key: 'color',
    minWidth: 140,
    render: (row) => renderEditableCell('color', row, '添加颜色'),
  },
  {
    title: '发出数量',
    key: 'qty',
    render: (row) => {
      const suggested = computeSuggestedQty(row)
      const planned = row.qty
      const override = row.actual_qty
      const hasOverride = override != null && Number(override) !== Number(planned)
      const displayed = override ?? planned

      const mainContent = hasOverride
        ? [
            h('span', { style: 'color: #1a8917; font-weight: 600;' }, displayed),
            h('span', { style: 'color: #999; margin-left: 4px; font-size: 12px;' }, `(原 ${planned})`),
          ]
        : [h('span', null, displayed ?? '-')]

      if (suggested == null) {
        return h('span', { style: 'white-space: nowrap; font-variant-numeric: tabular-nums;' }, mainContent)
      }

      return h(NTooltip, { trigger: 'hover' }, {
        trigger: () => h('span', { style: 'white-space: nowrap; cursor: help; font-variant-numeric: tabular-nums;' }, [
          ...mainContent,
          h('span', { style: 'color: #1890ff; margin-left: 4px; font-size: 13px;' }, [
            '（建议 ',
            h('span', { style: 'font-weight: 700; font-size: 14px;' }, suggested),
            '）',
          ]),
        ]),
        default: () => buildSuggestedTooltip(row),
      })
    },
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
    render: (r) => h('span', { class: `badge ${partStatusBadge[r.status] || 'badge-gray'}` }, `• ${partStatusLabel[r.status] || r.status || '未送出'}`),
  },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  {
    title: '重量',
    key: 'weight',
    width: 160,
    render: (row) => {
      const pickRows = pickingPartsByItemId.value[row.id] ?? []
      const isComposite = !!partMap.value[row.part_id]?.is_composite

      if (isComposite) {
        // Composite: SUM of all atom weights; read-only.
        // Atomic weight inputs live in the picking simulation modal.
        if (pickRows.length === 0) return '—'
        const totalKg = pickRows.reduce((s, r) => s + toKg(r.weight, r.weight_unit), 0)
        if (totalKg === 0) return '—'
        return h(NTooltip, { trigger: 'hover' }, {
          trigger: () => h('span', { style: 'color:#888;cursor:help' }, `${totalKg.toFixed(3)} kg（合计·只读）`),
          default: () => '组合配件请在配货模拟中按 atom 输入',
        })
      }

      // Atomic: single picking row matches (part_item_id, atom_part_id == row.part_id).
      const r = pickRows.find((x) => x.atom_part_id === row.part_id) ?? null
      const currentWeight = r?.weight ?? null
      const currentUnit = r?.weight_unit || 'kg'

      if (!isPending()) {
        return currentWeight != null ? `${currentWeight} ${currentUnit}` : '—'
      }

      // Editable atomic. Local state decouples the input from row.weight (legacy
      // column, now always null). After save we reload pickingPartsByItemId
      // which triggers a re-render with the persisted value.
      const localState = { weight: currentWeight, weight_unit: currentUnit }
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NInputNumber, {
          value: localState.weight,
          size: 'small',
          style: 'width:80px',
          min: 0,
          precision: 4,
          showButton: false,
          placeholder: '重量',
          'onUpdate:value': (v) => { localState.weight = v },
          onBlur: async () => {
            await updateHandcraftPart(route.params.id, row.id, {
              weight: localState.weight,
              weight_unit: localState.weight_unit,
            })
            await loadPickingWeights()
          },
        }),
        h(NSelect, {
          value: localState.weight_unit,
          size: 'small',
          style: 'width:55px',
          options: [{ label: 'kg', value: 'kg' }, { label: 'g', value: 'g' }],
          'onUpdate:value': async (v) => {
            localState.weight_unit = v
            await updateHandcraftPart(route.params.id, row.id, {
              weight_unit: v,
              weight: localState.weight,
            })
            await loadPickingWeights()
          },
        }),
      ])
    },
  },
  {
    title: '备注',
    key: 'note',
    minWidth: 240,
    render: (row) => renderEditableCell('note', row, '添加备注'),
  },
  {
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => renderPartOrderLinkCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: (row) => {
      const pending = isPending()
      const editBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                disabled: !pending,
                style: 'margin-right: 6px;',
                onClick: pending ? () => openEditModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                type: 'error',
                disabled: !pending,
                onClick: pending ? () => doDeleteItem(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '当前单子进行中/已完成，不允许删除',
        },
      )
      const btns = [editBtn, deleteBtn]
      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

const jewelryColumns = [
  {
    title: '类型',
    key: 'output_type',
    width: 60,
    render: (row) => h(NTag, { size: 'small', type: row.part_id ? 'warning' : 'info' }, () => row.output_type || '饰品'),
  },
  { title: '编号', key: 'display_id', width: 110, render: (row) => row.display_id || row.jewelry_id },
  {
    title: '名称',
    key: 'display_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.display_name, row.display_image, row.display_name, 40, row.output_type === '配件' && partMap.value[row.part_id]?.is_composite ? '组合' : null),
  },
  {
    title: '数量',
    key: 'qty',
    width: 70,
    render: (r) => h('span', { style: 'font-variant-numeric: tabular-nums; display: block; text-align: right; padding-right: 4px;' }, String(r.qty ?? 0)),
  },
  {
    title: '已收回',
    key: 'received_qty',
    width: 110,
    render: (r) => {
      const received = (r.received_qty ?? 0) - (r.loss_qty ?? 0)
      const total = r.qty ?? 0
      const pct = total > 0 ? Math.min(100, Math.round((received / total) * 100)) : 0
      const barColor = pct >= 100 ? '#1E7A5A' : (pct > 0 ? '#4CAF8A' : '#ECEDEF')
      return h('div', { style: 'min-width: 90px;' }, [
        h('div', { style: 'display: flex; justify-content: flex-start; font-variant-numeric: tabular-nums; font-size: 12px; margin-bottom: 3px;' }, [
          h('span', { style: 'color: #1A1D21; font-weight: 600;' }, String(received)),
          h('span', { style: 'color: #8B9096;' }, `/${total}`),
        ]),
        h('div', { style: 'height: 4px; background: #ECEDEF; border-radius: 2px; overflow: hidden;' }, [
          h('div', { style: `height: 100%; width: ${pct}%; background: ${barColor}; border-radius: 2px; transition: width 0.3s;` }),
        ]),
      ])
    },
  },
  {
    title: '损耗',
    key: 'loss_qty',
    width: 60,
    render: (r) => r.loss_qty ? h(NTag, { type: 'warning', size: 'small' }, { default: () => r.loss_qty }) : null,
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
    render: (r) => h('span', { class: `badge ${partStatusBadge[r.status] || 'badge-gray'}` }, `• ${partStatusLabel[r.status] || r.status || '未送出'}`),
  },
  {
    title: '重量',
    key: 'weight',
    width: 140,
    render: (row) => {
      if (!isPending()) {
        return row.weight != null ? `${row.weight} ${row.weight_unit || 'g'}` : '—'
      }
      return h('div', { style: 'display:flex;gap:4px;align-items:center' }, [
        h(NInputNumber, {
          value: row.weight ?? null,
          size: 'small',
          style: 'width:80px',
          min: 0,
          placeholder: '重量',
          'onUpdate:value': (v) => { row.weight = v },
          onBlur: () => { updateHandcraftJewelry(route.params.id, row.id, { weight: row.weight }) },
        }),
        h(NSelect, {
          value: row.weight_unit || 'g',
          size: 'small',
          style: 'width:55px',
          options: [{ label: 'g', value: 'g' }, { label: 'kg', value: 'kg' }],
          'onUpdate:value': (v) => { row.weight_unit = v; updateHandcraftJewelry(route.params.id, row.id, { weight_unit: v }) },
        }),
      ])
    },
  },
  {
    title: '关联订单',
    key: 'order_link',
    minWidth: 140,
    render: (row) => renderJewelryOrderLinkCell(row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: (row) => {
      const pending = order.value?.status === 'pending'
      const btns = []
      if (pending) {
        btns.push(h(
          NTooltip,
          { disabled: pending, trigger: 'hover' },
          {
            trigger: () =>
              h(NButton, {
                size: 'small',
                type: 'error',
                onClick: () => doDeleteJewelryItem(row),
              }, { default: () => '删除' }),
            default: () => '当前单子进行中/已完成，不允许删除',
          },
        ))
      }
      const gap = row.qty - (row.received_qty || 0)
      if (gap > 0 && row.status === '制作中') {
        btns.push(h(NButton, {
          size: 'small',
          type: 'warning',
          onClick: () => openLossModal(row, 'jewelry'),
        }, { default: () => '确认损耗' }))
      }
      if (btns.length === 0) return null
      return h(NSpace, { size: 'small' }, { default: () => btns })
    },
  },
]

onMounted(async () => {
  try {
    const { data: jewels } = await listJewelries()
    jewels.forEach((j) => { jewelryMap.value[j.id] = j })
    await loadData()
    listSuppliers({ type: 'handcraft' }).then(({ data }) => {
      supplierOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
    })
    await Promise.all([loadJewelries(), loadPartItemOrderLinks(), loadBreakdown()])
    await loadJewelryItemOrderLinks()
  } finally {
    loading.value = false
  }
})

async function onBreakdownSaved() {
  // Await both reloads so the parent's breakdownGroups + jewelryItems are
  // settled before the modal's saving spinner clears — otherwise the user
  // can see stale chips for a frame.
  await Promise.all([loadBreakdown(), loadJewelries()])
}

async function copyReceiptCode() {
  const code = order.value?.receipt_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    message.success(`已复制回执码 ${code}`)
  } catch {
    message.error('复制失败')
  }
}

</script>

<style scoped>
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
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #eadbc1;
  background: linear-gradient(180deg, #fffdf7, #f7f0e1);
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
  border: 1px dashed #d6b98d;
  border-radius: 14px;
  background: linear-gradient(180deg, #fffaf0, #f6eedc);
  color: #8a5a17;
  font-size: 30px;
  line-height: 1;
  cursor: pointer;
}

.delivery-image-add:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.delivery-images-meta {
  color: #8a6b39;
  font-size: 12px;
}

.export-excel-btn {
  background: #469c66;
  color: #fff;
  border-color: #469c66;
}

.export-excel-btn:hover,
.export-excel-btn:focus {
  background: #3d8959;
  color: #fff;
  border-color: #3d8959;
}

.export-pdf-btn {
  background: #d84243;
  color: #fff;
  border-color: #d84243;
}

.export-pdf-btn:hover,
.export-pdf-btn:focus {
  background: #bf3a3b;
  color: #fff;
  border-color: #bf3a3b;
}

:deep(.restock-row-done) {
  opacity: 0.6;
  background: #fafafa;
}

.receipt-code {
  font-family: "SF Mono", Menlo, monospace;
  font-weight: 600;
  letter-spacing: 0.1em;
  font-size: 14px;
  padding: 2px 8px;
  background: #f5f5f8;
  border-radius: 3px;
}
.receipt-code__hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  margin-left: 8px;
}

.breakdown-group {
  padding: 10px 0;
  border-bottom: 1px solid #e8e8ec;
}
.breakdown-group:last-child { border-bottom: none; }
.breakdown-group__head {
  display: flex;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 6px;
}
.breakdown-group__id {
  font-family: "SF Mono", Menlo, monospace;
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  padding: 2px 6px;
  background: #f5f5f8;
  border-radius: 3px;
}
.breakdown-group__name {
  font-weight: 500;
  font-size: 15px;
}
.breakdown-group__qty {
  margin-left: auto;
  margin-right: 12px;
  color: rgba(0, 0, 0, 0.65);
  font-size: 13px;
}
.breakdown-group__qty strong {
  font-family: "SF Mono", Menlo, monospace;
  color: rgba(0, 0, 0, 0.88);
}
.breakdown-group__chips {
  padding-left: 4px;
}

.section-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
}

.section-chevron {
  display: inline-block;
  width: 12px;
  text-align: center;
  color: #999;
}

/* ── Page header ──────────────────────────────────────────────── */
.hc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 4px;
}

.hc-head__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-back {
  margin-bottom: 2px;
  font-size: 13px;
}
.page-back :deep(.n-button__content) { color: #8B9096; transition: color 0.15s; }
.page-back:hover :deep(.n-button__content) { color: #1E7A5A; }

.hc-status-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.hc-status-pill--emerald {
  background: #E6F2EC;
  color: #1E7A5A;
}

.hc-status-pill--amber {
  background: #FBF0DC;
  color: #B7791F;
}

.hc-status-pill--gray {
  background: #F1F2F4;
  color: #6B7280;
}

/* ── Status stepper ───────────────────────────────────────────── */
.hc-stepper {
  display: flex;
  align-items: center;
  margin: 20px 0 4px;
}

.hc-step {
  display: flex;
  align-items: center;
  gap: 9px;
}

.hc-step__dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.hc-step--done .hc-step__dot {
  background: #1E7A5A;
  color: #fff;
}

.hc-step--cur .hc-step__dot {
  background: #1E7A5A;
  color: #fff;
  box-shadow: 0 0 0 4px #E6F2EC;
}

.hc-step--todo .hc-step__dot {
  background: #EDEFF1;
  color: #AEB3B8;
}

.hc-step__lab {
  font-size: 13px;
  font-weight: 600;
}

.hc-step--todo .hc-step__lab {
  color: #AEB3B8;
  font-weight: 500;
}

.hc-step__sub {
  font-size: 11px;
  color: #8B9096;
  margin-top: 1px;
}

.hc-bar {
  flex: 1;
  height: 2px;
  margin: 0 14px;
  border-radius: 1px;
}

.hc-bar--on { background: #1E7A5A; }
.hc-bar--off { background: #EDEFF1; }

/* ── Summary stat cards ───────────────────────────────────────── */
.hc-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  border: 1px solid #ECEDEF;
  border-radius: 10px;
  margin: 18px 0 4px;
  overflow: hidden;
}

.hc-stat {
  padding: 13px 16px;
  border-right: 1px solid #ECEDEF;
}

.hc-stat:last-child {
  border-right: 0;
}

.hc-stat__k {
  font-size: 10.5px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
}

.hc-stat__v {
  font-size: 23px;
  font-weight: 700;
  letter-spacing: -0.4px;
  margin-top: 5px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.hc-stat__v small {
  font-size: 13px;
  color: #8B9096;
  font-weight: 600;
}

.hc-stat__v--mono {
  font-family: "SF Mono", Menlo, monospace;
}

/* ── Meta strip ───────────────────────────────────────────────── */
.hc-meta {
  display: flex;
  gap: 26px;
  flex-wrap: wrap;
  padding: 14px 0 16px;
  font-size: 13px;
}

.hc-meta__k {
  font-size: 11px;
  color: #8B9096;
}

.hc-meta__v {
  font-weight: 500;
  margin-top: 2px;
}

/* ── Eyebrow section blocks ───────────────────────────────────── */
.hc-sec {
  margin-bottom: 20px;
}

.hc-sec--no-title {
  margin-top: 4px;
}

.hc-sec-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 8px;
  border-bottom: 1px solid #ECEDEF;
  margin-bottom: 12px;
}

.hc-sec-h .t {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: #8B9096;
}

.hc-sec-h .acts {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Small bordered action buttons in section headers */
.hc-sbtn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #1A1D21;
  background: #fff;
  border: 1px solid #ECEDEF;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  white-space: nowrap;
}

.hc-sbtn:hover {
  background: #F4F5F7;
  border-color: #C8CDD3;
}

.hc-sbtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hc-sbtn--primary {
  color: #1E7A5A;
  border-color: #B5D9CA;
  background: #E6F2EC;
}

.hc-sbtn--primary:hover {
  background: #D2EBDF;
  border-color: #1E7A5A;
}

.hc-export-btn--excel:hover { background-color: #1E7A5A !important; color: #fff !important; }
.hc-export-btn--pdf:hover   { background-color: #E5484D !important; color: #fff !important; }
.hc-export-btn--excel:hover :deep(.n-button__content),
.hc-export-btn--pdf:hover :deep(.n-button__content) { color: #fff !important; }

.hc-receipt-copy { cursor: pointer; transition: color 0.15s; }
.hc-receipt-copy:hover { color: #1E7A5A; }
</style>
