import { h } from 'vue'
import { NImage } from 'naive-ui'

export const BRAND_COLOR = '#FF0000'

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

export function renderNamedImage(name, image, fallback, size = 40) {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
      },
    },
    [
      renderImageThumb(image, name || fallback || '图片', size),
      h('span', fallback || name || '-'),
    ]
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
        h('div', { style: { color: '#666', fontSize: '12px' } }, option.name || option.label),
      ]),
    ]
  )
}
