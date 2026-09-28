# Awal Script

Glyphs App scripts by Awal Studio, organized by task. Copy the script or folder you need into your Glyphs Scripts folder, then reload scripts in Glyphs.

| Folder | Scripts |
| --- | --- |
| `Arabic-Glypher` | AutoVertical Metrics |
| `Kerning` | Assign Kerning Classes |
| `Mindspace-AI` | Mindspace |
| `Path-Tools` | Blend Between Paths |
| `QA-Check` | Check Node Correspondence, Touch Glyphs Check |
| `Plugins` | [Spacing Pilot 1.9.3](Plugins/SpacingPilot-1.9.3.zip) for Glyphs 3 and 4 |
| `SVG-Export` | SVG Export, export_glyphs_svg |
| `Unicode-Encoding` | Assign Unicode, Set Production Names from Unicode |

`Mindspace-AI/Mindspace.py` is the current loader. It fetches the application from the Mindspace server using a local `~/.mindspace/awal_config.json`; the server source and credentials are not in this repository.

Unzip `SpacingPilot-1.9.3.zip` and install the `.glyphsPlugin` in Glyphs. First use requires internet and an email registered for activation. The local `SpacingPilot/` development folder is excluded from this repository.

`Assign Unicode.py` handles Arabic Unicode and missing glyphs in one pass. `Blend Between Paths.py` checks path alignment before interpolation. `Set Production Names from Unicode.py` and `SVG Export.py` cover production naming and selected-glyph SVG export. These scripts retain MIT terms in [`licenses/Awal-Studio-MIT.txt`](licenses/Awal-Studio-MIT.txt).
