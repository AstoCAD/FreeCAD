# SPDX-License-Identifier: LGPL-2.1-or-later

"""Compatibility facade for Stair Designer task panels."""

from .geometry import BLONDEL_MAXIMUM, BLONDEL_MINIMUM
from .taskpanel import StairDesignerTaskPanel, translate

from .taskpanel_widgets import (
    _value,
    _length_spin,
    _float_spin,
    _percent_spin,
    _FlightTreeWidget,
)
