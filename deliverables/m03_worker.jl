#!/usr/bin/env julia

using JSON
using SHA

include(joinpath(@__DIR__, "m03_core.jl"))
using .M03Core

const RPC_SCHEMA = "windows-solver.m03-json-rpc/2"
const NODE_REQUEST_SCHEMA = "windows-solver.m03-node-request/2"
const BRANCH_REQUEST_SCHEMA = "windows-solver.m03-branch-request/2"
const WORKER_KIND = "m03-julia-protocol-worker"
const WORKER_VERSION = "m03-worker-v2"
const SHA256_RE = r"^[0-9a-f]{64}$"

struct IdentityRejection <: Exception
    message::String
end
struct PolicyRejection <: Exception
    message::String
end
struct SystemFailure <: Exception
    message::String
end
Base.showerror(io::IO, err::IdentityRejection) = print(io, err.message)
Base.showerror(io::IO, err::PolicyRejection) = print(io, err.message)
Base.showerror(io::IO, err::SystemFailure) = print(io, err.message)

function _require_sha(value, label)
    value isa AbstractString || throw(IdentityRejection("$label must be a SHA-256 string"))
    text = String(value)
    occursin(SHA256_RE, text) || throw(IdentityRejection("$label is not a lowercase SHA-256 digest"))
    return text
end

function _require_string(value, label)
    value isa AbstractString || throw(IdentityRejection("$label must be a string"))
    isempty(value) && throw(IdentityRejection("$label must not be empty"))
    return String(value)
end

function _require_bool(value, label)
    value isa Bool || throw(PolicyRejection("$label must be boolean"))
    return value
end

function _require_exact_keys(mapping, keys, label)
    mapping isa AbstractDict || throw(IdentityRejection("$label must be an object"))
    actual = Set(String(key) for key in Base.keys(mapping))
    expected = Set(String(key) for key in keys)
    actual == expected || throw(IdentityRejection("$label has the wrong field set"))
    return mapping
end

function _canonical_json(value)
    if value === nothing
        return "null"
    elseif value isa Bool
        return value ? "true" : "false"
    elseif value isa AbstractString
        return JSON.json(String(value))
    elseif value isa Integer
        return string(value)
    elseif value isa AbstractFloat
        isfinite(value) || throw(SystemFailure("nonfinite value cannot enter canonical JSON"))
        return JSON.json(value)
    elseif value isa AbstractVector
        return "[" * join((_canonical_json(item) for item in value), ",") * "]"
    elseif value isa Tuple
        return "[" * join((_canonical_json(item) for item in value), ",") * "]"
    elseif value isa NamedTuple
        return _canonical_json(Dict(String(key) => getfield(value, key) for key in keys(value)))
    elseif value isa AbstractDict
        entries = String[]
        for key in sort([String(k) for k in Base.keys(value)])
            push!(entries, JSON.json(key) * ":" * _canonical_json(value[key]))
        end
        return "{" * join(entries, ",") * "}"
    else
        throw(SystemFailure("unsupported canonical JSON value of type $(typeof(value))"))
    end
end

_sha256_text(text::AbstractString) = bytes2hex(SHA.sha256(codeunits(text)))

function _canonical_sha256(mapping)
    return _sha256_text(_canonical_json(mapping))
end

function _request_material(request)
    material = Dict{String,Any}()
    for (key, value) in request
        String(key) == "request_identity_sha256" && continue
        material[String(key)] = value
    end
    return material
end

function _response_with_identity(response::Dict{String,Any})
    material = Dict{String,Any}(response)
    pop!(material, "response_identity_sha256", nothing)
    response["response_identity_sha256"] = _canonical_sha256(material)
    return response
end

function _emit(response)
    println(_canonical_json(response))
    flush(stdout)
end

function _diagnostic(message)
    println(stderr, message)
    flush(stderr)
end

function _precision_bits(tier::String)
    tier == "bigfloat-40" && return 165
    tier == "bigfloat-80" && return 298
    throw(PolicyRejection("unsupported M03 precision tier: $tier"))
end

function _parse_decimal(::Type{T}, text, label) where {T<:AbstractFloat}
    canonical = _require_string(text, label)
    value = try
        parse(T, canonical)
    catch err
        throw(IdentityRejection("$label is not a valid decimal: $(sprint(showerror, err))"))
    end
    isfinite(value) || throw(IdentityRejection("$label is nonfinite"))
    return canonical, value
end

function _parse_complex(::Type{T}, mapping, label) where {T<:AbstractFloat}
    _require_exact_keys(mapping, ["real", "imaginary"], label)
    real_text, re = _parse_decimal(T, mapping["real"], "$label.real")
    imag_text, im = _parse_decimal(T, mapping["imaginary"], "$label.imaginary")
    return (real_text=real_text, imaginary_text=imag_text, value=Complex{T}(re, im))
end

