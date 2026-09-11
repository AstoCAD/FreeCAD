# Gordon surface

Choose **Gordon Surface**, select the first family of curves and use **Add
selected** under Profiles; repeat for Guides. Whole curve objects, individual
edges, and compounds of separate curves are accepted. Each edge is a network
curve. Use **Update preview**, then accept the task.

Every profile must intersect every guide once within the specified absolute
tolerance. Each family needs at least two curves. Input order and orientation
are resolved automatically. The surface covers the region between the outermost
crossings; portions of curves outside that region are trimmed. Closed curves and
networks with multiple crossings per pair must first be split into open patches.

The builder uses the Gordon sum of two interpolated curve skins minus their
intersection grid. Monotone reparameterization aligns crossings. A shared tensor
B-spline fit is refined and checked between nodes against both the Gordon sum
and the original network. Tolerance is an absolute distance in model units;
ApproximationError reports the largest sampled error (not a rigorous global
error bound). Failure to meet tolerance at MaxSamples produces a feature error.

Run `TestSurfaceGordonSurface` for geometry and GUI regressions.
