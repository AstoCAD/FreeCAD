# SPDX-License-Identifier: LGPL-2.1-or-later

"""Compatibility facade for the BIM Stair Designer object API."""

from .object_stair_base import QT_TRANSLATE_NOOP, translate

from .object_utils import (
    _add_property,
    _quantity_value,
    _first_flight,
    get_flights,
    _is_circular_flight,
    _is_landing_flight,
    _has_endpoint_angle,
    _flight_length,
    _flight_path_dimension,
    linked_flight_side_lengths,
    linked_flight_side_lengths_for_difference,
    straight_turn_side_difference,
    flight_side_length_difference,
    linked_circular_radii,
    sync_circular_radii,
    sync_flight_side_lengths,
    sync_all_flight_side_lengths,
    _uses_native_container_placement,
    _child_placement,
    _combined_placement,
)

from .object_components import (
    _make_component_group,
    _set_generated_properties,
    _set_tread_properties,
    _tread_extra_widths,
    _tread_extra_heights,
    _generated_parts,
    _resize_generated_parts,
)

from .object_stringers import (
    _stringer_run_plane,
    _layout_stringer_run_plane,
    _line_intersection,
    _stringer_center_line,
    _shift_line_point,
    _planar_stringer_runs,
    _stringer_parts_for_flights,
    _set_stringer_part_properties,
)

from .object_handrails import (
    _sync_handrail_parts,
)

from .object_stair import (
    StairProxy,
)

from .object_proxies import (
    FlightProxy,
    ComponentGroupProxy,
    ViewProviderStair,
    ViewProviderComponentGroup,
)

from .object_factory import (
    _make_flight,
    resize_flights,
    make_stair,
)
