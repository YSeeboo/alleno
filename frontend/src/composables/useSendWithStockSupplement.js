import { ref, h } from 'vue'
import { NIcon } from 'naive-ui'
import { CopyOutline } from '@vicons/ionicons5'
import { batchGetStock } from '@/api/inventory'

/**
 * Returns { sending, doSend } for an order page that wants the standard
 * 库存不足 → 一键补进并发出 flow.
 *
 * Caller provides:
 *   orderId       — ref/computed -> string (order id, e.g. 'HC-0042')
 *   sendApi       — (id) => Promise            normal send
 *   supplementApi — (id) => Promise<{ data: { supplemented: {pid: qty} } }>
 *   onSuccess     — () => Promise<void>        e.g. loadData() to refresh
 *   message       — useMessage()
 *   dialog        — useDialog()
 */
export function useSendWithStockSupplement({
  orderId,
  sendApi,
  supplementApi,
  onSuccess,
  message,
  dialog,
}) {
  const sending = ref(false)

  const doSend = async () => {
    sending.value = true
    try {
      await sendApi(orderId.value)
      message.success('已确认发出')
      await onSuccess()
    } catch (e) {
      const detail = e.response?.data?.detail || ''
      if (detail.includes('库存不足')) {
        openShortageDialog(detail)
      } else {
        message.error(detail || '发出失败')
      }
    } finally {
      sending.value = false
    }
  }

  const openShortageDialog = (detail) => {
    const items = parseShortageItems(detail)
    dialog.warning({
      title: '库存不足',
      content: () => renderShortageList(items, message),
      negativeText: '知道了',
      positiveText: '一键补进并发出',
      positiveButtonProps: { type: 'warning' },
      onPositiveClick: () => {
        openConfirmDialog(items)
        return true
      },
    })
  }

  const openConfirmDialog = async (items) => {
    const partIds = items.map(it => it.partId).filter(Boolean)
    let stocks = {}
    try {
      const resp = await batchGetStock('part', partIds)
      stocks = resp.data || {}
    } catch (e) {
      message.error('查询库存失败，请重试')
      return
    }
    const shortages = items
      .map(it => ({ partId: it.partId, gap: it.needed - (stocks[it.partId] ?? 0) }))
      .filter(it => it.gap > 0 && it.partId)

    if (shortages.length === 0) {
      await runSupplementAndSend()
      return
    }
    dialog.warning({
      title: '确认补进库存',
      content: () => renderSupplementPreview(shortages, orderId.value),
      negativeText: '取消',
      positiveText: '确认补进并发出',
      positiveButtonProps: { type: 'primary' },
      onPositiveClick: async () => {
        await runSupplementAndSend()
        return true
      },
    })
  }

  const runSupplementAndSend = async () => {
    sending.value = true
    try {
      const resp = await supplementApi(orderId.value)
      const supplemented = resp.data?.supplemented || {}
      const count = Object.keys(supplemented).length
      const total = Object.values(supplemented).reduce((a, b) => a + Number(b), 0)
      if (count === 0) {
        message.success('库存已足，订单已发出')
      } else {
        message.success(`已补进 ${count} 个配件共 ${total} 件，订单已发出`)
      }
      await onSuccess()
    } catch (e) {
      message.error(e.response?.data?.detail || '补进失败')
    } finally {
      sending.value = false
    }
  }

  return { sending, doSend }
}

/**
 * Parse the backend error "库存不足：part PJ-XX 当前库存 X，需要 Y；…" into
 * structured items. Items the regex can't match end up with NaN current/needed
 * but still surface via raw.
 */
function parseShortageItems(detail) {
  const stripped = String(detail).replace(/^库存不足[：:]?\s*/, '')
  return stripped.split('；').filter(Boolean).map(t => {
    const cleaned = t.replace(/^part\s+/i, '').trim()
    const m = cleaned.match(/^(\S+)\s*当前库存\s*([\d.]+)\s*[,，]\s*需要\s*([\d.]+)/)
    if (!m) {
      const fallbackPartId = (cleaned.match(/^(PJ-\S+)/) || [])[1] || ''
      return { partId: fallbackPartId, current: NaN, needed: NaN, raw: cleaned }
    }
    return {
      partId: m[1],
      current: parseFloat(m[2]),
      needed: parseFloat(m[3]),
      raw: cleaned,
    }
  })
}

function renderShortageList(items, message) {
  return h('ul', { style: 'padding-left: 20px; margin: 0;' }, items.map(it => {
    const partId = it.partId
    const rest = partId ? it.raw.slice(partId.length) : it.raw
    return h('li', { style: 'margin: 4px 0; display: flex; align-items: center; gap: 2px;' }, [
      partId ? [
        h('span', null, partId),
        h('span', {
          style: 'display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; color: #666; background: #f0f0f0; margin: 0 4px; transition: all 0.2s;',
          onMouseenter: (e) => { e.currentTarget.style.background = '#e0e0e0'; e.currentTarget.style.color = '#333' },
          onMouseleave: (e) => { e.currentTarget.style.background = '#f0f0f0'; e.currentTarget.style.color = '#666' },
          onClick: () => {
            navigator.clipboard
              ?.writeText(partId)
              .then(() => message.success('已复制'))
              .catch(() => message.error('复制失败'))
              ?? message.error('复制失败')
          },
        }, [h(NIcon, { size: 14 }, { default: () => h(CopyOutline) })]),
        h('span', null, rest),
      ] : it.raw,
    ])
  }))
}

function renderSupplementPreview(shortages, orderId) {
  const total = shortages.reduce((sum, s) => sum + Number(s.gap), 0)
  return h('div', null, [
    h('p', { style: 'margin: 0 0 8px;' }, '即将为以下配件补进库存：'),
    h('div', {
      style: 'background:#fafbfc;border:1px solid #efeff5;border-radius:3px;padding:10px 14px;margin:8px 0;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13px;line-height:1.9;',
    }, shortages.map(s => h('div', null, [
      h('span', { style: 'color:#36ad6a;font-weight:600;' }, s.partId),
      h('span', { style: 'color:#d03050;font-weight:600;margin-left:6px;' }, `+${s.gap}`),
      h('span', null, ' 件'),
    ]))),
    h('p', { style: 'margin: 6px 0 0; font-size: 13px; color: #666;' }, [
      '共 ',
      h('strong', null, String(shortages.length)),
      ' 个配件，总计补进 ',
      h('strong', null, String(total)),
      ' 件。补进成功后将立即继续发出 ',
      h('strong', null, orderId),
      '。',
    ]),
  ])
}
