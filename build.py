#!/usr/bin/env python3

"""
Generate the run0edit script by inserting the inner script into the main script.
"""

import os
import stat

with open("./run0edit_main.py", "r", encoding="utf-8") as f:
    main_script = f.read()

with open("./run0edit_inner.py", "r", encoding="utf-8") as f:
    inner_script = f.read()

PLACEHOLDER = "{{ SCRIPT }}"

if "'''" in inner_script:
    raise ValueError("run0edit_inner.py must not contain triple single-quotes (''')")
if PLACEHOLDER not in main_script:
    raise ValueError(f"Placeholder string '{PLACEHOLDER}' missing from run0edit_main.py")
main_script = main_script.replace(PLACEHOLDER, inner_script, 1)
if PLACEHOLDER in main_script:
    raise ValueError(f"""\
    Placeholder string '{PLACEHOLDER}' still present in run0edit_main.py after substitution;
    something has gone wrong with the build script!""")

with open("./run0edit", "w", encoding="utf-8") as f:
    f.write(main_script)

mode = os.stat("./run0edit").st_mode
os.chmod("./run0edit", mode | stat.S_IXUSR)
print("run0edit script generated.")
