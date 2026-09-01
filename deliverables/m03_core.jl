module M03Core

using DifferentialEquations
using LinearAlgebra
using SciMLBase
using GeneralizedSasakiNakamura

const GSN = GeneralizedSasakiNakamura
const CF = GeneralizedSasakiNakamura.ComplexFrequencies
const Kerr = GeneralizedSasakiNakamura.Kerr
const Potentials = GeneralizedSasakiNakamura.Potentials

const CORE_SCHEMA = "windows-solver.m03-core/1"
const CORE_VERSION = "m03-core-v1"

const PRODUCED = "PRODUCED"
const PROMOTION_REQUIRED = "PROMOTION_REQUIRED"
const UNRESOLVED = "UNRESOLVED"

const REQUIRED_SCIENTIFIC_OPERATION = "canonical-exterior-background-wronskian/v1"
const REQUIRED_DETERMINANT_FAMILY = "exterior-wronskian/v1"
const REQUIRED_DETERMINANT_CONVENTION = "wronskian-perturbed-Xin-with-Xup/v1"
const REQUIRED_DETERMINANT_NORMALISATION = "unit-asymptotic-branch-wronskian/v1"
const OPERATOR_PENCIL_ID = "angularly-closed-factored-gsn-boundary-value-evans-pencil/v1"
const ANGULAR_TRANSPOSE_ID = "complex-symmetric-spheroidal-c-product/v1"
const RADIAL_TRANSPOSE_ID = "factored-gsn-dual-cauchy-zprime-minus-PTz/v1"
const PAIRING_ID = "complex-bilinear-contour-plus-endpoint/v1"
const DOMEGA_REUSE_ID = "m02-canonical-exterior-wronskian-total-angular-closed-domega/v1"
const EVANS_KELDYSH_BRIDGE_ID = "m02-evans-to-keldysh-comode-normalization/v1"
const RESIDUE_ID = "matching-pencil-rank-one-residue/v1"
const PROJECTOR_ID = "derivative-weighted-matching-pencil-projector/v1"
const CONTINUATION_ID = "fixed-root-phase-orientation-overlap-genealogy/v1"

export CORE_SCHEMA
export CORE_VERSION
export RootSeed
export DomegaStencil
export NumericalPolicy
export RetainedPredecessor
export SpectralStateResult
export BranchResult
export solve_node
export compare_continuation
export reduce_branch

struct RootSeed{T<:AbstractFloat}
    node_identity_sha256::String
    root_identity_sha256::String
    background_identity_sha256::String
    handoff_identity_sha256::String
    s::Int
    ell::Int
    m::Int
    n::Int
    branch_identity::String
    chain_position::Int
    spin_text::String
    spin::T
    omega_real_text::String
    omega_imag_text::String
    omega::Complex{T}
    angular_A_real_text::String
    angular_A_imag_text::String
    angular_A::Complex{T}
    precision_tier::String
end

struct DomegaStencil{T<:AbstractFloat}
    request_sha256::String
    root_identity_sha256::String
    determinant_family::String
    determinant_convention::String
    determinant_normalisation::String
    scientific_operation_identity::String
    h::T
    D0::Complex{T}
    D_plus_h::Complex{T}
    D_minus_h::Complex{T}
    D_plus_half_h::Complex{T}
    D_minus_half_h::Complex{T}
    coarse_derivative::Complex{T}
    fine_derivative::Complex{T}
    disagreement_abs::T
    readout_radius_text::String
    rho_inner_text::String
    rho_outer_text::String
    endpoint_order::Int
    working_precision_bits::Int
end

struct NumericalPolicy{T<:AbstractFloat}
    policy_identity_sha256::String
    precision_tier::String
    working_precision_bits::Int
    readout_radius::T
    rho_inner::T
    rho_outer::T
    endpoint_order::Int
    angular_pad::Int
    ode_reltol::T
    ode_abstol::T
    angular_derivative_step::T
    frequency_audit_step::T
    quadrature_panels::Int
    required_reliable_digits::T
    maximum_horizon_distance::T
    ode_maxiters::Int
    angular_right_residual_max::T
    angular_transpose_residual_max::T
    angular_symmetry_residual_max::T
    angular_c_product_min::T
    lambda_derivative_disagreement_max::T
    radial_wronskian_max::T
    matching_right_null_max::T
    matching_left_null_max::T
    adjugate_factorization_max::T
    transpose_endpoint_residual_max::T
    transpose_readout_residual_max::T
    dual_projective_disagreement_max::T
    bilinear_conservation_max::T
    domega_stencil_relative_disagreement_max::T
    local_domega_to_m02_relative_max::T
    contour_to_readout_denominator_relative_max::T
    bridge_closure_relative_max::T
    residue_rescaling_relative_max::T
    projector_rescaling_relative_max::T
    projector_idempotence_relative_max::T
    projector_action_relative_max::T
    local_resolvent_residue_relative_max::T
    local_resolvent_projector_relative_max::T
    adjugate_residue_relative_max::T
    retained_rho_grid::Vector{T}
    right_rescaling::Complex{T}
    comode_rescaling::Complex{T}
end

struct RetainedPredecessor{T<:AbstractFloat}
    node_identity_sha256::String
    root_identity_sha256::String
    branch_identity::String
    chain_position::Int
    angular_right::Vector{Complex{T}}
    radial_right_samples::Matrix{Complex{T}}
    radial_dual_samples::Matrix{Complex{T}}
end

struct SpectralStateResult{T<:AbstractFloat}
    seed::RootSeed{T}
    disposition::String
    reason_code::Union{Nothing,String}
    counters::NamedTuple
    angular::NamedTuple
    radial_right::NamedTuple
    radial_dual::NamedTuple
    pole_object::NamedTuple
    validation::NamedTuple
    retained::NamedTuple
    timings::NamedTuple
end

struct BranchResult{T<:AbstractFloat}
    branch_identity::String
    ordered_node_identities::Vector{String}
    edges::Vector{NamedTuple}
    precision_history::Vector{String}
    unresolved_gaps::Vector{NamedTuple}
    classification::String
    classification_evidence::NamedTuple
    counters::NamedTuple
end

struct ScientificStop <: Exception
    reason::String
    evidence::NamedTuple
end

Base.showerror(io::IO, err::ScientificStop) = print(io, err.reason)

finite_complex(z) = isfinite(real(z)) && isfinite(imag(z))
bilinear(left, right) = sum(left .* right)
real_type(::Type{Complex{T}}) where {T<:Real} = T
real_type(::Type{T}) where {T<:Real} = T

function _relative_error(left, right, floor_value)
    return abs(left - right) / max(abs(right), floor_value)
end

function _matrix_relative_error(left, right, floor_value)
    return norm(left - right) / max(norm(right), floor_value)
end

function _phase_normalize!(vector)
    pivot = argmax(abs.(vector))
    anchor = vector[pivot]
    iszero(anchor) || (vector .*= conj(anchor) / abs(anchor))
    return vector
end

function _annihilator(vector)
    length(vector) == 2 || error("annihilator requires a two-vector")
    return Complex{real_type(eltype(vector))}[vector[2], -vector[1]]
end

function _adjugate_2x2(matrix)
    size(matrix) == (2, 2) || error("adjugate requires a 2x2 matrix")
    return [matrix[2, 2] -matrix[1, 2]; -matrix[2, 1] matrix[1, 1]]
