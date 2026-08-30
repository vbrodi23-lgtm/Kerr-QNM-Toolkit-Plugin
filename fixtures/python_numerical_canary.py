#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy import fft, integrate, optimize, special


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python_numerical_canary.py OUTPUT")

    matrix = np.array([[4.0, 1.0], [2.0, 3.0]])
    rhs = np.array([1.0, 2.0])
    solution = np.linalg.solve(matrix, rhs)
    residual = float(np.linalg.norm(matrix @ solution - rhs))

    complex_matrix = np.array([[1.0 + 2.0j, 0.25], [0.0, 3.0 - 1.0j]])
    eigenvalues = sorted(np.linalg.eigvals(complex_matrix), key=lambda value: value.real)
    root = optimize.root_scalar(lambda value: value * value - 2.0, bracket=(1.0, 2.0), xtol=1e-14)
    ode = integrate.solve_ivp(lambda _t, y: -y, (0.0, 1.0), [1.0], rtol=1e-11, atol=1e-13)
    signal = np.array([1.0, 2.0, -1.0, 0.5])
    fft_error = float(np.max(np.abs(fft.ifft(fft.fft(signal)).real - signal)))

    payload = {
        "schema_version": 1,
        "kind": "kerr-qnm-python-numerics/v1",
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "linear_solution": solution.tolist(),
        "linear_residual_norm": residual,
        "eigenvalues": [[float(value.real), float(value.imag)] for value in eigenvalues],
        "sqrt_two": float(root.root),
        "ode_exp_minus_one": float(ode.y[0, -1]),
        "bessel_j0_zero": float(special.jv(0, 0.0)),
        "fft_roundtrip_error": fft_error,
        "reference_exp_minus_one": math.exp(-1.0),
    }
    Path(sys.argv[1]).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
