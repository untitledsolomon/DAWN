"""
Safe expression evaluator — the `calc` language (intelligent-ui spec 4.4,
extended with the learning spec's math functions 5.9).

Grammar: numbers, input ids, + - * / ^ %, parentheses, comparisons
(< <= > >= == !=), and a fixed function set. No eval/exec, no property access,
no strings, no assignment. `round` uses half-away-from-zero so the Python and
TypeScript implementations agree.

Raises ExprError on any invalid or non-finite result; the callers render these
as an em dash, never NaN.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

VARIABLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_RE = re.compile(r"(?:\d+\.?\d*|\.\d+)")

OPERATORS = ("<=", ">=", "==", "!=", "+", "-", "*", "/", "^", "%", "<", ">", "(", ")", ",")


class ExprError(ValueError):
    pass


# ── Tokenizer ───────────────────────────────────────────────────────────────
TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>\d+\.?\d*|\.\d+)|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<op><=|>=|==|!=|[+\-*/^%<>(),])"
    r")"
)


class Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value: Any, pos: int):
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"Token({self.kind},{self.value!r})"


def tokenize(expr: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    n = len(expr)
    while pos < n:
        if expr[pos].isspace():
            pos += 1
            continue
        m = TOKEN_RE.match(expr, pos)
        if not m:
            raise ExprError(f"unexpected character {expr[pos]!r} at position {pos}")
        if m.group("num"):
            tokens.append(Token("num", float(m.group("num")), pos))
        elif m.group("ident"):
            tokens.append(Token("ident", m.group("ident"), pos))
        else:
            tokens.append(Token("op", m.group("op"), pos))
        pos = m.end()
    tokens.append(Token("eof", None, n))
    return tokens


# ── Functions ───────────────────────────────────────────────────────────────
def _round(x: float, dp: int = 0) -> float:
    """Half-away-from-zero rounding: identical in Python and TypeScript."""
    f = 10.0 ** int(dp)
    return math.floor(x * f + 0.5) / f

def _sign(x: float) -> float:
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)

def _deg2rad(x: float) -> float:
    return x * math.pi / 180.0

CONSTANTS = {"pi": math.pi, "e": math.e}

FUNCTIONS: dict[str, tuple] = {
    # name: (min_arity, max_arity, callable)
    "min": (2, 2, lambda a, b: min(a, b)),
    "max": (2, 2, lambda a, b: max(a, b)),
    "round": (1, 2, lambda x, dp=0: _round(x, dp)),
    "floor": (1, 1, math.floor),
    "ceil": (1, 1, math.ceil),
    "abs": (1, 1, abs),
    "sqrt": (1, 1, math.sqrt),
    "pow": (2, 2, math.pow),
    "if": (3, 3, lambda c, a, b: a if c != 0 else b),
    "sin": (1, 1, math.sin),
    "cos": (1, 1, math.cos),
    "tan": (1, 1, math.tan),
    "asin": (1, 1, math.asin),
    "acos": (1, 1, math.acos),
    "atan": (1, 1, math.atan),
    "atan2": (2, 2, math.atan2),
    "sinh": (1, 1, math.sinh),
    "cosh": (1, 1, math.cosh),
    "tanh": (1, 1, math.tanh),
    "exp": (1, 1, math.exp),
    "ln": (1, 1, math.log),
    "log10": (1, 1, math.log10),
    "log2": (1, 1, math.log2),
    "sign": (1, 1, _sign),
    "deg2rad": (1, 1, _deg2rad),
}


# ── Parser (recursive descent / Pratt) ───────────────────────────────────────
class Parser:
    def __init__(self, tokens: list[Token], variables: dict[str, float]):
        self.tokens = tokens
        self.i = 0
        self.variables = variables

    def peek(self) -> Token:
        return self.tokens[self.i]

    def next(self) -> Token:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect_op(self, op: str) -> None:
        t = self.next()
        if t.kind != "op" or t.value != op:
            raise ExprError(f"expected '{op}'")

    def parse(self) -> float:
        value = self.parse_comparison()
        if self.peek().kind != "eof":
            raise ExprError("unexpected trailing input")
        return self._checked(value)

    def _checked(self, v: float) -> float:
        if not math.isfinite(v):
            raise ExprError("result is not a finite number")
        return v

    # comparison (non-associative chain)
    def parse_comparison(self) -> float:
        left = self.parse_additive()
        while self.peek().kind == "op" and self.peek().value in ("<", "<=", ">", ">=", "==", "!="):
            op = self.next().value
            right = self.parse_additive()
            left = float({
                "<": left < right, "<=": left <= right, ">": left > right,
                ">=": left >= right, "==": left == right, "!=": left != right,
            }[op])
        return left

    def parse_additive(self) -> float:
        left = self.parse_multiplicative()
        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            op = self.next().value
            right = self.parse_multiplicative()
            left = left + right if op == "+" else left - right
        return left

    def parse_multiplicative(self) -> float:
        left = self.parse_exponent()
        while self.peek().kind == "op" and self.peek().value in ("*", "/", "%"):
            op = self.next().value
            right = self.parse_exponent()
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    raise ExprError("division by zero")
                left = left / right
            else:
                if right == 0:
                    raise ExprError("modulo by zero")
                left = math.fmod(left, right)
        return left

    def parse_exponent(self) -> float:
        base = self.parse_unary()
        if self.peek().kind == "op" and self.peek().value == "^":
            self.next()
            exp = self.parse_exponent()  # right-associative
            return math.pow(base, exp)
        return base

    def parse_unary(self) -> float:
        t = self.peek()
        if t.kind == "op" and t.value in ("-", "+"):
            self.next()
            v = self.parse_unary()
            return -v if t.value == "-" else v
        return self.parse_primary()

    def parse_primary(self) -> float:
        t = self.next()
        if t.kind == "num":
            return float(t.value)
        if t.kind == "op" and t.value == "(":
            v = self.parse_comparison()
            self.expect_op(")")
            return v
        if t.kind == "ident":
            name = t.value
            if self.peek().kind == "op" and self.peek().value == "(":
                return self.parse_function(name)
            if name in CONSTANTS:
                return CONSTANTS[name]
            if name in self.variables:
                return float(self.variables[name])
            raise ExprError(f"unknown variable '{name}'")
        raise ExprError(f"unexpected token {t.value!r}")

    def parse_function(self, name: str) -> float:
        fn = FUNCTIONS.get(name)
        if fn is None:
            raise ExprError(f"unknown function '{name}'")
        args: list[float] = []
        self.expect_op("(")
        if self.peek().kind == "op" and self.peek().value == ")":
            self.next()
            args = []
        else:
            args.append(self.parse_comparison())
            while self.peek().kind == "op" and self.peek().value == ",":
                self.next()
                args.append(self.parse_comparison())
            self.expect_op(")")
        min_a, max_a, call = fn
        if not (min_a <= len(args) <= max_a):
            raise ExprError(f"'{name}' expects {min_a}-{max_a} arguments")
        try:
            return float(call(*args))
        except (ValueError, OverflowError, ZeroDivisionError) as e:
            raise ExprError(f"'{name}' failed: {e}") from e


def evaluate(expr: str, variables: Optional[dict[str, float]] = None) -> float:
    """Evaluate `expr` with the given input ids. Raises ExprError."""
    return Parser(tokenize(expr or ""), variables or {}).parse()


def evaluate_or_error(expr: str, variables: Optional[dict[str, float]] = None) -> tuple[Optional[float], Optional[str]]:
    """Non-raising wrapper — returns (value, None) or (None, error)."""
    try:
        return evaluate(expr, variables), None
    except ExprError as e:
        return None, str(e)