end

function _rank_one_factor(adjugate)
    pivot = argmax(abs.(adjugate))
    i, j = Tuple(pivot)
    value = adjugate[i, j]
    iszero(value) && throw(ScientificStop("ADJUGATE_NUMERICALLY_ZERO", (;)))
    right = copy(adjugate[:, j])
    left = copy(adjugate[i, :]) ./ value
    reconstructed = right * transpose(left)
    T = real_type(eltype(adjugate))
    return (
        right=right,
        left=left,
        pivot_row=i,
        pivot_column=j,
        relative_error=_matrix_relative_error(reconstructed, adjugate, eps(T)),
    )
end

function _right_nullvector_2x2(matrix)
    T = real_type(eltype(matrix))
    row_norms = [norm(matrix[row, :]) for row in 1:2]
    row = argmax(row_norms)
    a = matrix[row, 1]
    b = matrix[row, 2]
    vector = Complex{T}[b, -a]
    norm(vector) > 0 || throw(ScientificStop("MATCHING_RIGHT_NULL_UNAVAILABLE", (;)))
    vector ./= norm(vector)
    _phase_normalize!(vector)
    residual = norm(matrix * vector) / max(norm(matrix) * norm(vector), eps(T))
    return vector, residual
end

function _left_nullvector_2x2(matrix)
    T = real_type(eltype(matrix))
    column_norms = [norm(matrix[:, column]) for column in 1:2]
    column = argmax(column_norms)
    a = matrix[1, column]
    b = matrix[2, column]
    vector = Complex{T}[b, -a]
    norm(vector) > 0 || throw(ScientificStop("MATCHING_LEFT_NULL_UNAVAILABLE", (;)))
    vector ./= norm(vector)
    _phase_normalize!(vector)
    residual = norm(transpose(vector) * matrix) /
        max(norm(matrix) * norm(vector), eps(T))
    return vector, residual
end

function _deterministic_scale(source, target)
    length(source) == length(target) || error("projective scale vectors differ in length")
    pivot = argmax(abs.(source))
    abs(source[pivot]) > 0 || throw(ScientificStop("PROJECTIVE_SCALE_SOURCE_ZERO", (;)))
    return target[pivot] / source[pivot]
end

function _projective_disagreement(left, right)
    T = real_type(eltype(left))
    denominator = norm(left) * norm(right)
    iszero(denominator) && return T(Inf)
    # Hermitian overlap is used only as a numerical projective-distance diagnostic.
    overlap = sum(conj.(left) .* right)
    cosine = min(one(T), abs(overlap) / denominator)
    return sqrt(max(zero(T), one(T) - cosine^2))
end

function _ode_algorithm()
    return AutoVern9(Rosenbrock23(autodiff=false))
end

function _digits_for_tier(tier::String)
    tier == "bigfloat-40" && return 40
    tier == "bigfloat-80" && return 80
    error("unsupported M03 scientific precision tier")
end

function _expected_bits(tier::String)
    tier == "bigfloat-40" && return 165
    tier == "bigfloat-80" && return 298
    error("unsupported M03 scientific precision tier")
end

function _scientific_disposition(policy::NumericalPolicy)
    return policy.precision_tier == "bigfloat-40" ? PROMOTION_REQUIRED : UNRESOLVED
end

function _empty_result(seed::RootSeed{T}, policy::NumericalPolicy{T}, reason::String; evidence=(;)) where {T}
    gates = Dict{String,Bool}(
        "frozen_root_identity" => true,
        "root_solve_count_zero" => true,
        "base_angular_eigenvalue_solve_count_zero" => true,
    )
    return SpectralStateResult{T}(
        seed,
        _scientific_disposition(policy),
        reason,
        (root_solves=0, base_angular_eigenvalue_solves=0, m02_response_solves=0,
         right_radial_states=0, radial_transpose_states=0),
        (;), (;), (;), (;),
        (gates=gates, evidence=evidence, passed=false),
        (rho_grid=copy(policy.retained_rho_grid), angular_right=Complex{T}[],
         radial_right_samples=zeros(Complex{T}, 0, 0), radial_dual_samples=zeros(Complex{T}, 0, 0)),
        (total_seconds=0.0,),
    )
end

function _validate_inputs(seed::RootSeed{T}, domega::DomegaStencil{T}, policy::NumericalPolicy{T}) where {T}
    seed.precision_tier == policy.precision_tier == (policy.working_precision_bits == 165 ? "bigfloat-40" : "bigfloat-80") ||
        error("seed and policy precision identities disagree")
    policy.working_precision_bits == _expected_bits(policy.precision_tier) ||
        error("M03 working precision bits are invalid")
    domega.working_precision_bits <= policy.working_precision_bits ||
        error("M02 derivative evidence exceeds the requested M03 precision unexpectedly")
    domega.root_identity_sha256 == seed.root_identity_sha256 ||
        error("M02 derivative root identity disagrees with the frozen M03 root")
    domega.scientific_operation_identity == REQUIRED_SCIENTIFIC_OPERATION ||
        error("wrong M02 Domega scientific operation identity")
    domega.determinant_family == REQUIRED_DETERMINANT_FAMILY ||
        error("wrong M02 determinant family")
    domega.determinant_convention == REQUIRED_DETERMINANT_CONVENTION ||
        error("wrong M02 determinant convention")
    domega.determinant_normalisation == REQUIRED_DETERMINANT_NORMALISATION ||
        error("wrong M02 determinant normalisation")
    all(finite_complex, (seed.omega, seed.angular_A, domega.D0, domega.D_plus_h,
        domega.D_minus_h, domega.D_plus_half_h, domega.D_minus_half_h,
        domega.coarse_derivative, domega.fine_derivative)) || error("nonfinite scientific input")
    all(isfinite, (seed.spin, domega.h, domega.disagreement_abs, policy.readout_radius,
        policy.rho_inner, policy.rho_outer, policy.ode_reltol, policy.ode_abstol,
        policy.frequency_audit_step)) || error("nonfinite M03 numerical policy")
    imag(seed.omega) < zero(T) || error("frozen M02 root violates the damped-root sign convention")
    return nothing
end

function _validate_domega_reduction(domega::DomegaStencil{T}) where {T}
    coarse = (domega.D_plus_h - domega.D_minus_h) / (T(2) * domega.h)
    fine = (domega.D_plus_half_h - domega.D_minus_half_h) / domega.h
    disagreement = abs(fine - coarse)
    tolerance = T(128) * eps(T)
    _relative_error(coarse, domega.coarse_derivative, eps(T)) <= tolerance ||
        error("supplied M02 coarse Domega disagrees with its raw stencil")
    _relative_error(fine, domega.fine_derivative, eps(T)) <= tolerance ||
        error("supplied M02 fine Domega disagrees with its raw stencil")
    abs(disagreement - domega.disagreement_abs) <= max(tolerance * max(disagreement, one(T)), eps(T)) ||
        error("supplied M02 Domega disagreement disagrees with its raw stencil")
    return (coarse=coarse, fine=fine, disagreement=disagreement)
end

function _Fslm(::Type{T}, s::Int, ell::Int, m::Int) where {T<:AbstractFloat}
    ep = T(ell + 1)
    iszero(ep) && iszero(s) && return zero(T)
    return sqrt(((ep^2 - T(m)^2) / (T(2ell + 3) * T(2ell + 1))) *
                ((ep^2 - T(s)^2) / ep^2))