function _scientific_jsonable(value)
    if value === nothing || value isa Bool || value isa Integer || value isa AbstractString
        return value
    elseif value isa Complex
        return Dict("real" => string(real(value)), "imaginary" => string(imag(value)))
    elseif value isa BigFloat
        return string(value)
    elseif value isa AbstractFloat
        return string(value)
    elseif value isa NamedTuple
        return Dict(String(key) => _scientific_jsonable(getfield(value, key)) for key in keys(value))
    elseif value isa AbstractDict
        return Dict(String(key) => _scientific_jsonable(item) for (key, item) in value)
    elseif value isa AbstractMatrix
        return [[_scientific_jsonable(value[row, column]) for column in axes(value, 2)] for row in axes(value, 1)]
    elseif value isa AbstractVector
        return [_scientific_jsonable(item) for item in value]
    elseif value isa Tuple
        return [_scientific_jsonable(item) for item in value]
    else
        throw(SystemFailure("cannot serialize scientific value of type $(typeof(value))"))
    end
end

function _parse_scientific_complex(::Type{T}, value, label) where {T<:AbstractFloat}
    parsed = _parse_complex(T, value, label)
    return parsed.value
end

function _parse_complex_vector(::Type{T}, values, label) where {T<:AbstractFloat}
    values isa AbstractVector || throw(IdentityRejection("$label must be an array"))
    return Complex{T}[_parse_scientific_complex(T, item, "$label[$index]") for (index, item) in enumerate(values)]
end

function _parse_complex_matrix(::Type{T}, values, label) where {T<:AbstractFloat}
    values isa AbstractVector || throw(IdentityRejection("$label must be a row array"))
    isempty(values) && return zeros(Complex{T}, 0, 0)
    column_count = length(values[1])
    all(row isa AbstractVector && length(row) == column_count for row in values) ||
        throw(IdentityRejection("$label rows have inconsistent lengths"))
    matrix = zeros(Complex{T}, length(values), column_count)
    for row in eachindex(values), column in 1:column_count
        matrix[row, column] = _parse_scientific_complex(T, values[row][column], "$label[$row][$column]")
    end
    return matrix
end

function _validate_rpc(request)
    _require_exact_keys(request, ["schema", "request_id", "method", "params", "request_identity_sha256"], "RPC envelope")
    request["schema"] == RPC_SCHEMA || throw(IdentityRejection("wrong M03 RPC schema"))
    request_id = _require_string(request["request_id"], "request_id")
    method = _require_string(request["method"], "method")
    method in ("hello", "probe", "solve_node", "reduce_branch", "shutdown") ||
        throw(IdentityRejection("unsupported M03 RPC method: $method"))
    request["params"] isa AbstractDict || throw(IdentityRejection("params must be an object"))
    supplied = _require_sha(request["request_identity_sha256"], "request_identity_sha256")
    observed = _canonical_sha256(_request_material(request))
    supplied == observed || throw(IdentityRejection("request_identity_sha256 does not authenticate the RPC envelope"))
    return (request_id=request_id, method=method, request_identity_sha256=supplied, params=request["params"])
end

function _parse_mode(params)
    mode = params["mode"]
    _require_exact_keys(mode, ["s", "ell", "m", "n"], "mode")
    all(mode[key] isa Integer for key in ("s", "ell", "m", "n")) ||
        throw(IdentityRejection("mode fields must be integers"))
    return (s=Int(mode["s"]), ell=Int(mode["ell"]), m=Int(mode["m"]), n=Int(mode["n"]))
end

