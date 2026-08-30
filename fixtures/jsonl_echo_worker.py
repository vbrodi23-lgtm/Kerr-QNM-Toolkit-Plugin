#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


for index, line in enumerate(sys.stdin):
    value = json.loads(line)
    print(json.dumps({"index": index, "received": value}, separators=(",", ":")), flush=True)