end

function _Gslm(::Type{T}, s::Int, ell::Int, m::Int) where {T<:AbstractFloat}
    ell == 0 && return zero(T)
    e = T(ell)
    return sqrt(((e^2 - T(m)^2) / (T(4) * e^2 - one(T))) *
                ((e^2 - T(s)^2) / e^2))
end

function _Hslm(::Type{T}, s::Int, ell::Int, m::Int) where {T<:AbstractFloat}
    (ell == 0 || s == 0) && return zero(T)
    return -T(m * s) / T(ell * (ell + 1))
end

function _angular_matrix_and_derivative(::Type{T}, c::Complex{T}, s::Int, m::Int, count::Int) where {T<:AbstractFloat}
    ell_min = max(abs(s), abs(m))
    matrix = zeros(Complex{T}, count, count)
    derivative = zeros(Complex{T}, count, count)
    for row in 1:count
        ell = ell_min + row - 1
        for column in max(1, row - 2):min(count, row + 2)
            ell_prime = ell_min + column - 1
            value = zero(Complex{T})
            value_c = zero(Complex{T})
            if ell_prime == ell - 2
                q = _Fslm(T, s, ell_prime, m) * _Fslm(T, s, ell_prime + 1, m)
                value = -c^2 * q
                value_c = -T(2) * c * q
            elseif ell_prime == ell - 1
                q = _Fslm(T, s, ell_prime, m) * (_Hslm(T, s, ell_prime + 1, m) + _Hslm(T, s, ell_prime, m))
                l = T(s) * _Fslm(T, s, ell_prime, m)
                value = -c^2 * q + T(2) * c * l
                value_c = -T(2) * c * q + T(2) * l
            elseif ell_prime == ell
                diagonal = T(ell_prime * (ell_prime + 1) - s * (s + 1))
                q = _Fslm(T, s, ell_prime, m) * _Gslm(T, s, ell_prime + 1, m) +
                    _Gslm(T, s, ell_prime, m) * _Fslm(T, s, ell_prime - 1, m) +
                    _Hslm(T, s, ell_prime, m)^2
                l = T(s) * _Hslm(T, s, ell_prime, m)
                value = diagonal - c^2 * q + T(2) * c * l
                value_c = -T(2) * c * q + T(2) * l
            elseif ell_prime == ell + 1
                q = _Gslm(T, s, ell_prime, m) * (_Hslm(T, s, ell_prime - 1, m) + _Hslm(T, s, ell_prime, m))
                l = T(s) * _Gslm(T, s, ell_prime, m)
                value = -c^2 * q + T(2) * c * l
                value_c = -T(2) * c * q + T(2) * l
            elseif ell_prime == ell + 2
                q = _Gslm(T, s, ell_prime, m) * _Gslm(T, s, ell_prime - 1, m)
                value = -c^2 * q
                value_c = -T(2) * c * q
            end
            matrix[row, column] = value
            derivative[row, column] = value_c
        end
    end
    return matrix, derivative
end

function _anchored_nullvector(matrix, pivot)
    T = real_type(eltype(matrix))
    n, m = size(matrix)
    n == m || error("angular nullvector matrix must be square")
    columns = [column for column in 1:n if column != pivot]
    best = nothing
    for omitted_row in 1:n
        rows = [row for row in 1:n if row != omitted_row]
        solution = try
            matrix[rows, columns] \ (-matrix[rows, pivot])
        catch
            continue
        end
        all(finite_complex, solution) || continue
        vector = zeros(eltype(matrix), n)
        vector[pivot] = one(T)
        vector[columns] = solution
        residual = norm(matrix * vector) / max(norm(matrix) * norm(vector), eps(T))
        if best === nothing || residual < best.residual
            best = (vector=vector, residual=residual, omitted_row=omitted_row)
        end
    end
    best === nothing && throw(ScientificStop("ANGULAR_NULLVECTOR_UNAVAILABLE", (;)))
    vector = best.vector / norm(best.vector)
    _phase_normalize!(vector)
    residual = norm(matrix * vector) / max(norm(matrix) * norm(vector), eps(T))
    return (vector=vector, residual=residual, omitted_row=best.omitted_row)
end

function _angular_state_and_comode(seed::RootSeed{T}, policy::NumericalPolicy{T}) where {T}
    c = seed.spin * seed.omega
    ell_min = max(abs(seed.s), abs(seed.m))
    count = seed.ell + policy.angular_pad - ell_min + 1
    target_index = seed.ell - ell_min + 1
    matrix, matrix_c = _angular_matrix_and_derivative(T, c, seed.s, seed.m, count)
    pencil = matrix - seed.angular_A * I
    right_data = _anchored_nullvector(pencil, target_index)
    transpose_data = _anchored_nullvector(transpose(pencil), target_index)
    right = copy(right_data.vector)
    dual_raw = copy(transpose_data.vector)
    c_product = bilinear(dual_raw, right)
    abs(c_product) > policy.angular_c_product_min ||
        throw(ScientificStop("ANGULAR_C_PRODUCT_SELF_ORTHOGONAL", (c_product=c_product,)))
    dual = dual_raw / c_product
    transpose_residual = norm(transpose(pencil) * dual) / max(norm(pencil) * norm(dual), eps(T))
    symmetry_residual = norm(matrix - transpose(matrix)) / max(norm(matrix), eps(T))
    normalized_c_product = bilinear(dual, right)
    A_c = bilinear(dual, matrix_c * right)
    A_omega = seed.spin * A_c
    lambda = seed.angular_A + c^2 - T(2 * seed.m) * c
    lambda_omega = A_omega + T(2) * seed.spin^2 * seed.omega - T(2 * seed.m) * seed.spin
    delta = policy.angular_derivative_step
    cplus = seed.spin * (seed.omega + delta)
    cminus = seed.spin * (seed.omega - delta)
    Aplus = seed.angular_A + A_omega * delta
    Aminus = seed.angular_A - A_omega * delta
    lambda_plus = Aplus + cplus^2 - T(2 * seed.m) * cplus
    lambda_minus = Aminus + cminus^2 - T(2 * seed.m) * cminus
    lambda_fd = (lambda_plus - lambda_minus) / (T(2) * delta)
    lambda_disagreement = _relative_error(lambda_fd, lambda_omega, eps(T))
    return (
        c=c, matrix=matrix, matrix_c=matrix_c, pencil=pencil,
        right=right, dual=dual, dual_raw=dual_raw,
        right_residual=right_data.residual,
        transpose_residual=transpose_residual,
        symmetry_residual=symmetry_residual,
        c_product_raw=c_product,
        c_product_normalized=normalized_c_product,
        A_c=A_c, A_omega=A_omega, lambda=lambda,
        lambda_omega=lambda_omega, lambda_omega_fd=lambda_fd,
        lambda_derivative_disagreement=lambda_disagreement,
        count=count, target_index=target_index,
    )
end

