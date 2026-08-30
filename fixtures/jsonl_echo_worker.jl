using SHA

for (index, line) in enumerate(eachline(stdin))
    payload = Vector{UInt8}(codeunits(line))
    digest = bytes2hex(sha256(payload))
    println("{\"index\":$(index - 1),\"input_bytes\":$(length(payload)),\"input_sha256\":\"$(digest)\"}")
    flush(stdout)
end
