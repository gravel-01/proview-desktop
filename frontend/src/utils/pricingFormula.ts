export interface PricingFormulaResult {
  ok: boolean
  value: number | null
  error: string
}

type FormulaToken =
  | { type: 'number'; value: number }
  | { type: 'identifier'; value: string }
  | { type: 'operator'; value: '+' | '-' | '*' | '/' }
  | { type: 'paren'; value: '(' | ')' }

export const DEFAULT_PRICING_VARIABLES = [
  'input_tokens',
  'output_tokens',
  'total_tokens',
  'call_count',
  'cache_hit_tokens',
  'cache_miss_tokens',
  'langfuse_cost',
]

export function evaluatePricingFormula(
  formula: string,
  variables: Record<string, number>,
): PricingFormulaResult {
  const expression = formula.trim()
  if (!expression) {
    return { ok: false, value: null, error: '公式为空' }
  }

  try {
    const parser = new FormulaParser(tokenize(expression), variables)
    const value = parser.parse()
    if (!Number.isFinite(value)) {
      return { ok: false, value: null, error: '计算结果不是有效数字' }
    }
    return { ok: true, value, error: '' }
  } catch (error) {
    return {
      ok: false,
      value: null,
      error: error instanceof Error ? error.message : '公式解析失败',
    }
  }
}

function tokenize(expression: string): FormulaToken[] {
  const tokens: FormulaToken[] = []
  let index = 0

  while (index < expression.length) {
    const char = expression[index] || ''
    if (/\s/.test(char)) {
      index += 1
      continue
    }

    if (/[0-9.]/.test(char)) {
      const start = index
      let dotCount = 0
      while (index < expression.length) {
        const current = expression[index] || ''
        if (!/[0-9.]/.test(current)) break
        if (current === '.') dotCount += 1
        index += 1
      }
      const raw = expression.slice(start, index)
      if (dotCount > 1 || raw === '.') {
        throw new Error(`数字格式不正确: ${raw}`)
      }
      tokens.push({ type: 'number', value: Number(raw) })
      continue
    }

    if (/[A-Za-z_]/.test(char)) {
      const start = index
      while (index < expression.length && /[A-Za-z0-9_]/.test(expression[index] || '')) {
        index += 1
      }
      tokens.push({ type: 'identifier', value: expression.slice(start, index) })
      continue
    }

    if (char === '+' || char === '-' || char === '*' || char === '/') {
      tokens.push({ type: 'operator', value: char })
      index += 1
      continue
    }

    if (char === '(' || char === ')') {
      tokens.push({ type: 'paren', value: char })
      index += 1
      continue
    }

    throw new Error(`不支持的字符: ${char}`)
  }

  return tokens
}

class FormulaParser {
  private readonly tokens: FormulaToken[]
  private readonly variables: Record<string, number>
  private index = 0

  constructor(
    tokens: FormulaToken[],
    variables: Record<string, number>,
  ) {
    this.tokens = tokens
    this.variables = variables
  }

  parse() {
    const value = this.parseExpression()
    if (this.peek()) {
      throw new Error('公式末尾存在无法解析的内容')
    }
    return value
  }

  private parseExpression(): number {
    let value = this.parseTerm()
    while (this.matchOperator('+') || this.matchOperator('-')) {
      const operator = this.previous().value
      const right = this.parseTerm()
      value = operator === '+' ? value + right : value - right
    }
    return value
  }

  private parseTerm(): number {
    let value = this.parseFactor()
    while (this.matchOperator('*') || this.matchOperator('/')) {
      const operator = this.previous().value
      const right = this.parseFactor()
      if (operator === '/') {
        if (right === 0) throw new Error('公式中存在除以 0')
        value /= right
      } else {
        value *= right
      }
    }
    return value
  }

  private parseFactor(): number {
    if (this.matchOperator('+')) return this.parseFactor()
    if (this.matchOperator('-')) return -this.parseFactor()

    const token = this.advance()
    if (!token) {
      throw new Error('公式不完整')
    }

    if (token.type === 'number') return token.value
    if (token.type === 'identifier') {
      if (!(token.value in this.variables)) {
        throw new Error(`未知变量: ${token.value}`)
      }
      const value = this.variables[token.value]
      if (typeof value !== 'number') {
        throw new Error(`变量不是数字: ${token.value}`)
      }
      return value
    }

    if (token.type === 'paren' && token.value === '(') {
      const value = this.parseExpression()
      const close = this.advance()
      if (!close || close.type !== 'paren' || close.value !== ')') {
        throw new Error('括号不匹配')
      }
      return value
    }

    throw new Error('公式语法错误')
  }

  private matchOperator(operator: '+' | '-' | '*' | '/') {
    const token = this.peek()
    if (token?.type !== 'operator' || token.value !== operator) return false
    this.index += 1
    return true
  }

  private advance() {
    const token = this.peek()
    if (token) this.index += 1
    return token
  }

  private peek() {
    return this.tokens[this.index]
  }

  private previous() {
    return this.tokens[this.index - 1] as Extract<FormulaToken, { type: 'operator' }>
  }
}
