import { describe, it, expect } from "vitest";
import { evaluate, ExprError } from "./expr";
import cases from "../../../../dawn-api/tests/fixtures/expr_cases.json";

describe("expr (shared vectors)", () => {
  for (const c of cases as { expr: string; vars?: Record<string, number>; expected?: number; error?: boolean; tol?: number }[]) {
    it(c.expr, () => {
      const vars = {};
      for (const [k, v] of Object.entries(c.vars ?? {})) vars[k] = Number(v);
      if (c.error) {
        expect(() => evaluate(c.expr, vars)).toThrow(ExprError);
        return;
      }
      const result = evaluate(c.expr, vars);
      expect(Math.abs(result - (c.expected ?? 0))).toBeLessThanOrEqual(c.tol ?? 1e-9);
    });
  }
});
