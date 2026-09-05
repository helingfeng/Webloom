export interface CodeError {
  line: number
  column: number
  message: string
}

export interface CodeValidateResult {
  ok: boolean
  errors: CodeError[]
}

export interface CodeFormatResult {
  code: string
  changed: boolean
}
