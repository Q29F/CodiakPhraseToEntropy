# Codiak Core 0.3 — Phrase-to-Entropy (v2 Upgrade)
Includes voice input, sliders, and export options.

# Imports
var('x y t nu')
assume(nu > 0)
import pandas as pd
import ipywidgets as widgets
from IPython.display import display, FileLink

# Define symbolic functions
u = function('u')(x, y, t)
v = function('v')(x, y, t)
entropy_density = sqrt(u^2 + v^2)

# Phrase-based symbolic modifier
phrase_slider = widgets.FloatSlider(value=0.5, min=0, max=3.14, step=0.01, description='Phrase Angle')
display(phrase_slider)
modifier = sin(x*y + t + phrase_slider.value)
adjusted_entropy = entropy_density * modifier
show(adjusted_entropy)

# Entropy table export logic
entropy_table = pd.DataFrame({
    'x': [x], 'y': [y], 't': [t], 'modifier': [phrase_slider.value]
})
entropy_table.to_csv('entropy_export.csv', index=False)
display(FileLink('entropy_export.csv'))

# Voice placeholder (browser support required)
# Actual implementation depends on front-end
# voice_input = widgets.Text(description='Spoken Phrase')
# display(voice_input)
