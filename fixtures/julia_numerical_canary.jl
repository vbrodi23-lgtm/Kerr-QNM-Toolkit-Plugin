using LinearAlgebra
using Printf

length(ARGS) == 1 || error("usage: julia_numerical_canary.jl OUTPUT")
output_path = ARGS[1]

A = [4.0 1.0; 2.0 3.0]
b = [1.0, 2.0]
x = A \ b
residual = norm(A * x - b)

C = ComplexF64[1 + 2im 0.25; 0 3 - 1im]
values = sort(eigvals(C), by = z -> real(z))

open(output_path, "w") do io
    @printf(io,
        "{\"schema_version\":1,\"kind\":\"kerr-qnm-julia-numerics/v1\",\"linear_solution\":[%.17g,%.17g],\"linear_residual_norm\":%.17g,\"eigenvalues\":[[%.17g,%.17g],[%.17g,%.17g]],\"complex_sqrt\":[%.17g,%.17g]}\n",
        x[1], x[2], residual,
        real(values[1]), imag(values[1]), real(values[2]), imag(values[2]),
        real(sqrt(3 + 4im)), imag(sqrt(3 + 4im)))
end
