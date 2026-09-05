import client from './client'
import type { CodeFormatResult, CodeValidateResult } from '@/types/code'

export function validateCode(code: string) {
  return client.post<CodeValidateResult>('/code/validate', { code })
}

export function formatCode(code: string) {
  return client.post<CodeFormatResult>('/code/format', { code })
}

export function validateSql(code: string) {
  return client.post<CodeValidateResult>('/code/sql-validate', { code })
}

export function formatSql(code: string) {
  return client.post<CodeFormatResult>('/code/sql-format', { code })
}
