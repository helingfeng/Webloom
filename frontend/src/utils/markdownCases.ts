import { statusLabel } from '@/types/testCase'
import type {
  ImportCaseIn,
  ImportModuleIn,
  MindmapNode,
  Requirement,
  TestCase,
  TestModule,
} from '@/types/testCase'

export interface ParsedCases {
  requirementName: string
  modules: ImportModuleIn[]
  looseCases: ImportCaseIn[]
}

// 支持 -、*、+ 以及 1. / 1) / 1、 有序列表
const LIST_RE = /^\s*(?:[-*+]|\d+\s*[.)、])\s+(.*)$/
const PRECOND_PREFIXES = ['前置条件', '前置', '前提条件', '前提']
const EXPECTED_PREFIXES = ['预期结果', '预期', '期望结果', '期望']

function stripPrefix(line: string, prefixes: string[]): string | null {
  for (const p of prefixes) {
    if (line.startsWith(p)) {
      return line.slice(p.length).replace(/^[:：]\s*/, '').trim()
    }
  }
  return null
}

/**
 * 解析 Markdown 文本为测试用例结构：
 * - `#` H1 = 需求名（取第一个）
 * - `##` H2 = 模块
 * - `###` H3 = 用例；直接位于 H1 下的 H3 为无模块用例
 * - 用例正文：`前置/前提` 开头 → 前置条件；`预期/期望` 开头 → 预期结果；
 *   列表项 → 步骤；其他非空行兜底为步骤
 */
export function parseMarkdownCases(text: string): ParsedCases {
  const result: ParsedCases = { requirementName: '', modules: [], looseCases: [] }
  let currentModule: ImportModuleIn | null = null
  let currentCase: ImportCaseIn | null = null

  for (const rawLine of text.split(/\r?\n/)) {
    const trimmed = rawLine.trim()

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      const level = headingMatch[1]!.length
      const title = headingMatch[2]!.trim()
      if (level === 1) {
        if (!result.requirementName && title) result.requirementName = title
        currentModule = null
        currentCase = null
        continue
      }
      if (level === 2) {
        currentModule = { name: title, cases: [] }
        result.modules.push(currentModule)
        currentCase = null
        continue
      }
      if (level === 3) {
        currentCase = { title, precondition: '', steps: [], expected_result: '' }
        if (currentModule) currentModule.cases.push(currentCase)
        else result.looseCases.push(currentCase)
        continue
      }
      if (currentCase && title) currentCase.steps.push(title)
      continue
    }

    if (!trimmed || !currentCase) continue

    const precond = stripPrefix(trimmed, PRECOND_PREFIXES)
    if (precond !== null) {
      currentCase.precondition = precond
      continue
    }
    const expected = stripPrefix(trimmed, EXPECTED_PREFIXES)
    if (expected !== null) {
      currentCase.expected_result = expected
      continue
    }
    const listMatch = trimmed.match(LIST_RE)
    currentCase.steps.push(listMatch ? listMatch[1]!.trim() : trimmed)
  }
  return result
}

export function countParsedCases(parsed: ParsedCases): number {
  return parsed.looseCases.length + parsed.modules.reduce((n, m) => n + m.cases.length, 0)
}

/** 导入预览思维导图：需求 → 模块 → 用例 */
export function buildImportMindmap(parsed: ParsedCases): MindmapNode {
  const root: MindmapNode = { content: parsed.requirementName || '未命名需求', children: [] }
  for (const m of parsed.modules) {
    root.children.push({
      content: m.name,
      children: m.cases.map((c) => ({ content: c.title, children: [] })),
    })
  }
  for (const c of parsed.looseCases) {
    root.children.push({ content: c.title, children: [] })
  }
  return root
}

/** 已有需求思维导图：需求 → 模块 → 用例（带状态标记） */
export function buildRequirementMindmap(
  req: Requirement,
  modules: TestModule[],
  cases: TestCase[],
): MindmapNode {
  const caseNode = (c: TestCase): MindmapNode => ({
    content: `[${statusLabel(c.status)}] ${c.title}`,
    children: [],
  })
  const root: MindmapNode = { content: req.name, children: [] }
  for (const m of modules) {
    root.children.push({
      content: m.name,
      children: cases.filter((c) => c.module_id === m.id).map(caseNode),
    })
  }
  for (const c of cases.filter((c) => c.module_id === null)) {
    root.children.push(caseNode(c))
  }
  return root
}