function _parse_stencil(::Type{T}, evidence, root_identity, policy_bits) where {T<:AbstractFloat}
    evidence isa AbstractDict || throw(IdentityRejection("m02_domega_evidence must be an object"))
    request_sha = _require_sha(evidence["request_sha256"], "m02_domega_evidence.request_sha256")
    derivative_root = _require_sha(evidence["root_identity_sha256"], "m02_domega_evidence.root_identity_sha256")
    derivative_root == root_identity || throw(IdentityRejection("M02 derivative evidence is bound to a different root"))
    operation = _require_string(evidence["scientific_operation_identity"], "m02_domega_evidence.scientific_operation_identity")
    family = _require_string(evidence["determinant_family"], "m02_domega_evidence.determinant_family")
    convention = _require_string(evidence["determinant_convention"], "m02_domega_evidence.determinant_convention")
    normalisation = _require_string(evidence["determinant_normalisation"], "m02_domega_evidence.determinant_normalisation")
    operation == "canonical-exterior-background-wronskian/v1" || throw(IdentityRejection("wrong M02 derivative scientific operation"))
    family == "exterior-wronskian/v1" || throw(IdentityRejection("wrong M02 derivative family"))
    convention == "wronskian-perturbed-Xin-with-Xup/v1" || throw(IdentityRejection("wrong M02 derivative convention"))
    normalisation == "unit-asymptotic-branch-wronskian/v1" || throw(IdentityRejection("wrong M02 derivative normalisation"))

    h_text, h = _parse_decimal(T, get(evidence, "h", get(evidence, "frequency_step", nothing)), "m02_domega_evidence.h")

    function explicit_or_sample(name, role)
        if haskey(evidence, name)
            return evidence[name]
        end
        samples = get(evidence, "samples", nothing)
        samples isa AbstractVector || throw(IdentityRejection("M02 derivative evidence lacks $name and raw samples"))
        matched = [sample for sample in samples if string(get(sample, "sample_role", "")) == role]
        length(matched) == 1 || throw(IdentityRejection("M02 derivative sample role $role is missing or duplicated"))
        return matched[1]["determinant"]
    end

    D0 = _parse_scientific_complex(T, explicit_or_sample("D0", "D0"), "D0")
    Dph = _parse_scientific_complex(T, explicit_or_sample("D_plus_h", "DOMEGA_REAL_PLUS_H"), "D_plus_h")
    Dmh = _parse_scientific_complex(T, explicit_or_sample("D_minus_h", "DOMEGA_REAL_MINUS_H"), "D_minus_h")
    Dp2 = _parse_scientific_complex(T, explicit_or_sample("D_plus_half_h", "DOMEGA_REAL_PLUS_HALF_H"), "D_plus_half_h")
    Dm2 = _parse_scientific_complex(T, explicit_or_sample("D_minus_half_h", "DOMEGA_REAL_MINUS_HALF_H"), "D_minus_half_h")
    coarse = haskey(evidence, "coarse_derivative") ?
        _parse_scientific_complex(T, evidence["coarse_derivative"], "coarse_derivative") :
        (Dph - Dmh) / (T(2) * h)
    fine = haskey(evidence, "fine_derivative") ?
        _parse_scientific_complex(T, evidence["fine_derivative"], "fine_derivative") :
        (Dp2 - Dm2) / h
    disagreement_text = string(get(evidence, "disagreement_abs", get(evidence, "step_disagreement_abs", abs(fine - coarse))))
    _, disagreement = _parse_decimal(T, disagreement_text, "m02_domega_evidence.disagreement_abs")
    readout_text = _require_string(get(evidence, "readout_radius", nothing), "m02_domega_evidence.readout_radius")
    rho_inner_text = _require_string(get(evidence, "selected_horizon_rho", get(evidence, "rho_inner", nothing)), "m02_domega_evidence.rho_inner")
    rho_outer_text = _require_string(get(evidence, "selected_infinity_rho", get(evidence, "rho_outer", nothing)), "m02_domega_evidence.rho_outer")
    endpoint_order = Int(get(evidence, "endpoint_series_order", get(evidence, "endpoint_order", 0)))
    endpoint_order > 0 || throw(IdentityRejection("M02 derivative endpoint order is invalid"))
    working_bits = Int(get(evidence, "working_precision_bits", policy_bits))
    working_bits in (165, 298) || throw(IdentityRejection("M02 derivative working precision is invalid"))

    return M03Core.DomegaStencil{T}(
        request_sha, derivative_root, family, convention, normalisation, operation,
        h, D0, Dph, Dmh, Dp2, Dm2, coarse, fine, disagreement,
        readout_text, rho_inner_text, rho_outer_text, endpoint_order, working_bits,
    )
end

function _policy_decimal(::Type{T}, mapping, key) where {T<:AbstractFloat}
    haskey(mapping, key) || throw(PolicyRejection("numerical_policy is missing $key"))
    _, value = _parse_decimal(T, mapping[key], "numerical_policy.$key")
    return value
end

function _parse_policy(::Type{T}, mapping, identity, tier, bits) where {T<:AbstractFloat}
    mapping isa AbstractDict || throw(PolicyRejection("numerical_policy must be an object"))
    retained = get(mapping, "retained_rho_grid", nothing)
    retained isa AbstractVector && !isempty(retained) || throw(PolicyRejection("numerical_policy.retained_rho_grid must be nonempty"))
    rho_grid = T[_parse_decimal(T, item, "retained_rho_grid[$index]")[2] for (index, item) in enumerate(retained)]
    function complex_scale(key)
        value = get(mapping, key, nothing)
        value isa AbstractDict || throw(PolicyRejection("numerical_policy.$key must be a complex object"))
        return _parse_complex(T, value, "numerical_policy.$key").value
    end
    return M03Core.NumericalPolicy{T}(
        identity, tier, bits,
        _policy_decimal(T, mapping, "readout_radius"),
        _policy_decimal(T, mapping, "rho_inner"),
        _policy_decimal(T, mapping, "rho_outer"),
        Int(get(mapping, "endpoint_order", 0)),
        Int(get(mapping, "angular_pad", 0)),
        _policy_decimal(T, mapping, "ode_reltol"),
        _policy_decimal(T, mapping, "ode_abstol"),
        _policy_decimal(T, mapping, "angular_derivative_step"),
        _policy_decimal(T, mapping, "frequency_audit_step"),
        Int(get(mapping, "quadrature_panels", 0)),
        _policy_decimal(T, mapping, "required_reliable_digits"),
        _policy_decimal(T, mapping, "maximum_horizon_distance"),
        Int(get(mapping, "ode_maxiters", 0)),
        _policy_decimal(T, mapping, "angular_right_residual_max"),
        _policy_decimal(T, mapping, "angular_transpose_residual_max"),
        _policy_decimal(T, mapping, "angular_symmetry_residual_max"),
        _policy_decimal(T, mapping, "angular_c_product_min"),
        _policy_decimal(T, mapping, "lambda_derivative_disagreement_max"),
        _policy_decimal(T, mapping, "radial_wronskian_max"),
        _policy_decimal(T, mapping, "matching_right_null_max"),
        _policy_decimal(T, mapping, "matching_left_null_max"),
        _policy_decimal(T, mapping, "adjugate_factorization_max"),
        _policy_decimal(T, mapping, "transpose_endpoint_residual_max"),
        _policy_decimal(T, mapping, "transpose_readout_residual_max"),
        _policy_decimal(T, mapping, "dual_projective_disagreement_max"),
        _policy_decimal(T, mapping, "bilinear_conservation_max"),
        _policy_decimal(T, mapping, "domega_stencil_relative_disagreement_max"),
        _policy_decimal(T, mapping, "local_domega_to_m02_relative_max"),
        _policy_decimal(T, mapping, "contour_to_readout_denominator_relative_max"),
        _policy_decimal(T, mapping, "bridge_closure_relative_max"),
        _policy_decimal(T, mapping, "residue_rescaling_relative_max"),
        _policy_decimal(T, mapping, "projector_rescaling_relative_max"),
        _policy_decimal(T, mapping, "projector_idempotence_relative_max"),
        _policy_decimal(T, mapping, "projector_action_relative_max"),
        _policy_decimal(T, mapping, "local_resolvent_residue_relative_max"),
        _policy_decimal(T, mapping, "local_resolvent_projector_relative_max"),
        _policy_decimal(T, mapping, "adjugate_residue_relative_max"),
        rho_grid,
        complex_scale("right_rescaling"),
        complex_scale("comode_rescaling"),
    )
