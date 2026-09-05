import { describe, expect, it } from 'vitest'
import { buildImportMindmap, countParsedCases, parseMarkdownCases } from '@/utils/markdownCases'

const SAMPLE = `# 登录需求

### 无模块用例：页面加载

### 直接第二个
- 步骤A

## 账号登录

### 正确登录
前置条件：账号已注册
- 打开登录页
- 输入账号密码
1. 点击登录
预期结果：跳转首页

### 错误登录
前提：账号存在
期望：提示失败
`

describe('parseMarkdownCases', () => {
  it('解析需求名、模块、无模块用例', () => {
    const parsed = parseMarkdownCases(SAMPLE)
    expect(parsed.requirementName).toBe('登录需求')
    expect(parsed.modules).toHaveLength(1)
    expect(parsed.modules[0]!.name).toBe('账号登录')
    expect(parsed.looseCases).toHaveLength(2)
    expect(parsed.looseCases[1]!.steps).toEqual(['步骤A'])
  })

  it('解析前置/预期与步骤（含有序列表）', () => {
    const parsed = parseMarkdownCases(SAMPLE)
    const case1 = parsed.modules[0]!.cases[0]!
    expect(case1.title).toBe('正确登录')
    expect(case1.precondition).toBe('账号已注册')
    expect(case1.steps).toEqual(['打开登录页', '输入账号密码', '点击登录'])
    expect(case1.expected_result).toBe('跳转首页')

    const case2 = parsed.modules[0]!.cases[1]!
    expect(case2.precondition).toBe('账号存在')
    expect(case2.expected_result).toBe('提示失败')
  })

  it('统计用例总数', () => {
    expect(countParsedCases(parseMarkdownCases(SAMPLE))).toBe(4)
    expect(countParsedCases(parseMarkdownCases('# 空需求'))).toBe(0)
  })

  it('构造导入思维导图', () => {
    const parsed = parseMarkdownCases(SAMPLE)
    const map = buildImportMindmap(parsed)
    expect(map.content).toBe('登录需求')
    expect(map.children).toHaveLength(3) // 1 模块 + 2 无模块用例
    expect(map.children[0]!.children).toHaveLength(2)
  })
})
