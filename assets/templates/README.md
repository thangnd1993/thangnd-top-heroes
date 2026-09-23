# Screen-recognition templates

Templates are cropped from real, explicitly targeted Android screenshots. Each PNG has a neighboring
JSON metadata file defining its state, expected normalized region, threshold, and required/optional role.
Full diagnostic screenshots remain outside Git under `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision`.

Recovery also recognizes the paired Stranger Things startup title and loading caption from the saved
index-11 65% loading frame. It recognizes the later login-assistance modal from two independent text
anchors. These states are observation-only: recovery still sends no input when a popup has no reviewed
handler.