end

function _parse_node_request(::Type{T}, params, tier, bits) where {T<:AbstractFloat}
    required = [
        "request_schema", "node_identity_sha256", "mode", "spin_identity",
        "frozen_omega", "frozen_A", "upstream_root_identity",
        "background_identity_sha256", "m02_handoff_sha256", "branch_identity",
        "chain_position", "predecessor_state_reference", "precision_tier",
        "m02_domega_evidence", "numerical_policy_identity", "numerical_policy",
        "output_root", "source_revision", "root_movement_permitted",
        "base_angular_eigenvalue_solve_permitted",
    ]
    _require_exact_keys(params, required, "solve_node params")
    params["request_schema"] == NODE_REQUEST_SCHEMA || throw(IdentityRejection("wrong M03 node request schema"))
    params["precision_tier"] == tier || throw(PolicyRejection("precision tier changed during request parsing"))
    _require_bool(params["root_movement_permitted"], "root_movement_permitted") == false ||
        throw(PolicyRejection("M03 root movement is forbidden"))
    _require_bool(params["base_angular_eigenvalue_solve_permitted"], "base_angular_eigenvalue_solve_permitted") == false ||
        throw(PolicyRejection("M03 base angular eigenvalue solving is forbidden"))
    node_identity = _require_sha(params["node_identity_sha256"], "node_identity_sha256")
    root_identity = _require_sha(params["upstream_root_identity"], "upstream_root_identity")
    background_identity = _require_sha(params["background_identity_sha256"], "background_identity_sha256")
    handoff_identity = _require_sha(params["m02_handoff_sha256"], "m02_handoff_sha256")
    branch_identity = _require_string(params["branch_identity"], "branch_identity")
    params["chain_position"] isa Integer || throw(IdentityRejection("chain_position must be an integer"))
    mode = _parse_mode(params)
    spin_mapping = params["spin_identity"]
    _require_exact_keys(spin_mapping, ["text"], "spin_identity")
    spin_text, spin = _parse_decimal(T, spin_mapping["text"], "spin_identity.text")
    omega = _parse_complex(T, params["frozen_omega"], "frozen_omega")
    A = _parse_complex(T, params["frozen_A"], "frozen_A")
    imag(omega.value) < zero(T) || throw(IdentityRejection("frozen omega violates the damped-root sign convention"))
    policy_identity = _require_sha(params["numerical_policy_identity"], "numerical_policy_identity")
    policy = _parse_policy(T, params["numerical_policy"], policy_identity, tier, bits)
    policy.endpoint_order > 0 || throw(PolicyRejection("endpoint_order must be positive"))
    policy.angular_pad >= 0 || throw(PolicyRejection("angular_pad must be nonnegative"))
    policy.quadrature_panels >= 2 || throw(PolicyRejection("quadrature_panels must be at least 2"))
    policy.ode_maxiters > 0 || throw(PolicyRejection("ode_maxiters must be positive"))
    stencil = _parse_stencil(T, params["m02_domega_evidence"], root_identity, bits)
    # Exact policy/evidence geometry conservation. Values are parsed for arithmetic,
    # but the authoritative request text remains untouched in request.json and echoes.
    parse(T, stencil.readout_radius_text) == policy.readout_radius || throw(IdentityRejection("M02 Domega readout radius disagrees with M03 policy"))
    parse(T, stencil.rho_inner_text) == policy.rho_inner || throw(IdentityRejection("M02 Domega horizon rho disagrees with M03 policy"))
    parse(T, stencil.rho_outer_text) == policy.rho_outer || throw(IdentityRejection("M02 Domega infinity rho disagrees with M03 policy"))
    stencil.endpoint_order == policy.endpoint_order || throw(IdentityRejection("M02 Domega endpoint order disagrees with M03 policy"))
    seed = M03Core.RootSeed{T}(
        node_identity, root_identity, background_identity, handoff_identity,
        mode.s, mode.ell, mode.m, mode.n, branch_identity, Int(params["chain_position"]),
        spin_text, spin, omega.real_text, omega.imaginary_text, omega.value,
        A.real_text, A.imaginary_text, A.value, tier,
    )
    return (
        seed=seed, stencil=stencil, policy=policy,
        output_root=_require_string(params["output_root"], "output_root"),
        source_revision=_require_string(params["source_revision"], "source_revision"),
        predecessor=params["predecessor_state_reference"],
        canonical_echo=Dict(
            "spin" => spin_text,
            "omega" => Dict("real" => omega.real_text, "imaginary" => omega.imaginary_text),
            "A" => Dict("real" => A.real_text, "imaginary" => A.imaginary_text),
            "root_identity_sha256" => root_identity,
            "handoff_identity_sha256" => handoff_identity,
            "policy_identity_sha256" => policy_identity,
        ),
    )
