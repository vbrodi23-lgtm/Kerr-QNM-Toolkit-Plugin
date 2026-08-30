module ToolkitCanaryProject

export damped_frequency

damped_frequency(real_part, damping) = complex(real_part, -abs(damping))

end
