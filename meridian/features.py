from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from mutagen import File as MutagenFile
from mutagen.id3 import ID3NoHeaderError

# PLACEHOLDER_TOO_SHORT_WILL_FAIL_ASSERT