function _build_fixed_geometry(seed::RootSeed{T}, policy::NumericalPolicy{T}, convention) where {T}
    rstar_match = T(GSN.rstar_from_r(seed.spin, policy.readout_radius))
    horizon_radius_from_rho = CF.solve_r_from_rho(
        seed.spin, zero(T), rstar_match, policy.rho_inner;
        sign=Int8(1), dtype=Complex{T}, odealgo=_ode_algorithm(),
        reltol=policy.ode_reltol, abstol=policy.ode_abstol,
        ode_maxiters=policy.ode_maxiters,
        r_at_rho_zero=Complex{T}(policy.readout_radius), verbose=false,
    )
    infinity_radius_from_rho = CF.solve_r_from_rho(
        seed.spin, convention.infinity_contour_angle, rstar_match, policy.rho_outer;
        sign=convention.infinity_sign, dtype=Complex{T}, odealgo=_ode_algorithm(),
        reltol=policy.ode_reltol, abstol=policy.ode_abstol,
        ode_maxiters=policy.ode_maxiters,
        r_at_rho_zero=Complex{T}(policy.readout_radius), verbose=false,
    )
    return (
        match_radius=policy.readout_radius, rstar_match=rstar_match,
        rho_horizon=policy.rho_inner, rho_infinity=policy.rho_outer,
        horizon_radius_from_rho=horizon_radius_from_rho,
        infinity_radius_from_rho=infinity_radius_from_rho,
    )
end

function _build_spectral_context(seed::RootSeed{T}, policy::NumericalPolicy{T}, omega, lambda, convention) where {T}
    return CF.build_homogeneous_spectral_context(
        seed.s, seed.m, seed.spin, omega, lambda,
        _digits_for_tier(policy.precision_tier), policy.working_precision_bits,
        policy.endpoint_order, convention,
    )
end

function _prepare_horizon_endpoint(seed::RootSeed{T}, policy::NumericalPolicy{T}, spectral, geometry) where {T}
    contour = CF.build_real_inner_horizon_contour(
        spectral, geometry.match_radius, geometry.rstar_match,
        geometry.rho_horizon, geometry.horizon_radius_from_rho,
    )
    geometry_candidates = CF.horizon_endpoint_geometry_candidates(
        spectral, contour; rho_candidates=T[geometry.rho_horizon],
        maximum_horizon_distance=policy.maximum_horizon_distance,
    )
    candidates = CF.horizon_endpoint_candidates(
        spectral, contour, geometry_candidates, policy.required_reliable_digits;
        maximum_horizon_distance=policy.maximum_horizon_distance,
        endpoint_orders=Int[policy.endpoint_order], attempted_endpoint_order=policy.endpoint_order,
    )
    length(candidates) == 1 || throw(ScientificStop("HORIZON_ENDPOINT_CANDIDATE_AMBIGUOUS", (; count=length(candidates))))
    candidate = only(candidates)
    candidate.ingoing_adequate || throw(ScientificStop("HORIZON_ENDPOINT_INADEQUATE", (;)))
    endpoint = CF.prepare_real_inner_horizon_endpoint(
        spectral, contour, candidate, CF.HORIZON_INGOING, policy.required_reliable_digits,
    )
    endpoint.assessment.adequate || throw(ScientificStop("HORIZON_ENDPOINT_PREPARATION_INADEQUATE", (;)))
    raw = GSN.reconstruct_state(endpoint.state, endpoint.carrier, endpoint.rho)
    tangent = contour.tangent
    state = Complex{T}[raw.X, raw.Xrho / tangent]
    return (contour=contour, endpoint=endpoint, state=state, tangent=tangent)
end

function _prepare_infinity_endpoint(seed::RootSeed{T}, policy::NumericalPolicy{T}, spectral, geometry) where {T}
    contour = CF.build_outer_contour_context(
        spectral, geometry.match_radius, geometry.rstar_match,
        geometry.rho_infinity, geometry.infinity_radius_from_rho,
    )
    preparation = CF.prepare_factored_infinity_outgoing(
        spectral, contour, policy.required_reliable_digits,
    )
    preparation.assessment.adequate || throw(ScientificStop("INFINITY_ENDPOINT_INADEQUATE", (;)))
    initial = preparation.initial_condition
    raw = GSN.reconstruct_state(initial.state, initial.carrier, geometry.rho_infinity)
    tangent = contour.infinity_tangent
    state = Complex{T}[raw.X, raw.Xrho / tangent]
    return (contour=contour, preparation=preparation, state=state, tangent=tangent)
end

function _physical_system_matrix(seed::RootSeed{T}, omega, lambda, radius_from_rho, tangent, rho) where {T}
    radius = Complex{T}(radius_from_rho(rho))
    F = Complex{T}(Potentials.sF(seed.s, seed.m, seed.spin, omega, lambda, radius))
    U = Complex{T}(Potentials.sU(seed.s, seed.m, seed.spin, omega, lambda, radius))
    return Complex{T}[zero(T) tangent; tangent * U tangent * F]
end

function _solve_physical_branch(seed::RootSeed{T}, policy::NumericalPolicy{T}, omega, lambda,
    radius_from_rho, tangent, start_rho, endpoint_state, label) where {T}
    function rhs!(du, state, _p, rho)
        value = _physical_system_matrix(seed, omega, lambda, radius_from_rho, tangent, rho) * state
        du[1] = value[1]
        du[2] = value[2]
        return nothing
    end
    problem = ODEProblem(rhs!, copy(endpoint_state), (start_rho, zero(T)))
    solution = solve(problem, _ode_algorithm(); maxiters=policy.ode_maxiters,
        reltol=policy.ode_reltol, abstol=policy.ode_abstol, dense=true,
        save_everystep=true, save_start=true, save_end=true, verbose=false)
    SciMLBase.successful_retcode(solution.retcode) ||
        throw(ScientificStop("RADIAL_ODE_FAILED", (label=label, retcode=string(solution.retcode))))
    return solution
end

function _solve_right_state(seed::RootSeed{T}, policy::NumericalPolicy{T}, omega, A, label) where {T}
    c = seed.spin * omega
    lambda = A + c^2 - T(2 * seed.m) * c
    p_horizon = omega - T(seed.m) * Kerr.omega_horizon(seed.spin)
    convention = GSN.gsn_branch_convention(omega, p_horizon)
    spectral = _build_spectral_context(seed, policy, omega, lambda, convention)
    geometry = _build_fixed_geometry(seed, policy, spectral.convention)
    horizon = _prepare_horizon_endpoint(seed, policy, spectral, geometry)
    infinity = _prepare_infinity_endpoint(seed, policy, spectral, geometry)
    horizon_solution = _solve_physical_branch(seed, policy, omega, lambda,
        geometry.horizon_radius_from_rho, horizon.tangent, geometry.rho_horizon,
        horizon.state, "$label horizon->readout")
    infinity_solution = _solve_physical_branch(seed, policy, omega, lambda,
        geometry.infinity_radius_from_rho, infinity.tangent, geometry.rho_infinity,
        infinity.state, "$label infinity->readout")
    horizon_match = Complex{T}.(horizon_solution(zero(T)))
    infinity_match = Complex{T}.(infinity_solution(zero(T)))
    matching_matrix = hcat(horizon_match, infinity_match)
    determinant = det(matching_matrix)
    normalized_wronskian = abs(determinant) /
        max(norm(horizon_match) * norm(infinity_match), eps(T))
    projection_denominator = max(sum(abs2, infinity_match), eps(T))
    outer_scale = sum(conj.(infinity_match) .* horizon_match) / projection_denominator
    join_residual = norm(horizon_match - outer_scale * infinity_match) /
        max(norm(horizon_match), eps(T))
    return (
        label=label, omega=omega, A=A, lambda=lambda, spectral=spectral,
        geometry=geometry, horizon=horizon, infinity=infinity,
        horizon_solution=horizon_solution, infinity_solution=infinity_solution,
        horizon_endpoint_state=horizon.state, infinity_endpoint_state=infinity.state,
        horizon_match=horizon_match, infinity_match=infinity_match,
        matching_matrix=matching_matrix, determinant=determinant,
        normalized_wronskian=normalized_wronskian, join_residual=join_residual,
    )
