#!/usr/bin/env python3
"""Write automation spec to pending_auto_spec.json (avoids 255-char input_text limit)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *

if len(sys.argv) < 2:
    print("ERROR: spec argument required.")
    sys.exit(1)

spec = " ".join(sys.argv[1:])
os.makedirs(os.path.dirname(PENDING_SPEC_PATH), exist_ok=True)
with open(PENDING_SPEC_PATH, 'w') as f:
    f.write(spec)
print("OK")
