#!/usr/bin/env python3

"""
Generate the run0edit script by inserting the inner script into the main script.
"""

import os

with open("./run0edit-main.sh", "r", encoding="utf-8") as f:
    main_script = f.read()

with open("./run0edit-inner.sh", "r", encoding="utf-8") as f:
    inner_script = f.read()

PLACEHOLDER = "{{ SCRIPT }}"

assert "END_OF_INNER_SCRIPT" not in inner_script
assert PLACEHOLDER in main_script
main_script = main_script.replace(PLACEHOLDER, inner_script, 1)
assert PLACEHOLDER not in main_script

with open("./run0edit", "w", encoding="utf-8") as f:
    f.write(main_script)

os.chmod("./run0edit", 0o755)
print("run0edit script generated.")