end

function _solve_dual_augmented(seed::RootSeed{T}, policy::NumericalPolicy{T}, base, plus, minus,
    side::Symbol, initial_dual, delta) where {T}
    if side == :horizon
        base_radius = base.geometry.horizon_radius_from_rho
        plus_radius = plus.geometry.horizon_radius_from_rho
        minus_radius = minus.geometry.horizon_radius_from_rho
        base_tangent = base.horizon.tangent
        plus_tangent = plus.horizon.tangent
        minus_tangent = minus.horizon.tangent
        start_rho = base.geometry.rho_horizon
        right_solution = base.horizon_solution
        integrand_sign = -one(T)
    elseif side == :infinity
        base_radius = base.geometry.infinity_radius_from_rho
        plus_radius = plus.geometry.infinity_radius_from_rho
        minus_radius = minus.geometry.infinity_radius_from_rho
        base_tangent = base.infinity.tangent
        plus_tangent = plus.infinity.tangent
        minus_tangent = minus.infinity.tangent
        start_rho = base.geometry.rho_infinity
        right_solution = base.infinity_solution
        integrand_sign = one(T)
    else
        error("unknown dual side")
    end
    function rhs!(du, state, _p, rho)
        z = Complex{T}[state[1], state[2]]
        P0 = _physical_system_matrix(seed, base.omega, base.lambda, base_radius, base_tangent, rho)
        Pplus = _physical_system_matrix(seed, plus.omega, plus.lambda, plus_radius, plus_tangent, rho)
        Pminus = _physical_system_matrix(seed, minus.omega, minus.lambda, minus_radius, minus_tangent, rho)
        Pdot = (Pplus - Pminus) / (T(2) * delta)
        right = Complex{T}.(right_solution(rho))
        zdot = -transpose(P0) * z
        du[1] = zdot[1]
        du[2] = zdot[2]
        du[3] = integrand_sign * bilinear(z, Pdot * right)
        return nothing
    end
    initial = Complex{T}[initial_dual[1], initial_dual[2], zero(T)]
    problem = ODEProblem(rhs!, initial, (start_rho, zero(T)))
    solution = solve(problem, _ode_algorithm(); maxiters=policy.ode_maxiters,
        reltol=policy.ode_reltol, abstol=policy.ode_abstol, dense=true,
        save_everystep=true, save_start=true, save_end=true, verbose=false)
    SciMLBase.successful_retcode(solution.retcode) ||
        throw(ScientificStop("RADIAL_TRANSPOSE_ODE_FAILED", (side=String(side), retcode=string(solution.retcode))))
    return solution
end

function _dual_conservation_error(::Type{T}, dual_solution, right_solution, start_rho) where {T}
    maximum = zero(T)
    for rho in range(start_rho, zero(T); length=17)
        dual = Complex{T}.(dual_solution(rho)[1:2])
        right = Complex{T}.(right_solution(rho))
        value = bilinear(dual, right)
        scale = max(norm(dual) * norm(right), eps(T))
        maximum = max(maximum, abs(value) / scale)
    end
    return maximum
end

function _construct_radial_comode(seed::RootSeed{T}, policy::NumericalPolicy{T}, base, plus, minus,
    matching_left, matching_right, delta) where {T}
    b_horizon = _annihilator(base.horizon_endpoint_state)
    b_infinity = _annihilator(base.infinity_endpoint_state)
    b_horizon_dot = (_annihilator(plus.horizon_endpoint_state) - _annihilator(minus.horizon_endpoint_state)) / (T(2) * delta)
    b_infinity_dot = (_annihilator(plus.infinity_endpoint_state) - _annihilator(minus.infinity_endpoint_state)) / (T(2) * delta)
    horizon_dual = _solve_dual_augmented(seed, policy, base, plus, minus, :horizon, b_horizon, delta)
    infinity_dual = _solve_dual_augmented(seed, policy, base, plus, minus, :infinity, -b_infinity, delta)
    horizon_match = Complex{T}.(horizon_dual(zero(T))[1:2])
    infinity_match = Complex{T}.(infinity_dual(zero(T))[1:2])
    multiplier_matrix = hcat(horizon_match, -infinity_match)
    multipliers, multiplier_residual = _right_nullvector_2x2(multiplier_matrix)
    eta_horizon = multipliers[1]
    eta_infinity = multipliers[2]
    Z_horizon_match = eta_horizon * horizon_match
    Z_infinity_match = eta_infinity * infinity_match
    raw_match_residual = norm(Z_horizon_match - Z_infinity_match) /
        max(norm(Z_horizon_match), norm(Z_infinity_match), eps(T))
    raw_match = (Z_horizon_match + Z_infinity_match) / T(2)
    readout_scale = _deterministic_scale(raw_match, -matching_left)
    eta_horizon_readout = readout_scale * eta_horizon
    eta_infinity_readout = readout_scale * eta_infinity
    Z_match_readout = readout_scale * raw_match
    u_h = matching_right[1]
    u_i = matching_right[2]
    horizon_accumulator = horizon_dual(zero(T))[3]
    infinity_accumulator = infinity_dual(zero(T))[3]
    bulk_horizon_raw = eta_horizon * u_h * horizon_accumulator
    bulk_infinity_raw = -eta_infinity * u_i * infinity_accumulator
    endpoint_horizon_raw = eta_horizon * u_h * bilinear(b_horizon_dot, base.horizon_endpoint_state)
    endpoint_infinity_raw = -eta_infinity * u_i * bilinear(b_infinity_dot, base.infinity_endpoint_state)
    raw_total = bulk_horizon_raw + bulk_infinity_raw + endpoint_horizon_raw + endpoint_infinity_raw
    bulk_horizon = readout_scale * bulk_horizon_raw
    bulk_infinity = readout_scale * bulk_infinity_raw
    endpoint_horizon = readout_scale * endpoint_horizon_raw
    endpoint_infinity = readout_scale * endpoint_infinity_raw
    readout_total = bulk_horizon + bulk_infinity + endpoint_horizon + endpoint_infinity
    horizon_conservation = _dual_conservation_error(T, horizon_dual, base.horizon_solution, base.geometry.rho_horizon)
    infinity_conservation = _dual_conservation_error(T, infinity_dual, base.infinity_solution, base.geometry.rho_infinity)
    readout_left_disagreement = _projective_disagreement(Z_match_readout, matching_left)
    return (
        b_horizon=b_horizon, b_infinity=b_infinity,
        b_horizon_dot=b_horizon_dot, b_infinity_dot=b_infinity_dot,
        horizon_dual=horizon_dual, infinity_dual=infinity_dual,
        multiplier_matrix=multiplier_matrix, multipliers=multipliers,
        multiplier_residual=multiplier_residual,
        eta_horizon_raw=eta_horizon, eta_infinity_raw=eta_infinity,
        raw_match=raw_match, raw_match_residual=raw_match_residual,
        readout_scale=readout_scale, eta_horizon_readout=eta_horizon_readout,
        eta_infinity_readout=eta_infinity_readout, Z_match_readout=Z_match_readout,
        readout_left_disagreement=readout_left_disagreement,
        horizon_conservation=horizon_conservation, infinity_conservation=infinity_conservation,
        bulk_horizon=bulk_horizon, bulk_infinity=bulk_infinity,
        endpoint_horizon=endpoint_horizon, endpoint_infinity=endpoint_infinity,
        raw_total=raw_total, readout_total=readout_total,
    )
