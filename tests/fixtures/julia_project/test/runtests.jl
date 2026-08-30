using Test
using ToolkitCanaryProject

@test damped_frequency(0.5, 0.1) == 0.5 - 0.1im
