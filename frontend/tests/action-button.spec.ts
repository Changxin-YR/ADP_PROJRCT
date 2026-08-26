import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ActionButton from '../src/layers/common/ui/ActionButton.vue'

describe('ActionButton', () => {
  it('renders a semantic icon and accessible label', () => {
    const wrapper = mount(ActionButton, {
      props: { icon: 'download', variant: 'secondary' },
      slots: { default: '导出明细' },
    })

    expect(wrapper.get('button').attributes('aria-label')).toBe('导出明细')
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.classes()).toContain('action-button--secondary')
  })

  it('blocks interaction and announces loading', () => {
    const wrapper = mount(ActionButton, {
      props: { loading: true },
      slots: { default: '保存方案' },
    })

    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button').attributes('aria-busy')).toBe('true')
    expect(wrapper.text()).toContain('处理中')
  })
})