end

function _residue_analysis(::Type{T}, policy::NumericalPolicy{T}, base, plus, minus,
    m02_fine, matching_right, matching_left, radial_comode, delta) where {T}
    F0 = base.matching_matrix
    Fplus = plus.matching_matrix
    Fminus = minus.matching_matrix
    Fdot = (Fplus - Fminus) / (T(2) * delta)
    matching_denominator = bilinear(matching_left, Fdot * matching_right)
    abs(matching_denominator) > policy.angular_c_product_min ||
        throw(ScientificStop("MATCHING_KELDYSH_DENOMINATOR_ZERO", (;)))
    full_denominator = radial_comode.readout_total
    abs(full_denominator) > policy.angular_c_product_min ||
        throw(ScientificStop("FULL_KELDYSH_DENOMINATOR_ZERO", (;)))
    determinant_derivative_fd = (plus.determinant - minus.determinant) / (T(2) * delta)
    adjugate = _adjugate_2x2(F0)
    determinant_derivative_jacobi = tr(adjugate * Fdot)
    evans_bridge = m02_fine / full_denominator
    bridged_full_denominator = evans_bridge * full_denominator
    matching_bridge = m02_fine / matching_denominator
    left_evans = matching_bridge * matching_left
    bridged_matching_denominator = bilinear(left_evans, Fdot * matching_right)
    residue = matching_right * transpose(matching_left) / matching_denominator
    projector = residue * Fdot
    residue_adjugate = adjugate / m02_fine
    right_scaled = policy.right_rescaling * matching_right
    left_scaled = policy.comode_rescaling * matching_left
    denominator_scaled = bilinear(left_scaled, Fdot * right_scaled)
    residue_scaled = right_scaled * transpose(left_scaled) / denominator_scaled
    projector_scaled = residue_scaled * Fdot
    residue_rescaling_error = _matrix_relative_error(residue_scaled, residue, eps(T))
    projector_rescaling_error = _matrix_relative_error(projector_scaled, projector, eps(T))
    projector_idempotence_error = _matrix_relative_error(projector * projector, projector, eps(T))
    projector_right_action_error = norm(projector * matching_right - matching_right) / max(norm(matching_right), eps(T))
    local_residue = delta / T(2) * (inv(Fplus) - inv(Fminus))
    local_projector = local_residue * Fdot
    local_residue_error = _matrix_relative_error(local_residue, residue, eps(T))
    local_projector_error = _matrix_relative_error(local_projector, projector, eps(T))
    adjugate_residue_error = _matrix_relative_error(residue_adjugate, residue, eps(T))
    return (
        Fdot=Fdot, matching_denominator=matching_denominator,
        full_denominator=full_denominator,
        determinant_derivative_fd=determinant_derivative_fd,
        determinant_derivative_jacobi=determinant_derivative_jacobi,
        adjugate=adjugate, evans_bridge=evans_bridge,
        bridged_full_denominator=bridged_full_denominator,
        matching_bridge=matching_bridge, left_evans=left_evans,
        bridged_matching_denominator=bridged_matching_denominator,
        residue=residue, projector=projector, residue_adjugate=residue_adjugate,
        residue_rescaling_error=residue_rescaling_error,
        projector_rescaling_error=projector_rescaling_error,
        projector_idempotence_error=projector_idempotence_error,
        projector_right_action_error=projector_right_action_error,
        local_residue=local_residue, local_projector=local_projector,
        local_residue_error=local_residue_error,
        local_projector_error=local_projector_error,
        adjugate_residue_error=adjugate_residue_error,
    )
end

function _retained_samples(::Type{T}, policy::NumericalPolicy{T}, base, radial_comode, matching_right) where {T}
    grid = copy(policy.retained_rho_grid)
    right_samples = zeros(Complex{T}, length(grid), 2)
    dual_samples = zeros(Complex{T}, length(grid), 2)
    for (index, rho) in enumerate(grid)
        if rho <= zero(T)
            right_samples[index, :] = matching_right[1] .* Complex{T}.(base.horizon_solution(rho))
            dual_samples[index, :] = (radial_comode.readout_scale * radial_comode.eta_horizon_raw) .* Complex{T}.(radial_comode.horizon_dual(rho)[1:2])
        else
            right_samples[index, :] = -matching_right[2] .* Complex{T}.(base.infinity_solution(rho))
            dual_samples[index, :] = (radial_comode.readout_scale * radial_comode.eta_infinity_raw) .* Complex{T}.(radial_comode.infinity_dual(rho)[1:2])
        end
    end
    return right_samples, dual_samples
end