end

function _safe_node_directory(output_root, node_identity)
    _require_sha(node_identity, "node identity path component")
    root = abspath(output_root)
    nodes = joinpath(root, "nodes")
    final = joinpath(nodes, node_identity)
    dirname(final) == nodes || throw(IdentityRejection("node artifact path escaped the nodes directory"))
    return root, nodes, final
end

function _write_canonical(path, value)
    open(path, "w") do io
        write(io, _canonical_json(value))
        write(io, "\n")
        flush(io)
    end
    return path
end

function _file_sha256(path)
    open(path, "r") do io
        return bytes2hex(SHA.sha256(io))
    end
end

function _verify_manifest(final_directory, manifest)
    files = manifest["files"]
    for (name, expected) in files
        path = joinpath(final_directory, String(name))
        isfile(path) || throw(SystemFailure("published artifact is missing $name"))
        _file_sha256(path) == expected || throw(SystemFailure("published artifact hash mismatch for $name"))
    end
    return true
end

function _read_manifest(final_directory)
    path = joinpath(final_directory, "node-manifest.json")
    isfile(path) || throw(IdentityRejection("existing node directory has no manifest"))
    return JSON.parsefile(path), path
end

function _reuse_if_complete(final_directory, request_identity)
    isdir(final_directory) || return nothing
    manifest, path = _read_manifest(final_directory)
    get(manifest, "request_identity_sha256", nothing) == request_identity ||
        throw(IdentityRejection("existing node artifact belongs to a different request"))
    _verify_manifest(final_directory, manifest)
    return (
        disposition="REUSED",
        artifact_path=final_directory,
        artifact_sha256=_file_sha256(path),
        manifest=manifest,
    )
end

function _load_predecessor(::Type{T}, reference, successor_branch) where {T<:AbstractFloat}
    reference === nothing && return nothing
    reference isa AbstractDict || throw(IdentityRejection("predecessor_state_reference must be null or an object"))
    _require_exact_keys(reference, ["artifact_path", "node_identity_sha256", "artifact_sha256"], "predecessor_state_reference")
    path = abspath(_require_string(reference["artifact_path"], "predecessor_state_reference.artifact_path"))
    node_identity = _require_sha(reference["node_identity_sha256"], "predecessor_state_reference.node_identity_sha256")
    expected_manifest_hash = _require_sha(reference["artifact_sha256"], "predecessor_state_reference.artifact_sha256")
    manifest, manifest_path = _read_manifest(path)
    _file_sha256(manifest_path) == expected_manifest_hash || throw(IdentityRejection("predecessor manifest digest is stale"))
    get(manifest, "node_identity_sha256", nothing) == node_identity || throw(IdentityRejection("predecessor node identity mismatch"))
    _verify_manifest(path, manifest)
    retained = JSON.parsefile(joinpath(path, "retained-state.json"))
    branch = _require_string(retained["branch_identity"], "predecessor retained branch")
    branch == successor_branch || throw(IdentityRejection("predecessor belongs to the wrong branch"))
    return M03Core.RetainedPredecessor{T}(
        node_identity,
        _require_sha(retained["root_identity_sha256"], "predecessor root identity"),
        branch,
        Int(retained["chain_position"]),
        _parse_complex_vector(T, retained["angular_right"], "predecessor.angular_right"),
        _parse_complex_matrix(T, retained["radial_right_samples"], "predecessor.radial_right_samples"),
        _parse_complex_matrix(T, retained["radial_dual_samples"], "predecessor.radial_dual_samples"),
    )
end

