from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import exp, hypot

from meridian.context import Context, LENS_RADIUS_MIN, Mode, band_bias, mode_bias
from meridian.library import Track
