# SPDX-License-Identifier: LGPL-2.1-or-later

"""Compatibility facade for the BIM Stair Designer geometry API."""

from dataclasses import replace

from .geometry_core import (
    BLONDEL_MINIMUM,
    BLONDEL_MAXIMUM,
    StraightStairMetrics,
    BalancedSection,
    _CircularProfile,
    straight_stair_metrics,
    flight_stair_metrics,
    _distributed_dimensions,
    tread_goings,
    tread_stations,
    riser_heights,
    riser_stations,
    distribute_treads,
    _cross,
    _dot,
    _shifted,
    _translated_section,
    balanced_section_top,
    assign_section_elevations,
)

from .geometry_winders import (
    balanced_winder_sections,
    _winding_controls,
    _herse_curve_point,
    _herse_corner_trims,
    _endpoint_side,
    _endpoint_balance_trim,
    _fit_transition_trims,
    _safe_angle_tangent,
    _append_endpoint_transition,
    _apply_endpoint_boundary_sections,
    _section_is_locked_to_flight,
    _landing_winder_sections,
    _dense_path_length,
    _tangent_matches_direction,
    _sample_dense_path,
    _fit_sections_to_flight_footprint,
    _line_rectangle_interval,
    _flight_corner_extensions,
)

from .geometry_tangent import (
    tangent_flight_sections,
    _tangent_path_primitives,
    _primitive_point,
    _primitive_tangent,
    _append_primitive_range,
    _append_dense_point,
    _tangent_junction_modes,
)

from .geometry_plan import (
    make_tangent_stair_footprint,
    tangent_tread_faces,
    _straight_primitive_face,
    _circular_primitive_face,
    _fuse_plan_faces,
    fit_tangent_sections_to_footprint,
    make_stair_footprint,
    _line_intersection,
    fit_balanced_sections_to_footprint,
    _clip_chord_to_boundary,
    _point_in_boundary,
    balanced_tread_faces,
    _tangent_tread_faces,
    balanced_partition_is_valid,
    _boundary_data,
    _boundary_candidates,
    _unwrap_boundary_parameters,
    _monotone_boundary_parameters,
    _isotonic_increasing,
    _boundary_point,
    _boundary_vertices_between,
    _without_duplicate_points,
    _horizontal_face,
    _balanced_step_faces,
    _half_plane_face,
)

from .geometry_steps import (
    make_balanced_tread_shape,
    _local_step_expansion_faces,
    _continued_section_endpoint,
    _section_band_faces,
    make_balanced_riser_shape,
    make_balanced_concrete_shape,
    _align_straight_concrete_bottoms,
    _make_profiled_plan_solid,
    _make_helical_profiled_plan_solid,
    _circular_profile_data,
    _circular_profiles_join,
    _make_circular_concrete_span,
    _triangle_face,
    _make_triangulated_solid,
    balanced_plan_segments,
    balanced_plan_geometry,
)

from .geometry_helical import (
    _make_helical_annular_solid,
    _circular_profile_between,
    _annular_sector_face,
    _helical_profile_edge,
    _make_helical_band_solid,
    _make_sectioned_helical_band_solid,
)

from .geometry_stringer_path import (
    straight_stringer_sections,
    _stringer_inward,
    _stringer_cross_section,
    _monotone_profile_slopes,
    _profile_bezier_edges,
    _make_planar_housed_stringer_shape,
    _stringer_elevations,
    _stringer_slope,
    automatic_stringer_width,
    stringer_flight_runs,
    planar_stringer_sections,
    _stringer_section_runs,
    _circular_stringer_data,
)

from .geometry_stringer_shapes import (
    make_housed_stringer_shape,
    _make_housed_stringer_run,
    make_notched_stringer_shape,
    _make_circular_notched_stringer_shape,
    _planar_notched_stringer_shape,
    _make_notched_stringer_run,
)

from .geometry_handrails import (
    make_handrail_path,
    sample_handrail_path,
    handrail_picket_fractions,
    make_handrail_top_rail_shape,
    make_handrail_vertical_member_shape,
)

from .geometry_straight import (
    make_tread_shape,
    make_riser_shape,
    make_concrete_shape,
    default_concrete_thickness,
    plan_segments,
)