function _publish_node(request, rpc, parsed, result, continuation)
    root, nodes, final = _safe_node_directory(parsed.output_root, parsed.seed.node_identity_sha256)
    mkpath(nodes)
    temporary = joinpath(nodes, ".tmp-$(parsed.seed.node_identity_sha256)-$(getpid())-$(time_ns())")
    ispath(temporary) && rm(temporary; recursive=true, force=true)
    mkdir(temporary)
    try
        request_payload = request
        angular_payload = _scientific_jsonable(result.angular)
        radial_right_payload = _scientific_jsonable(result.radial_right)
        radial_dual_payload = _scientific_jsonable(result.radial_dual)
        pole_payload = _scientific_jsonable(result.pole_object)
        validation_payload = Dict(
            "disposition" => result.disposition,
            "reason_code" => result.reason_code,
            "counters" => _scientific_jsonable(result.counters),
            "validation" => _scientific_jsonable(result.validation),
            "timings" => _scientific_jsonable(result.timings),
        )
        retained_payload = Dict(
            "node_identity_sha256" => result.seed.node_identity_sha256,
            "root_identity_sha256" => result.seed.root_identity_sha256,
            "branch_identity" => result.seed.branch_identity,
            "chain_position" => result.seed.chain_position,
            "precision_tier" => result.seed.precision_tier,
            "rho_grid" => _scientific_jsonable(result.retained.rho_grid),
            "angular_right" => _scientific_jsonable(result.retained.angular_right),
            "radial_right_samples" => _scientific_jsonable(result.retained.radial_right_samples),
            "radial_dual_samples" => _scientific_jsonable(result.retained.radial_dual_samples),
        )
        payloads = Dict{String,Any}(
            "request.json" => request_payload,
            "angular-state.json" => angular_payload,
            "radial-right.json" => radial_right_payload,
            "radial-dual.json" => radial_dual_payload,
            "pole-object.json" => pole_payload,
            "validation.json" => validation_payload,
            "retained-state.json" => retained_payload,
        )
        continuation !== nothing && (payloads["continuation.json"] = _scientific_jsonable(continuation))
        hashes = Dict{String,String}()
        for name in sort(collect(keys(payloads)))
            path = joinpath(temporary, name)
            _write_canonical(path, payloads[name])
            hashes[name] = _file_sha256(path)
        end
        manifest = Dict{String,Any}(
            "schema" => "windows-solver.m03-node-manifest/2",
            "request_identity_sha256" => rpc.request_identity_sha256,
            "node_identity_sha256" => result.seed.node_identity_sha256,
            "root_identity_sha256" => result.seed.root_identity_sha256,
            "handoff_identity_sha256" => result.seed.handoff_identity_sha256,
            "background_identity_sha256" => result.seed.background_identity_sha256,
            "branch_identity" => result.seed.branch_identity,
            "chain_position" => result.seed.chain_position,
            "precision_tier" => result.seed.precision_tier,
            "policy_identity_sha256" => result.seed.precision_tier == parsed.policy.precision_tier ? parsed.policy.policy_identity_sha256 : "",
            "source_revision" => parsed.source_revision,
            "core_schema" => M03Core.CORE_SCHEMA,
            "core_version" => M03Core.CORE_VERSION,
            "worker_kind" => WORKER_KIND,
            "worker_version" => WORKER_VERSION,
            "disposition" => result.disposition,
            "reason_code" => result.reason_code,
            "canonical_echo" => parsed.canonical_echo,
            "files" => hashes,
        )
        manifest_path = joinpath(temporary, "node-manifest.json")
        _write_canonical(manifest_path, manifest)
        for (name, digest) in hashes
            _file_sha256(joinpath(temporary, name)) == digest || throw(SystemFailure("temporary artifact hash changed before publication: $name"))
        end
        if isdir(final)
            throw(IdentityRejection("node directory appeared during publication; refusing overwrite"))
        end
        mv(temporary, final)
        final_manifest = joinpath(final, "node-manifest.json")
        _verify_manifest(final, manifest)
        return (artifact_path=final, artifact_sha256=_file_sha256(final_manifest), manifest=manifest)
    catch
        ispath(temporary) && rm(temporary; recursive=true, force=true)
        rethrow()
    end
end

function _node_summary(result, continuation)
    gates = haskey(result.validation, :gates) ? result.validation.gates : Dict{String,Bool}()
    return Dict(
        "gate_count" => length(gates),
        "gate_pass_count" => count(identity, values(gates)),
        "all_gates_passed" => !isempty(gates) && all(values(gates)),
        "counters" => _scientific_jsonable(result.counters),
        "timings" => _scientific_jsonable(result.timings),
        "continuation" => continuation === nothing ? nothing : _scientific_jsonable(continuation),
    )
end

function _handle_solve_node(request, rpc)
    tier = _require_string(rpc.params["precision_tier"], "precision_tier")
    bits = _precision_bits(tier)
    return setprecision(BigFloat, bits) do
        T = BigFloat
        parsed = _parse_node_request(T, rpc.params, tier, bits)
        _, _, final = _safe_node_directory(parsed.output_root, parsed.seed.node_identity_sha256)
        reused = _reuse_if_complete(final, rpc.request_identity_sha256)
        if reused !== nothing
            result = Dict(
                "disposition" => "REUSED",
                "node_identity_sha256" => parsed.seed.node_identity_sha256,
                "root_identity_sha256" => parsed.seed.root_identity_sha256,
                "precision_tier" => tier,
                "artifact_path" => reused.artifact_path,
                "artifact_sha256" => reused.artifact_sha256,
                "reason" => nothing,
                "canonical_echo" => parsed.canonical_echo,
                "summary" => Dict("core_invocations" => 0, "zero_work_reuse" => true),
            )
            return result
        end
        spectral = M03Core.solve_node(parsed.seed, parsed.stencil, parsed.policy)
        predecessor = _load_predecessor(T, parsed.predecessor, parsed.seed.branch_identity)
        continuation = predecessor === nothing ? nothing : M03Core.compare_continuation(predecessor, spectral, parsed.policy)
        publication = _publish_node(request, rpc, parsed, spectral, continuation)
        return Dict(
            "disposition" => spectral.disposition,
            "node_identity_sha256" => spectral.seed.node_identity_sha256,
            "root_identity_sha256" => spectral.seed.root_identity_sha256,
            "precision_tier" => spectral.seed.precision_tier,
            "artifact_path" => publication.artifact_path,
            "artifact_sha256" => publication.artifact_sha256,
            "reason" => spectral.reason_code,
            "canonical_echo" => parsed.canonical_echo,
            "summary" => _node_summary(spectral, continuation),
        )
    end
