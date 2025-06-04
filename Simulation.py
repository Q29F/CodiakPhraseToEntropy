# Codiak Core 0.3 — Phrase-to-Entropy Simulation
Simulate symbolic entropy fields using phrases.

var('x y t nu')
assume(nu > 0)

u = function('u')(x, y, t)
v = function('v')(x, y, t)
entropy_density = sqrt(u^2 + v^2)
modifier = sin(x*y + t)
adjusted_entropy = entropy_density * modifier
show(adjusted_entropy)
