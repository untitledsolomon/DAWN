// Safe expression evaluator — TS mirror of dawn-api/ui/expr.py (calc block,
// plot/calc inputs). Same grammar, same semantics: numbers, input ids,
// + - * / ^ %, parentheses, comparisons, a fixed function set. No eval,
// Function, property access, strings or assignment. round() is half-away.

export class ExprError extends Error {}

const TOKEN_RE = /^\s*(?:\d+\.?\d*|\.\d+|[A-Za-z_][A-Za-z0-9_]*|<=|>=|==|!=|[+\-*/^%<>(),])/;

type Tok = { kind: "num" | "ident" | "op" | "eof"; value: string | number };

function tokenize(src: string): Tok[] {
  const tokens: Tok[] = [];
  let pos = 0;
  while (pos < src.length) {
    if (/\s/.test(src[pos])) {
      pos += 1;
      continue;
    }
    const m = TOKEN_RE.exec(src.slice(pos));
    if (!m) throw new ExprError(`unexpected character ${src[pos]!} at position ${pos}`);
    const raw = m[0];
    if (/^\d/.test(raw)) tokens.push({ kind: "num", value: parseFloat(raw) });
    else if (/^[A-Za-z_]/.test(raw)) tokens.push({ kind: "ident", value: raw });
    else tokens.push({ kind: "op", value: raw });
    pos += raw.length;
  }
  tokens.push({ kind: "eof", value: "" });
  return tokens;
}

const CONSTANTS: Record<string, number> = { pi: Math.PI, e: Math.E };

function halfRound(x: number, dp = 0): number {
  const f = 10 ** dp;
  return Math.floor(x * f + 0.5) / f;
}

type Fn = (args: number[]) => number;
const FUNCTIONS: Record<string, { min: number; max: number; fn: Fn }> = {
  min: { min: 2, max: 2, fn: ([a, b]) => Math.min(a, b) },
  max: { min: 2, max: 2, fn: ([a, b]) => Math.max(a, b) },
  round: { min: 1, max: 2, fn: ([x, dp]) => halfRound(x, dp ?? 0) },
  floor: { min: 1, max: 1, fn: ([x]) => Math.floor(x) },
  ceil: { min: 1, max: 1, fn: ([x]) => Math.ceil(x) },
  abs: { min: 1, max: 1, fn: ([x]) => Math.abs(x) },
  sqrt: { min: 1, max: 1, fn: ([x]) => Math.sqrt(x) },
  pow: { min: 2, max: 2, fn: ([a, b]) => Math.pow(a, b) },
  if: { min: 3, max: 3, fn: ([c, a, b]) => (c !== 0 ? a : b) },
  sin: { min: 1, max: 1, fn: ([x]) => Math.sin(x) },
  cos: { min: 1, max: 1, fn: ([x]) => Math.cos(x) },
  tan: { min: 1, max: 1, fn: ([x]) => Math.tan(x) },
  asin: { min: 1, max: 1, fn: ([x]) => Math.asin(x) },
  acos: { min: 1, max: 1, fn: ([x]) => Math.acos(x) },
  atan: { min: 1, max: 1, fn: ([x]) => Math.atan(x) },
  atan2: { min: 2, max: 2, fn: ([a, b]) => Math.atan2(a, b) },
  sinh: { min: 1, max: 1, fn: ([x]) => Math.sinh(x) },
  cosh: { min: 1, max: 1, fn: ([x]) => Math.cosh(x) },
  tanh: { min: 1, max: 1, fn: ([x]) => Math.tanh(x) },
  exp: { min: 1, max: 1, fn: ([x]) => Math.exp(x) },
  ln: { min: 1, max: 1, fn: ([x]) => Math.log(x) },
  log10: { min: 1, max: 1, fn: ([x]) => Math.log10(x) },
  log2: { min: 1, max: 1, fn: ([x]) => Math.log2(x) },
  sign: { min: 1, max: 1, fn: ([x]) => (x > 0 ? 1 : x < 0 ? -1 : 0) },
  deg2rad: { min: 1, max: 1, fn: ([x]) => (x * Math.PI) / 180 },
};

