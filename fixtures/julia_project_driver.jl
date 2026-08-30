using Pkg

length(ARGS) == 1 || error("usage: julia_project_driver.jl ACTION")
action = ARGS[1]

if action == "status"
    Pkg.status()
elseif action == "instantiate"
    Pkg.instantiate()
elseif action == "precompile"
    Pkg.precompile()
elseif action == "resolve"
    Pkg.resolve()
elseif action == "test"
    Pkg.test()
else
    error("unsupported Julia project action: $(action)")
end