end

function _result_stub_from_node(::Type{T}, node_path, policy) where {T<:AbstractFloat}
    manifest, _ = _read_manifest(node_path)
    _verify_manifest(node_path, manifest)
    request = JSON.parsefile(joinpath(node_path, "request.json"))
    params = request["params"]
    tier = String(params["precision_tier"])
    parsed = _parse_node_request(T, params, tier, _precision_bits(tier))
    retained_json = JSON.parsefile(joinpath(node_path, "retained-state.json"))
    retained = (
        rho_grid=T[parse(T, string(item)) for item in retained_json["rho_grid"]],
        angular_right=_parse_complex_vector(T, retained_json["angular_right"], "branch.angular_right"),
        radial_right_samples=_parse_complex_matrix(T, retained_json["radial_right_samples"], "branch.radial_right_samples"),
        radial_dual_samples=_parse_complex_matrix(T, retained_json["radial_dual_samples"], "branch.radial_dual_samples"),
    )
    validation_json = JSON.parsefile(joinpath(node_path, "validation.json"))
    disposition = String(validation_json["disposition"])
    reason = get(validation_json, "reason_code", nothing)
    return M03Core.SpectralStateResult{T}(
        parsed.seed, disposition, reason,
        (root_solves=0, base_angular_eigenvalue_solves=0, m02_response_solves=0,
         right_radial_states=0, radial_transpose_states=0),
        (;), (;), (;), (;),
        (gates=Dict{String,Bool}(), passed=disposition == "PRODUCED"),
        retained,
        (total_seconds=0.0,),
    )
end

function _handle_reduce_branch(request, rpc)
    params = rpc.params
    required = ["request_schema", "branch_identity", "ordered_node_references",
        "precision_tier", "numerical_policy_identity", "numerical_policy",
        "output_root", "source_revision"]
    _require_exact_keys(params, required, "reduce_branch params")
    params["request_schema"] == BRANCH_REQUEST_SCHEMA || throw(IdentityRejection("wrong M03 branch request schema"))
    branch_identity = _require_string(params["branch_identity"], "branch_identity")
    tier = _require_string(params["precision_tier"], "precision_tier")
    bits = _precision_bits(tier)
    references = params["ordered_node_references"]
    references isa AbstractVector && !isempty(references) || throw(IdentityRejection("ordered_node_references must be nonempty"))
    return setprecision(BigFloat, bits) do
        T = BigFloat
        policy_identity = _require_sha(params["numerical_policy_identity"], "numerical_policy_identity")
        policy = _parse_policy(T, params["numerical_policy"], policy_identity, tier, bits)
        nodes = M03Core.SpectralStateResult{T}[]
        node_manifest_hashes = String[]
        for (index, reference) in enumerate(references)
            _require_exact_keys(reference, ["artifact_path", "artifact_sha256"], "ordered_node_references[$index]")
            node_path = abspath(_require_string(reference["artifact_path"], "node artifact path"))
            expected = _require_sha(reference["artifact_sha256"], "node artifact sha256")
            manifest, manifest_path = _read_manifest(node_path)
            _file_sha256(manifest_path) == expected || throw(IdentityRejection("node reference $index has a stale manifest hash"))
            get(manifest, "branch_identity", nothing) == branch_identity || throw(IdentityRejection("node reference $index belongs to the wrong branch"))
            _verify_manifest(node_path, manifest)
            push!(nodes, _result_stub_from_node(T, node_path, policy))
            push!(node_manifest_hashes, expected)
        end
        reduced = M03Core.reduce_branch(nodes, policy)
        root = abspath(_require_string(params["output_root"], "output_root"))
        branches = joinpath(root, "branches")
        mkpath(branches)
        branch_digest = _sha256_text(branch_identity)
        final = joinpath(branches, branch_digest)
        if isdir(final)
            manifest_path = joinpath(final, "branch-manifest.json")
            isfile(manifest_path) || throw(IdentityRejection("existing branch directory has no manifest"))
            manifest = JSON.parsefile(manifest_path)
            get(manifest, "request_identity_sha256", nothing) == rpc.request_identity_sha256 ||
                throw(IdentityRejection("existing branch artifact belongs to a different request"))
            return Dict(
                "disposition" => "REUSED",
                "branch_identity" => branch_identity,
                "artifact_path" => final,
                "artifact_sha256" => _file_sha256(manifest_path),
                "reason" => nothing,
                "summary" => Dict("core_invocations" => 0, "zero_work_reuse" => true),
            )
        end
        temporary = joinpath(branches, ".tmp-$branch_digest-$(getpid())-$(time_ns())")
        mkdir(temporary)
        try
            payload = _scientific_jsonable((
                branch_identity=reduced.branch_identity,
                ordered_node_identities=reduced.ordered_node_identities,
                edges=reduced.edges,
                precision_history=reduced.precision_history,
                unresolved_gaps=reduced.unresolved_gaps,
                classification=reduced.classification,
                classification_evidence=reduced.classification_evidence,
                counters=reduced.counters,
            ))
            payload_path = joinpath(temporary, "branch-state.json")
            _write_canonical(payload_path, payload)
            payload_hash = _file_sha256(payload_path)
            manifest = Dict(
                "schema" => "windows-solver.m03-branch-artifact/2",
                "request_identity_sha256" => rpc.request_identity_sha256,
                "branch_identity" => branch_identity,
                "source_revision" => _require_string(params["source_revision"], "source_revision"),
                "ordered_node_manifest_sha256" => node_manifest_hashes,
                "classification" => reduced.classification,
                "files" => Dict("branch-state.json" => payload_hash),
            )
            manifest_path = joinpath(temporary, "branch-manifest.json")
            _write_canonical(manifest_path, manifest)
            mv(temporary, final)
            return Dict(
                "disposition" => "PRODUCED",
                "branch_identity" => branch_identity,
                "artifact_path" => final,
                "artifact_sha256" => _file_sha256(joinpath(final, "branch-manifest.json")),
                "reason" => nothing,
                "summary" => Dict("node_count" => length(nodes), "classification" => reduced.classification,
                    "counters" => _scientific_jsonable(reduced.counters)),
            )
        catch
            ispath(temporary) && rm(temporary; recursive=true, force=true)
            rethrow()
        end
    end