class Parser {
  private i = 0;
  constructor(private tokens: Tok[], private vars: Record<string, number>) {}

  private peek(): Tok {
    return this.tokens[this.i];
  }
  private next(): Tok {
    return this.tokens[this.i++];
  }
  private expectOp(op: string) {
    const t = this.next();
    if (t.kind !== "op" || t.value !== op) throw new ExprError(`expected '${op}'`);
  }
  private checked(v: number): number {
    if (!Number.isFinite(v)) throw new ExprError("result is not a finite number");
    return v;
  }

  parse(): number {
    const v = this.comparison();
    if (this.peek().kind !== "eof") throw new ExprError("unexpected trailing input");
    return this.checked(v);
  }

  private comparison(): number {
    let left = this.additive();
    while (this.peek().kind === "op" && ["<", "<=", ">", ">=", "==", "!="].includes(this.peek().value as string)) {
      const op = this.next().value as string;
      const right = this.additive();
      left = {
        "<": left < right, "<=": left <= right, ">": left > right,
        ">=": left >= right, "==": left === right, "!=": left !== right,
      }[op]
        ? 1
        : 0;
    }
    return left;
  }

  private additive(): number {
    let left = this.multiplicative();
    while (this.peek().kind === "op" && (this.peek().value === "+" || this.peek().value === "-")) {
      const op = this.next().value as string;
      const right = this.multiplicative();
      left = op === "+" ? left + right : left - right;
    }
    return left;
  }

  private multiplicative(): number {
    let left = this.exponent();
    while (this.peek().kind === "op" && ["*", "/", "%"].includes(this.peek().value as string)) {
      const op = this.next().value as string;
      const right = this.exponent();
      if (op === "*") left = left * right;
      else if (op === "/") {
        if (right === 0) throw new ExprError("division by zero");
        left = left / right;
      } else {
        if (right === 0) throw new ExprError("modulo by zero");
        left = left % right;
      }
    }
    return left;
  }

  private exponent(): number {
    const base = this.unary();
    if (this.peek().kind === "op" && this.peek().value === "^") {
      this.next();
      return Math.pow(base, this.exponent());
    }
    return base;
  }

  private unary(): number {
    if (this.peek().kind === "op" && (this.peek().value === "-" || this.peek().value === "+")) {
      const op = this.next().value as string;
      const v = this.unary();
      return op === "-" ? -v : v;
    }
    return this.primary();
  }

  private primary(): number {
    const t = this.next();
    if (t.kind === "num") return t.value as number;
    if (t.kind === "op" && t.value === "(") {
      const v = this.comparison();
      this.expectOp(")");
      return v;
    }
    if (t.kind === "ident") {
      const name = t.value as string;
      if (this.peek().kind === "op" && this.peek().value === "(") return this.callFunction(name);
      if (name in CONSTANTS) return CONSTANTS[name];
      if (name in this.vars) return this.vars[name];
      throw new ExprError(`unknown variable '${name}'`);
    }
    throw new ExprError(`unexpected token ${String(t.value)}`);
  }

  private callFunction(name: string): number {
    const def = FUNCTIONS[name];
    if (!def) throw new ExprError(`unknown function '${name}'`);
    this.expectOp("(");
    const args: number[] = [];
    if (!(this.peek().kind === "op" && this.peek().value === ")")) {
      args.push(this.comparison());
      while (this.peek().kind === "op" && this.peek().value === ",") {
        this.next();
        args.push(this.comparison());
      }
    }
    this.expectOp(")");
    if (args.length < def.min || args.length > def.max) {
      throw new ExprError(`'${name}' expects ${def.min}-${def.max} arguments`);
    }
    return def.fn(args);
  }
}

export function evaluate(expr: string, vars: Record<string, number> = {}): number {
  return new Parser(tokenize(expr ?? ""), vars).parse();
}

export function evaluateOrError(expr: string, vars: Record<string, number> = {}): [number | null, string | null] {
  try {
    return [evaluate(expr, vars), null];
  } catch (e) {
    return [null, e instanceof ExprError ? e.message : String(e)];
  }
}