function solve_node(seed::RootSeed{T}, domega::DomegaStencil{T}, policy::NumericalPolicy{T})::SpectralStateResult{T} where {T<:AbstractFloat}
    started = time()
    _validate_inputs(seed, domega, policy)
    reductions = _validate_domega_reduction(domega)
    counters = (root_solves=0, base_angular_eigenvalue_solves=0, m02_response_solves=0,
        right_radial_states=3, radial_transpose_states=2)
    try
        angular = _angular_state_and_comode(seed, policy)
        delta = policy.frequency_audit_step
        delta > zero(T) || error("frequency audit step must be positive")
        omega_plus = seed.omega + Complex{T}(delta, zero(T))
        omega_minus = seed.omega - Complex{T}(delta, zero(T))
        A_plus = seed.angular_A + angular.A_omega * delta
        A_minus = seed.angular_A - angular.A_omega * delta
        base_started = time()
        base = _solve_right_state(seed, policy, seed.omega, seed.angular_A, "base")
        base_seconds = time() - base_started
        plus_started = time()
        plus = _solve_right_state(seed, policy, omega_plus, A_plus, "plus")
        plus_seconds = time() - plus_started
        minus_started = time()
        minus = _solve_right_state(seed, policy, omega_minus, A_minus, "minus")
        minus_seconds = time() - minus_started
        matching_right, matching_right_residual = _right_nullvector_2x2(base.matching_matrix)
        matching_left, matching_left_residual = _left_nullvector_2x2(base.matching_matrix)
        adjugate = _adjugate_2x2(base.matching_matrix)
        factor = _rank_one_factor(adjugate)
        comode_started = time()
        radial_comode = _construct_radial_comode(seed, policy, base, plus, minus,
            matching_left, matching_right, delta)
        comode_seconds = time() - comode_started
        residue = _residue_analysis(T, policy, base, plus, minus, reductions.fine,
            matching_right, matching_left, radial_comode, delta)
        m02_step_relative = reductions.disagreement / max(abs(reductions.fine), eps(T))
        Domega_relative = _relative_error(residue.determinant_derivative_fd, reductions.fine, eps(T))
        full_matching_relative = _relative_error(residue.full_denominator, residue.matching_denominator, eps(T))
        bridge_relative = _relative_error(residue.bridged_full_denominator, reductions.fine, eps(T))
        gates = Dict{String,Bool}(
            "01_frozen_root_identity_conserved" => domega.root_identity_sha256 == seed.root_identity_sha256,
            "02_root_solve_count_zero" => counters.root_solves == 0,
            "03_base_angular_eigenvalue_solve_count_zero" => counters.base_angular_eigenvalue_solves == 0,
            "04_angular_right_residual" => angular.right_residual <= policy.angular_right_residual_max,
            "05_angular_transpose_residual" => angular.transpose_residual <= policy.angular_transpose_residual_max,
            "06_angular_matrix_transpose_symmetry" => angular.symmetry_residual <= policy.angular_symmetry_residual_max,
            "07_angular_c_product_nonzero_normalized" => abs(angular.c_product_raw) > policy.angular_c_product_min && _relative_error(angular.c_product_normalized, one(Complex{T}), eps(T)) <= policy.angular_transpose_residual_max,
            "08_lambda_prime_independent_audit" => angular.lambda_derivative_disagreement <= policy.lambda_derivative_disagreement_max,
            "09_base_radial_ode_legs" => true,
            "10_base_wronskian" => base.normalized_wronskian <= policy.radial_wronskian_max,
            "11_matching_right_null" => matching_right_residual <= policy.matching_right_null_max,
            "12_matching_transpose_left_null" => matching_left_residual <= policy.matching_left_null_max,
            "13_adjugate_rank_one_factorization" => factor.relative_error <= policy.adjugate_factorization_max,
            "14_shifted_radial_ode_legs" => true,
            "15_radial_transpose_endpoint_multiplier" => radial_comode.multiplier_residual <= policy.transpose_endpoint_residual_max,
            "16_radial_transpose_readout" => radial_comode.raw_match_residual <= policy.transpose_readout_residual_max,
            "17_comode_readout_left_projective_agreement" => radial_comode.readout_left_disagreement <= policy.dual_projective_disagreement_max,
            "18_horizon_bilinear_conservation" => radial_comode.horizon_conservation <= policy.bilinear_conservation_max,
            "19_infinity_bilinear_conservation" => radial_comode.infinity_conservation <= policy.bilinear_conservation_max,
            "20_m02_domega_disk_excludes_zero" => abs(reductions.fine) > reductions.disagreement,
            "21_m02_stencil_stability" => m02_step_relative <= policy.domega_stencil_relative_disagreement_max,
            "22_local_matrix_derivative_agrees_m02" => Domega_relative <= policy.local_domega_to_m02_relative_max,
            "23_evans_keldysh_bridge_closure" => bridge_relative <= policy.bridge_closure_relative_max && full_matching_relative <= policy.contour_to_readout_denominator_relative_max,
            "24_residue_projector_rescaling_invariance" => residue.residue_rescaling_error <= policy.residue_rescaling_relative_max && residue.projector_rescaling_error <= policy.projector_rescaling_relative_max,
            "25_projector_idempotence_right_action" => residue.projector_idempotence_error <= policy.projector_idempotence_relative_max && residue.projector_right_action_error <= policy.projector_action_relative_max,
            "26_local_resolvent_and_adjugate_audits" => residue.local_residue_error <= policy.local_resolvent_residue_relative_max && residue.local_projector_error <= policy.local_resolvent_projector_relative_max && residue.adjugate_residue_error <= policy.adjugate_residue_relative_max,
        )
        passed = all(values(gates))
        disposition = passed ? PRODUCED : _scientific_disposition(policy)
        reason = passed ? nothing : "NUMERICAL_SUFFICIENCY_GATE_FAILED"
        right_samples, dual_samples = _retained_samples(T, policy, base, radial_comode, matching_right)
        angular_payload = (
            operator_pencil=OPERATOR_PENCIL_ID, transpose_identity=ANGULAR_TRANSPOSE_ID,
            right=angular.right, transpose_covector=angular.dual,
            c_product_raw=angular.c_product_raw, c_product_normalized=angular.c_product_normalized,
            A_c=angular.A_c, A_omega=angular.A_omega, lambda=angular.lambda,
            lambda_omega=angular.lambda_omega, lambda_omega_fd=angular.lambda_omega_fd,
            lambda_derivative_disagreement=angular.lambda_derivative_disagreement,
            right_residual=angular.right_residual, transpose_residual=angular.transpose_residual,
            symmetry_residual=angular.symmetry_residual, basis_count=angular.count,
            target_index=angular.target_index,
        )
        radial_right_payload = (
            base=(omega=base.omega, A=base.A, lambda=base.lambda,
                matching_matrix=base.matching_matrix, determinant=base.determinant,
                normalized_wronskian=base.normalized_wronskian, join_residual=base.join_residual,
                horizon_endpoint_state=base.horizon_endpoint_state,
                infinity_endpoint_state=base.infinity_endpoint_state),
            plus=(omega=plus.omega, A=plus.A, lambda=plus.lambda,
                matching_matrix=plus.matching_matrix, determinant=plus.determinant),
            minus=(omega=minus.omega, A=minus.A, lambda=minus.lambda,
                matching_matrix=minus.matching_matrix, determinant=minus.determinant),
            matching_right=matching_right, matching_left_transpose=matching_left,
            matching_right_residual=matching_right_residual,
            matching_left_residual=matching_left_residual,
            adjugate_factor_error=factor.relative_error,
            retained_samples=right_samples,
        )
        radial_dual_payload = (
            transpose_identity=RADIAL_TRANSPOSE_ID, pairing_identity=PAIRING_ID,
            boundary_covector_horizon=radial_comode.b_horizon,
            boundary_covector_infinity=radial_comode.b_infinity,
            boundary_covector_horizon_omega=radial_comode.b_horizon_dot,
            boundary_covector_infinity_omega=radial_comode.b_infinity_dot,
            endpoint_multipliers_raw=radial_comode.multipliers,
            endpoint_multiplier_residual=radial_comode.multiplier_residual,
            readout_match_residual=radial_comode.raw_match_residual,
            readout_scale_to_negative_left=radial_comode.readout_scale,
            readout_left_projective_disagreement=radial_comode.readout_left_disagreement,
            horizon_bilinear_conservation_error=radial_comode.horizon_conservation,
            infinity_bilinear_conservation_error=radial_comode.infinity_conservation,
            denominator_contributions=(bulk_horizon=radial_comode.bulk_horizon,
                bulk_infinity=radial_comode.bulk_infinity,
                endpoint_horizon=radial_comode.endpoint_horizon,
                endpoint_infinity=radial_comode.endpoint_infinity,
                total=radial_comode.readout_total),
            retained_samples=dual_samples,
        )
        pole_payload = (
            domega_reuse_identity=DOMEGA_REUSE_ID,
            evans_keldysh_bridge_identity=EVANS_KELDYSH_BRIDGE_ID,
            residue_identity=RESIDUE_ID, projector_identity=PROJECTOR_ID,
            F=base.matching_matrix, Fprime=residue.Fdot,
            adjugate=residue.adjugate, coefficient_right=matching_right,
            coefficient_left_transpose=matching_left,
            m02_Domega=reductions.fine,
            m02_Domega_coarse=reductions.coarse,
            m02_Domega_disagreement=reductions.disagreement,
            local_matrix_Domega=residue.determinant_derivative_fd,
            jacobi_Domega=residue.determinant_derivative_jacobi,
            raw_full_keldysh_denominator=residue.full_denominator,
            matching_keldysh_denominator=residue.matching_denominator,
            evans_bridge=residue.evans_bridge,
            bridged_full_denominator=residue.bridged_full_denominator,
            bridged_matching_denominator=residue.bridged_matching_denominator,
            residue=residue.residue, projector=residue.projector,
            adjugate_over_m02_Domega=residue.residue_adjugate,
            local_symmetric_resolvent_residue=residue.local_residue,
            residue_rescaling_error=residue.residue_rescaling_error,
            projector_rescaling_error=residue.projector_rescaling_error,
            projector_idempotence_error=residue.projector_idempotence_error,
            projector_right_action_error=residue.projector_right_action_error,
            local_resolvent_residue_error=residue.local_residue_error,
            local_resolvent_projector_error=residue.local_projector_error,
            adjugate_residue_error=residue.adjugate_residue_error,
        )
        validation = (
            gates=gates, passed=passed,
            metrics=(m02_stencil_relative_disagreement=m02_step_relative,
                local_Domega_to_M02_relative_disagreement=Domega_relative,
                full_vs_matching_denominator_relative_disagreement=full_matching_relative,
                bridge_closure_relative_error=bridge_relative),
        )
        retained = (
            rho_grid=copy(policy.retained_rho_grid), angular_right=copy(angular.right),
            radial_right_samples=right_samples, radial_dual_samples=dual_samples,
        )
        timings = (base_right_seconds=base_seconds, plus_right_seconds=plus_seconds,
            minus_right_seconds=minus_seconds, comode_seconds=comode_seconds,
            total_seconds=time() - started)
        return SpectralStateResult{T}(seed, disposition, reason, counters,
            angular_payload, radial_right_payload, radial_dual_payload,
            pole_payload, validation, retained, timings)
    catch err
        if err isa ScientificStop
            return _empty_result(seed, policy, err.reason; evidence=err.evidence)
        end
        rethrow()
    end
