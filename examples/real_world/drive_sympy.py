"""Exercise sympy: algebra, calculus and simplification. A stress test with 3,000+ functions.

    git clone --depth 1 https://github.com/sympy/sympy.git
    pip install -e ./sympy
Then:
    callgraph run --root ./sympy/sympy --format html --open examples/real_world/drive_sympy.py

Note: much of the trace is sympy importing itself. That's real startup cost, not your math.
"""

from sympy import Rational, cos, diff, exp, expand, factor, integrate, series, simplify, sin, solve, symbols


def algebra(x, y, z):
    expanded = expand((x + y + z) ** 6)
    factored = factor(x**4 - y**4)
    roots = solve(x**3 - 6 * x**2 + 11 * x - 6, x)
    return expanded, factored, roots


def calculus(x):
    derivative = diff(sin(x) * exp(x) / (1 + x**2), x)
    integral = integrate(x**2 * cos(x), x)
    taylor = series(exp(sin(x)), x, 0, 8)
    return derivative, integral, taylor


def simplification(x):
    return simplify((x**2 - 1) / (x - 1) + Rational(1, 3) * sin(x) ** 2 + Rational(1, 3) * cos(x) ** 2)


def main():
    x, y, z = symbols("x y z")
    expanded, factored, roots = algebra(x, y, z)
    calculus(x)
    simplification(x)
    print(f"expanded to {len(expanded.args)} terms; x^4-y^4 = {factored}; roots {roots}")


if __name__ == "__main__":
    main()
