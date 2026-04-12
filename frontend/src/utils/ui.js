import { h } from 'vue'
import { NImage } from 'naive-ui'

export const BRAND_COLOR = '#FF0000'

/**
 * Format a monetary value: up to 7 decimal places, no trailing zeros, minimum 2 decimals.
 * e.g. 2340 → "2340.00", 1.5 → "1.50", 0.1234567 → "0.1234567"
 */
export function fmtMoney(val) {
  if (val == null) return '-'
  const s = Number(val).toFixed(7)
  // Remove trailing zeros but keep at least 2 decimal places
  const [int, dec] = s.split('.')
  const trimmed = dec.replace(/0+$/, '')
  const final = trimmed.length < 2 ? trimmed.padEnd(2, '0') : trimmed
  return `${int}.${final}`
}

export const fmtPrice = (v) => v == null ? '' : fmtMoney(v)
export const parseNum = (v) => {
  if (v == null || String(v).trim() === '') return null
  const n = Number(String(v).replace(/,/g, ''))
  return n // NaN for truly invalid strings → NInputNumber reverts to previous value
}

export function renderImageThumb(src, alt = '图片', size = 40) {
  const side = `${size}px`
  const boxStyle = {
    width: side,
    height: side,
    borderRadius: '8px',
    border: '1px solid #ffd6d6',
    background: '#fff5f5',
    flexShrink: 0,
    overflow: 'hidden',
  }

  if (src) {
    return h(
      'div',
      { style: boxStyle },
      [h(NImage, {
        src,
        alt,
        width: size,
        height: size,
        objectFit: 'cover',
        style: { display: 'block', cursor: 'zoom-in' },
      })]
    )
  }

  return h(
    'div',
    {
      style: {
        ...boxStyle,
        color: '#d03050',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '12px',
        fontWeight: 600,
      },
    },
    '无图'
  )
}

export function renderNamedImage(name, image, fallback, size = 40, tag = null) {
  const children = [
    renderImageThumb(image, name || fallback || '图片', size),
    h('span', fallback || name || '-'),
  ]
  if (tag) {
    children.push(
      h('span', {
        style: {
          fontSize: '11px',
          lineHeight: '1',
          padding: '2px 6px',
          borderRadius: '3px',
          whiteSpace: 'nowrap',
          fontWeight: '500',
          background: '#e8f4ff',
          color: '#2080f0',
          border: '1px solid #b8deff',
          flexShrink: '0',
        },
      }, tag)
    )
  }
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
      },
    },
    children,
  )
}

export function renderOptionWithImage(option) {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      },
    },
    [
      renderImageThumb(option.image, option.name || option.label, 32),
      h('div', [
        h('div', { style: { fontWeight: 600 } }, option.code || option.value),
        h('div', { style: { color: '#666', fontSize: '12px' } }, [
          option.name || option.label,
          ...(option.badge ? [h('span', {
            style: `margin-left: 4px; font-size: 11px; font-weight: bold; color: #fff; background: ${option.badgeColor || '#999'}; padding: 1px 5px; border-radius: 4px;`,
          }, option.badge)] : []),
        ]),
      ]),
    ]
  )
}