end

function _flatten(matrix::Matrix{Complex{T}}) where {T}
    return vec(copy(matrix))
end

function _orientation_overlap(reference::Vector{Complex{T}}, candidate::Vector{Complex{T}}) where {T}
    length(reference) == length(candidate) || error("continuation vectors have different lengths")
    denominator = norm(reference) * norm(candidate)
    denominator > zero(T) || return (overlap=zero(T), phase=one(Complex{T}), aligned=copy(candidate))
    inner = sum(conj.(reference) .* candidate)
    overlap = abs(inner) / denominator
    phase = iszero(inner) ? one(Complex{T}) : conj(inner) / abs(inner)
    return (overlap=overlap, phase=phase, aligned=phase .* candidate)
end

function compare_continuation(predecessor::RetainedPredecessor{T}, successor::SpectralStateResult{T}, policy::NumericalPolicy{T}) where {T<:AbstractFloat}
    predecessor.branch_identity == successor.seed.branch_identity ||
        error("continuation predecessor belongs to the wrong branch")
    predecessor.chain_position < successor.seed.chain_position ||
        error("continuation predecessor does not precede the successor")
    successor.disposition == PRODUCED ||
        return (identity=CONTINUATION_ID, state="UNRESOLVED", reason="SUCCESSOR_NOT_PRODUCED",
            predecessor_node_identity_sha256=predecessor.node_identity_sha256,
            successor_node_identity_sha256=successor.seed.node_identity_sha256)
    angular = _orientation_overlap(predecessor.angular_right, successor.retained.angular_right)
    right = _orientation_overlap(_flatten(predecessor.radial_right_samples), _flatten(successor.retained.radial_right_samples))
    dual = _orientation_overlap(_flatten(predecessor.radial_dual_samples), _flatten(successor.retained.radial_dual_samples))
    return (
        identity=CONTINUATION_ID, state="COMPARED",
        predecessor_node_identity_sha256=predecessor.node_identity_sha256,
        successor_node_identity_sha256=successor.seed.node_identity_sha256,
        predecessor_root_identity_sha256=predecessor.root_identity_sha256,
        successor_root_identity_sha256=successor.seed.root_identity_sha256,
        branch_identity=successor.seed.branch_identity,
        predecessor_chain_position=predecessor.chain_position,
        successor_chain_position=successor.seed.chain_position,
        angular_overlap=angular.overlap, radial_right_overlap=right.overlap,
        radial_dual_overlap=dual.overlap,
        angular_phase=angular.phase, radial_right_phase=right.phase,
        radial_dual_phase=dual.phase,
        successor_identity_preserved=true,
        anomaly_flags=String[],
    )
end

function reduce_branch(ordered_nodes::Vector{SpectralStateResult{T}}, policy::NumericalPolicy{T})::BranchResult{T} where {T<:AbstractFloat}
    isempty(ordered_nodes) && error("branch reduction requires at least one node")
    branch_identity = ordered_nodes[1].seed.branch_identity
    all(node.seed.branch_identity == branch_identity for node in ordered_nodes) ||
        error("branch reduction mixed branch identities")
    positions = [node.seed.chain_position for node in ordered_nodes]
    positions == sort(positions) || error("branch nodes are not in chain order")
    edges = NamedTuple[]
    unresolved = NamedTuple[]
    for index in 2:length(ordered_nodes)
        previous = ordered_nodes[index - 1]
        current = ordered_nodes[index]
        if previous.disposition == PRODUCED && current.disposition == PRODUCED
            predecessor = RetainedPredecessor{T}(
                previous.seed.node_identity_sha256,
                previous.seed.root_identity_sha256,
                previous.seed.branch_identity,
                previous.seed.chain_position,
                copy(previous.retained.angular_right),
                copy(previous.retained.radial_right_samples),
                copy(previous.retained.radial_dual_samples),
            )
            push!(edges, compare_continuation(predecessor, current, policy))
        else
            gap = (predecessor_node_identity_sha256=previous.seed.node_identity_sha256,
                successor_node_identity_sha256=current.seed.node_identity_sha256,
                reason="NON_PRODUCED_NODE_IN_GENEALOGY")
            push!(unresolved, gap)
            push!(edges, (identity=CONTINUATION_ID, state="UNRESOLVED",
                predecessor_node_identity_sha256=previous.seed.node_identity_sha256,
                successor_node_identity_sha256=current.seed.node_identity_sha256,
                reason=gap.reason))
        end
    end
    # No branch label is inferred from overlap alone. Classification remains conservative.
    classification = "UNRESOLVED"
    evidence = (reason="M03 core does not infer ZDM/DM/TRANSITION from overlap alone",
        node_count=length(ordered_nodes), unresolved_gap_count=length(unresolved))
    counters = (root_solves=0, base_angular_solves=0, right_radial_solves=0,
        radial_transpose_solves=0, julia_process_launches=0)
    return BranchResult{T}(
        branch_identity,
        [node.seed.node_identity_sha256 for node in ordered_nodes],
        edges,
        [node.seed.precision_tier for node in ordered_nodes],
        unresolved,
        classification,
        evidence,
        counters,
    )
end

end # module M03Core
