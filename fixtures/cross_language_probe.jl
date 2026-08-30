using SHA

length(ARGS) == 2 || error("usage: cross_language_probe.jl INPUT OUTPUT")
input_path, output_path = ARGS
payload = read(input_path)
digest = bytes2hex(sha256(payload))
open(output_path, "w") do io
    write(io, "{\"schema_version\":1,\"kind\":\"kerr-qnm-cross-language/v1\",\"input_bytes\":$(length(payload)),\"input_sha256\":\"$(digest)\"}\n")
end