end

function _success_response(rpc, result)
    return _response_with_identity(Dict{String,Any}(
        "schema" => RPC_SCHEMA,
        "request_id" => rpc.request_id,
        "request_identity_sha256" => rpc.request_identity_sha256,
        "ok" => true,
        "result" => result,
        "error" => nothing,
    ))
end

function _error_response(request_id, request_identity, category, message)
    return _response_with_identity(Dict{String,Any}(
        "schema" => RPC_SCHEMA,
        "request_id" => request_id,
        "request_identity_sha256" => request_identity,
        "ok" => false,
        "result" => nothing,
        "error" => Dict("category" => category, "message" => message),
    ))
end

function _dispatch(request)
    rpc = _validate_rpc(request)
    if rpc.method == "hello"
        isempty(rpc.params) || throw(IdentityRejection("hello params must be empty"))
        return rpc, Dict(
            "worker_kind" => WORKER_KIND,
            "worker_version" => WORKER_VERSION,
            "rpc_schema" => RPC_SCHEMA,
            "core_schema" => M03Core.CORE_SCHEMA,
            "core_version" => M03Core.CORE_VERSION,
            "supported_precision_tiers" => ["bigfloat-40", "bigfloat-80"],
            "persistent_process" => true,
        ), false
    elseif rpc.method == "probe"
        isempty(rpc.params) || throw(IdentityRejection("probe params must be empty"))
        return rpc, Dict(
            "status" => "READY",
            "core_loaded" => true,
            "core_schema" => M03Core.CORE_SCHEMA,
            "root_solving_available" => false,
            "base_angular_eigenvalue_solving_available" => false,
        ), false
    elseif rpc.method == "solve_node"
        return rpc, _handle_solve_node(request, rpc), false
    elseif rpc.method == "reduce_branch"
        return rpc, _handle_reduce_branch(request, rpc), false
    elseif rpc.method == "shutdown"
        isempty(rpc.params) || throw(IdentityRejection("shutdown params must be empty"))
        return rpc, Dict("status" => "SHUTDOWN"), true
    end
    error("unreachable RPC method")
end

function server_loop()
    for line in eachline(stdin)
        isempty(strip(line)) && continue
        request_id = "unknown"
        request_identity = "0"^64
        shutdown = false
        try
            request = JSON.parse(line)
            if request isa AbstractDict
                request_id = string(get(request, "request_id", "unknown"))
                request_identity = string(get(request, "request_identity_sha256", "0"^64))
            end
            rpc, result, shutdown = _dispatch(request)
            _emit(_success_response(rpc, result))
        catch err
            category = err isa IdentityRejection ? "IDENTITY_REJECTION" :
                err isa PolicyRejection ? "POLICY_REJECTION" : "SYSTEM_FAILURE"
            message = sprint(showerror, err)
            category == "SYSTEM_FAILURE" && _diagnostic("M03 worker system failure: $message")
            safe_identity = occursin(SHA256_RE, request_identity) ? request_identity : "0"^64
            _emit(_error_response(request_id, safe_identity, category, message))
        end
        shutdown && break
    end
    return nothing
end

if abspath(PROGRAM_FILE) == @__FILE__
    server_loop()
end
