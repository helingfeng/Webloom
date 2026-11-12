import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ScriptEditor from '../ScriptEditor.vue'
import ParameterValue from '../ParameterValue.vue'
import type { ScriptCreate } from '@/types/script'

vi.mock('../CodeEditor.vue', () => ({ default: { name: 'CodeEditor', template: '<div />' } }))
vi.mock('../RecordDialog.vue', () => ({ default: { name: 'RecordDialog', template: '<div />' } }))

const wrap = { template: '<div><slot /></div>' }
function editor() {
  return mount(ScriptEditor, {
    props: { initialData: { workspace_id: 1, name: '采集脚本', code: 'print("saved")', inputs: [{ name: 'enabled', type: 'boolean', required: true }, { name: 'count', type: 'number', required: true }] } },
    global: {
      plugins: [createPinia()],
      stubs: {
        ElTabs: wrap, ElTabPane: wrap, ElForm: wrap, ElFormItem: wrap, ElTable: { template: '<div />' },
        ElButton: { template: '<button><slot /></button>' }, ElSelect: wrap, ElOption: true, ElInput: true, ElSwitch: true,
        ElInputNumber: true, ElAlert: true, RecordDialog: true,
        CodeEditor: { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
      },
    },
  })
}

describe('script editor run contract', () => {
  it('submits edited code with native false and zero and default global inheritance', async () => {
    const wrapper = editor()
    await wrapper.get('textarea').setValue('print("edited")')
    const fields = wrapper.findAllComponents(ParameterValue)
    fields[0]!.vm.$emit('update:modelValue', false)
    fields[1]!.vm.$emit('update:modelValue', 0)
    const run = wrapper.findAll('button').find(button => button.text() === '保存并运行')!
    await run.trigger('click')
    const payload = wrapper.emitted('run')![0]![0] as { script: ScriptCreate; inputs: Record<string, unknown>; mode: string }
    expect(payload.script.code).toBe('print("edited")')
    expect(payload.script.inherit_global).toBe(true)
    expect(payload.inputs).toEqual({ enabled: false, count: 0 })
    expect(payload.mode).toBe('manual')
    wrapper.unmount()
  })

  it('omits unspecified optional values so server defaults are preserved', async () => {
    const wrapper = editor()
    await wrapper.findAll('button').find(button => button.text() === '保存并运行')!.trigger('click')
    const payload = wrapper.emitted('run')![0]![0] as { inputs: Record<string, unknown> }
    expect(payload.inputs).toEqual({})
    wrapper.unmount()
  })
})
