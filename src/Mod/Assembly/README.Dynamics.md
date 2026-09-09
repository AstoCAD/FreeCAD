# Assembly dynamics backend

This is a headless extension of the integrated Assembly workbench, using the
single bundled OndselSolver. It does not load FreeCADMbD or MBDyn. The existing
joint-editing workflow is unchanged. The Simulation task panel has Settings,
Motions, Loads, Initial, Contacts, Friction and Results tabs. The Settings tab's
Analysis selector offers **Automatic**, **Kinematics** and **Dynamics**.
Automatic preserves existing GUI studies: physical inputs select dynamics,
while motion-only studies use kinematics without requiring material density.
Choose Dynamics explicitly for motion-only actuator sizing; moving components
then require density and inertia, and motor reactions appear under Joint reactions.
Kinematics requires gravity to be disabled and loads, initial velocities,
contacts and friction to be suppressed. Incompatible active inputs produce an
error instead of being ignored. Analysis selection is saved with the study,
and changing it invalidates results. New headless `Dynamics.create_study()`
objects default to Dynamics, preserving their existing behavior.

## Materials and mass properties

`assembly.getMassProperties(component)` uses the existing `ShapeMaterial`
physical material and its `Density` property. OpenCASCADE supplies volume,
centre of mass and the full inertia tensor about the centre of mass. Material
values are not copied into a second editable density database.

- A solid `Part::Feature`, a PartDesign Body's final shape, or a link occurrence
  is supported. Feature history is not counted as additional material.
- An `App::Part` is one consolidated component, including when linked. Its
  physical children supply their own materials; nested Parts are aggregated with
  their transforms and the parallel-axis contributions. Organizational folders
  and non-solid construction geometry contribute no mass. Visibility does not
  disable a physical component; suppression does.
- Mass properties are expressed in the occurrence's local frame, including link
  shape scaling but excluding the occurrence's placement.
- Rigid groups combine member masses and rotated inertia tensors, including
  the parallel-axis contributions. Grounded members do not require mass data.
- Missing, dimensionally invalid or nonpositive density is an error. New parts
  may already have FreeCAD's default material: the UI displays the
  actual material/density for review, not just an "assigned" indicator.
- **Materials persistence remains library-based.** `ShapeMaterial` saves a UUID,
  not arbitrary unsaved edits to a `Materials.Material()` instance. Save custom
  materials through Materials before relying on reopening/rerunning a document.
  Result snapshots retain the numerical density, mass and inertia actually used,
  along with the material name and UUID. They are not a material library.

Each returned mass record has `Mass`, `Volume`, `Density`, `Material`,
`MaterialUUID`, `CenterOfMass`, `Inertia` (a row-major 3-by-3 tensor) and
`IsAggregate`. Containers have no single material/UUID; their Density is the
mass/volume-weighted mean, not an assignable material. `assembly.getComponents()`
returns the same consolidated, unsuppressed occurrences used by the solver.

The existing core **Mass Properties** command remains the material UI; Assembly
does not duplicate it. Its Physical Properties panel includes a reusable
Material selector. For a mixed selection the button lists up to two material
names followed by an ellipsis, and one selection assigns the chosen physical
material to every writable selected object in undoable document transactions.
Selecting an `App::Link` edits its source material because links have no physical
material override. Assembly links therefore continue to share the source's
material while retaining occurrence-specific placement and scale for mass
calculation.

## Headless API

Run in a FreeCAD Python environment with Assembly available:

```python
import FreeCAD as App
import Dynamics

# assembly and component are existing document objects. Assign the component's
# physical material through Materials and recompute/assemble the geometry first.
mass = assembly.getMassProperties(component)
study = Dynamics.create_study(assembly)
study.EndTime = "1 s"
study.OutputStep = "0.02 s"
study.GravityEnabled = True
study.GravityMagnitude = "9.81 m/s^2"

# Optional constant load at the component's centre of mass.
load = Dynamics.create_load(study, "Force", component)
load.Force = "1 N"
load.Direction = App.Vector(0, 0, 1)
load.AttachmentI.Base = App.Vector(*mass["CenterOfMass"])
# Optional time law. Force formulas are in N, torque formulas in N mm, and
# expose `time` in seconds. A nonempty formula supersedes the constant magnitude.
load.Formula = "1 + 0.5*sin(2*pi*time)"
# Optional: rotate the direction with the component (also supported for torque).
load.Follower = True

data = Dynamics.run(study)
saved_data = Dynamics.results(study)
```

Study, motion, load, initial-velocity, contact and friction objects are persistent
`App::FeaturePython` objects. A study references motion objects
using the current `Joint`, `MotionType` and `Formula` schema. The study's owning
Assembly backlink is hidden from the dependency graph to avoid a cycle.
Inputs directly inside the Assembly's SimulationGroup are global and apply to
every study; inputs nested in a study are local to that study. Dragging an input
between either level changes its scope.

The low-level `assembly.generateDynamics(study)` returns the sampled dictionary
and raises on failure. `Dynamics.run` also manages status/error properties and
saves a versioned JSON result snapshot in the document. A failed run clears that
study's old result rather than presenting it as a new successful result.

`run` does **not** recompute or move CAD components. Recompute/assemble geometry
before running: an Assembly recompute can itself invoke the kinematic solver.
Initial-condition assembly happens in the solver copy. The prior in-memory
simulation remains available if a new dynamics run fails.

### Frames, units and loads

The reference frame is the containing **Assembly**, not the document world frame
when the Assembly itself has a nonidentity placement. Directions are constant in
that reference frame, not follower loads. Attachment placements are body-local;
an empty `BodyJ` means ground and makes `AttachmentJ` assembly-relative.

| Quantity | API/result unit |
| --- | --- |
| Position, volume | mm, mm³ |
| Mass, density | kg, kg/mm³ |
| Inertia about COM | kg mm² |
| Time, linear velocity/acceleration | s, mm/s, mm/s² |
| Angular velocity/acceleration | rad/s, rad/s² |
| Reaction force/torque | N, N mm |
| Energy/work, power | mJ, mW |

Quantity inputs accept FreeCAD unit strings; torque uses e.g. `"1 N*mm"`.
Spring stiffness uses `"1 N/mm"`, viscous damping `"1 kg/s"`, and rest length mm.
Torsional stiffness and damping use `"N*mm/rad"` and `"N*mm*s/rad"`;
the free angle accepts any FreeCAD angle unit and is transferred to the solver in radians.
Dynamic quantity-property units are restored explicitly when reopening a study.

`Force` and `Torque` act on BodyI. They may be constant or use a symbolic
time-dependent magnitude expression. BodyJ receives the balancing wrench, including
the transported couple for separated attachments. An axial `SpringDamper` acts
along its two attachment points; coincident endpoints are rejected. This is an
ideal, bilateral linear spring, not contact or a tension-only element.
A `TorsionalSpringDamper` uses the two attachment frames' X/Y orientation to
measure signed relative twist. For aligned attachment axes its torque is along
attachment I's Z axis. With swing, torque follows the gradient of that twist and
damping uses its time derivative, preserving virtual work and elastic energy. Its
equal and opposite couples act on the selected component and reaction component,
or on assembly ground when no reaction component is selected.
The initial twist uses the equivalent angle nearest `FreeAngle`; subsequent
accepted integration steps track continuous winding through multiple turns.
Residual evaluations and output interpolation do not change that history.
An initial placement alone cannot encode extra complete turns of spring preload.

A `Bushing` is a six-degree-of-freedom compliant connection between two coincident
attachment frames. Three independent translational stiffness/damping pairs and
three independent rotational pairs act along/about attachment I's local X, Y and
Z axes. **Use current pose as free pose** aligns attachment J with attachment I;
that coincident and aligned configuration applies no force or torque. The optional
**Coupled 6×6 matrices** editor replaces the diagonal law with full stiffness and
damping matrices. Edit the upper triangle; lower entries are mirrored. Rows are
`Fx,Fy,Fz,Mx,My,Mz`, columns are `x,y,z,rx,ry,rz`. Entries use N and N mm for
efforts, mm and radians for strains, and seconds for damping; each cell's tooltip
shows its units. Both matrices must be finite, symmetric and positive semidefinite.
The backend rejects invalid matrices, including ones with positive diagonals but
negative eigenvalues. Matrices are saved as row-major 36-entry FloatList properties.
Elastic energy is `qᵀKq/2` and dissipated power is `qdotᵀCqdot`. Keep the
maximum integration step small relative to the bushing's shortest natural period.
The rotational strain is the principal rotation vector (below a half turn).
Its logarithm Jacobian maps strain forces and damping back to physical torque.
Translational strain rates include rotation of attachment I, and the wrench
includes the corresponding transport moment, preserving elastic virtual work.

### Joint friction

Revolute and slider joints can apply friction along their free axis during dynamic
simulation. A dedicated friction object exposes static and dynamic resisting torque or force,
a transition velocity, and optional viscous damping. The dry-friction direction is
regularized through zero velocity, avoiding a discontinuous sign change; a smaller
transition velocity more closely approximates Coulomb friction but can require
smaller integration steps. **Specified resistance** uses the entered force or torque
directly. **Reaction based** instead multiplies the joint reaction perpendicular to
the free axis by static/dynamic coefficients. Revolute bearings additionally
multiply by an effective bearing radius to obtain friction torque. **Rolling
resistance** uses the same radial-load law with an effective rolling coefficient;
it does not model individual rolling elements. **Thrust bearing** uses the absolute
axial joint reaction instead. Both are restricted to revolute joints. Use measured
or manufacturer bearing coefficients and the corresponding effective radius.
Seal drag and preload are not inferred; model those through specified resistance or
an additional load when needed.

### Contacts

The contact command can check one selected pair or every unordered component
pair in the Assembly. The all-pairs mode is intended only for very small
assemblies because both its broad phase and shape checks scale with the
number of pairs. When invoked
from the Simulation task it creates a child of that simulation; otherwise it
creates a global child of the SimulationGroup that participates in dragging and every simulation.
Both component fields accept normal components, links, `App::Part` containers,
and links to Parts.

Interactive dragging accepts any component containing solid BRep geometry,
including compound `App::Part` components and links. It uses bounding boxes as
a broad phase and OpenCASCADE's triangulated shape-proximity BVH as the
interactive narrow phase. Accuracy therefore follows the component's display
tessellation. An exact common-volume Boolean is retained only as a fallback for
shapes without usable triangulation. Contact time is refined before transferring
the remaining cursor translation to the contacted component. A grounded
contacted component instead stops the dragged component. The dragged object does
not physically rebound during kinematic dragging.

Forward dynamics uses an exact centre-distance model for sphere-sphere pairs.
Sphere-to-solid contact uses the closest BRep boundary witness. Other solid pairs
use cached surface quadrature, solid classification and distances to actual BRep
boundaries. Bounding boxes only reject separated pairs in forward dynamics.
Reference bounds are cached and transformed conservatively for broad-phase
rejection. Consecutive queries at exactly identical poses reuse their contact
points, including empty results; forces still use the current velocities.
No pose tolerance is used for this cache, so small solver perturbations are
evaluated and rejected integration steps cannot leave stale geometry behind.
The smaller surface supplies the quadrature; the other surface and clipped
intersection patches provide fallback witnesses. Pair stiffness and damping are
distributed over the active witness points using reference triangle areas while
local point velocities generate the moments that resist rocking and sliding.
This remains an approximate penalty model: finite surface sampling and changes
of active witnesses can affect force continuity and energy, especially for thin,
concave or highly tessellated shapes. It is not a qualified general-purpose
contact solver. Interactive drag response still uses a bounding-box escape
direction after geometric overlap detection. Dynamics uses a lagged tangent, so `MaximumStep` should be kept
small relative to impact duration. Optional regularized Coulomb friction opposes
each relative contact-point velocity. Separate static and dynamic
coefficients control sticking and sliding; the transition velocity smooths the
force near zero speed to keep the integrator stable. During kinematic dragging,
the same coefficients determine how much tangential cursor motion is transferred
to the contacted component, while the transition velocity is dynamics-only.

The two paths are selected automatically: dragging retains the cheaper
triangulated overlap test and approximate displacement response; simulation uses
surface witnesses for physical forces. In particular, nonconvex/curved witness
queries and clipped-intersection fallbacks can cost substantially more than a
drag overlap test. No additional contact accuracy selector is needed.

Large separated-endpoint drag moves additionally use conservative advancement
against BRep solids, including rotational surface travel. Simulation contact
loads validate converged trials before accepting history: potentially crossing
steps are retried at a smaller size. Sweeps interpolate rigid translation and
orientation; angular-travel guards prevent skipping complete revolutions. A
bounded iteration count treats unresolved grazing sweeps conservatively rather
than declaring them clear. Already-contacting pairs use a geometry-size-based
maximum surface increment so compliant penetration remains possible. This is
also limited by the contact's mass/stiffness timescale, so a small, stiff
projectile does not skip its much smaller elastic compression. This is
adaptive, tolerance-based contact handling, not an exact continuous trajectory
or rigid-impact solution. Very small/stiff bodies still require timestep and
tolerance convergence checks; lowering the minimum step alone is not sufficient.

Contact regression coverage includes rotated sphere/ramp and box/support force
directions, zero moment for symmetric face contact, a two-cube stack initialized
at its analytically calculated gravity equilibrium, and a falling cube settling
to `m*g/k` compression at two maximum time steps. Additional tests cover a fast
sphere crossing a thin wall between separated endpoint poses, a rotating bar,
analytical undamped impact velocity/travel for two projectile sizes,
and a concave passage that must remain open. A stack of hollow components tests
area-weighted manifold equilibrium; its unequal triangles must not produce a
spurious moment. Arbitrary concave stacks are not universally qualified by these
benchmarks.

### Results

Schema version 2 provides:

- `Times`: physical samples starting with the solved initial condition. The
  solver's unsolved input sample at the same start time is excluded.
- `Bodies`: keyed by component name. `Placements` are
  `[x, y, z, qx, qy, qz, qw]`; velocity and acceleration refer to the **component
  origin**, not its COM. Angular velocities/accelerations are also included.
  Rigid-group members have their own correctly transported origin trajectories.
- `MassProperties`: the local per-component material/mass snapshot.
- `JointReactions`: forces and moments on connector I, resolved in Assembly
  coordinates, keyed by solver joint/motion name. Moments are about connector I.
- `Loads`: the applied force/couple on attachment I, keyed by load object name.
- `Limits`: stored energy and dissipation for compliant joint stops.
- `Energy/System`: translational, rotational and total kinetic energy;
  gravitational potential and elastic stored energy; mechanical energy;
  external power/work; dissipated power/energy; and an energy-balance residual.
  Body records also contain their individual kinetic, potential and mechanical
  energies. Loads expose power, stored energy, dissipation and accumulated work;
  joint reactions and prescribed motions expose power and work.
- `SolverFrames`: indices for the current in-memory `assembly.updateForFrame`
  cache. These indices are not a persistent cache identifier: another solve/run
  replaces that cache. Saved placements remain self-contained for later playback.
- `CoordinateSystem`, and `Units` added by `Dynamics.run`.

Saved results are **historical snapshots**. The task editors invalidate them when
an input changes; recomputing geometry alone does not rerun the study.

## Deliberate first-slice limits

Supported joint mappings are Fixed, Revolute, Slider, Cylindrical, Ball, Gears,
Belt, Rack-and-Pinion and Screw, plus existing rigid groups. Gear and belt
relations transmit angular motion by their pitch-radius ratio; rack-and-pinion
uses pitch radius, and screw uses lead per revolution. Angular drives use Revolute/Cylindrical joints;
linear drives use Slider/Cylindrical joints. Duplicate/incompatible drives and
incomplete active joints are rejected. Free bodies need no artificial joint or
grounding constraint. Linear and angular initial velocities are applied at the
component centre of mass. For rigid groups, the selected component's COM velocity
is converted to the aggregate COM velocity, including the angular-velocity offset.
When only angular velocity is specified, that selected component's COM starts at
rest. When linear and angular inputs select different members of one rigid group,
the linear input determines the COM at which translation is specified.
Revolute/slider limits support rigid and independently
configured compliant min/max stops in dynamics.
Hard stops have perfectly inelastic impact and release when their reaction would
become tensile, including when a later load reversal pulls the component away.

Nested Assembly subassemblies, other joint types, detailed rolling-element bearings,
flexible/FEM bodies, and asynchronous cancellation
are not implemented in this Assembly slice. Unsupported model structures are
reported explicitly, rather than silently simulated with missing constraints.

## Verification

The separate mass-properties increment passes 45 headless tests across Mass
Properties, Dynamics and Assembly Core (3 GUI-only tests skipped), and 26
offscreen GUI tests across Mass Properties and Gravity, on Windows/MSVC Release.
Coverage includes 100 repeated links, material overrides, undo, nested Parts,
uniform/nonuniform scaling, link chains with both LinkTransform modes, folder
deduplication, toolbar registration, the Materials chooser, and aggregate dynamics.

The permanent suite is `AssemblyTests/TestDynamics.py`, also registered in
`TestAssemblyWorkbench`. From a configured FreeCAD Python runtime:

```python
import unittest
from AssemblyTests.TestDynamics import TestDynamics
unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestDynamics)
)
```

On Windows/MSVC Release, the full OndselSolver suite passes, including
the three backhoe drag regressions, compliant stops, dynamic shape contact and
cursor-driven sphere pushing. The Assembly contact tests cover global, local and
all-pairs scope, spherical and arbitrary-solid rebound, tangential friction,
multi-point rocking damping, simultaneous contacts, suppression/error handling,
and linked `App::Part` occurrences. The complete headless Assembly workbench
suite discovers 136 tests: 85 pass headlessly and 51 require the GUI.
The reviewed Release solver passes 70 tests, including 35 dynamics benchmarks.
New regressions cover inclined-plane force direction and magnitude, symmetric
contact moments, radian-based stop stiffness/damping, transformed Assembly load
frames, result invalidation, multi-turn torsion, and multi-axis bushing virtual work.
An offscreen GUI run with an isolated profile executes all 136 tests: 133 pass,
including all MbD tests; three view-editor/insert-link tests have incomplete mock
objects. No viewport rendering qualification is implied by that offscreen run.
Analysis-mode coverage includes a motion-only rotor with analytical actuator
torque and work, automatic dispatch, rejected incompatible kinematic inputs,
mode-change invalidation, legacy migration, and save/reopen persistence.

## Current UI and next gaps

The Settings tab contains gravity and integration controls. Motions, Loads,
Initial velocities, Contacts and Friction have consistent list/add/remove workflows
and open dedicated child tasks. Every type also has a toolbar command: invoking it
while editing a simulation creates a local input, while invoking it outside a
simulation creates a global input. Global entries appear in each simulation list
with a `(global)` suffix.
Force/torque loads reuse the attachment task box; linear spring-dampers add a
second component/ground endpoint, stiffness, viscous damping and free length.
Torsional spring-dampers use the same editor with angular stiffness, angular
damping and free angle, and reuse the curved torque/axis visualization. Their
viewport visuals follow the attachments during animation. The Results tab
exposes body position/velocity/acceleration, angular motion, joint/load reactions,
energy, work and power as a table, FreeCAD Plot graph, or CSV export.

SolidWorks Motion parity is not established. Remaining workflows include
cycle-angle/result-driven motor profiles, curve contacts
and advanced event-driven motion,
motion-load transfer to stress analysis, nested assemblies, full bearing friction,
and cancellable background integration. Flexible bodies and detailed bearing
models need an agreed edition/version scope.

## Latest validation increment

The contact-step, coupled-matrix, effective bearing-friction and follower-load
changes add independent solver oscillator/passivity/serialization tests and
Assembly tests for cross-coupled force/torque, finite-rotation virtual work,
damping power, radial versus axial reaction selection, and constant/formula
follower directions. GUI coverage includes matrix mirroring, follower selection
and cancellation. Release builds are used throughout. These checks are not a
claim of SolidWorks/ANSYS parity or universal contact stability.

The final GUI run passes 150 Assembly tests, including repeated child-task
switching. A review fix invalidates Qt wrappers synchronously on native widget
destruction, preventing reused widget addresses from returning stale wrappers.
The headless suite passes 97 tests (GUI-only cases are skipped). The standalone solver passes 37 dynamics
and 35 legacy tests, including the backhoe drag regressions. Standalone C++
geometry tests cover translation, rotation, concave passages and departure from
touching contact. The separate `AssemblyObjectTest` fixture still needs its
Windows embedded-Python/material runtime initialization repaired; its results
are not counted as passing. Temporary attempts to change that fixture were not
retained.
The GUI test runner also emits caught `GUIApplication::notify` diagnostics seen
in pre-existing runs; passing assertions do not establish a clean diagnostic log.

## Point measurements and trajectories

After generation, Results > Point measurement creates a saved measurement child.
Select one viewport vertex, datum point or coordinate-system origin, then press
the Point selection button. References preserve the component occurrence: a
source and each link to it are independent measurement targets. App::Part
descendants and scaled-link vertices are resolved in occurrence-local space.
The reference frame can be the assembly, another component, or a component's
coordinate system. Position, velocity and acceleration include rigid-point
offsets and moving-frame angular acceleration, centripetal and Coriolis terms.

The task includes a numerical table, plot/CSV export, forward/backward playback
and stepping. A trajectory and current-point marker are visible by default while
the task is open. For moving-frame measurements the path is carried by the
reference frame at the displayed time. Closing the task removes the temporary
overlay and restores component placements. Reopen saved measurements from the
Results list or by double-clicking their tree objects. All processing and playback
use saved samples, including after document reopen; no solver run is necessary.
Changing simulation inputs still requires regeneration. Trajectory-to-Part-curve
export is not included.

Ten point-measurement regressions cover analytical point/frame derivatives,
occurrence and scaled/nested references, datums, persistence, result preservation,
and the create/edit/cancel/playback task lifecycle. The complete GUI Assembly
suite passes 160 tests with this increment.

## Time-based motor and load profiles

Motion and force/torque tasks share a Profile field and resizable modal editor.
Constant, Segments, Data points and Expression definitions have a live input
preview. Motions can prescribe position, velocity or acceleration, with explicit
initial position/velocity for integrated profiles. Loads prescribe signed force
or torque magnitude; attachment and follower settings remain independent.

Segments use durations and endpoint values with Hold, Linear or quintic Smooth
transitions. Hold values follow the preceding endpoint. Data can be entered,
pasted or imported from CSV with column/unit selection, using linear or natural
cubic interpolation. Time is in seconds; supported base units are mm/m, rad/deg,
N and N mm/N m. Changing display units converts the definition. Previews expose
position, velocity, acceleration and jerk separately, with time/value readout.

The restricted expression editor supports t/time, pi, initialValue, arithmetic,
constant powers, sin, cos and exp. It never evaluates Python code. In the editor,
initialValue is the explicit initial-position field (seeded from the joint), not
a dynamically substituted joint value. Existing legacy formulas remain unchanged
until the profile editor is accepted. Expressions used as velocity/acceleration
must have a supported analytic antiderivative (polynomials and affine-argument
sin/cos/exp); other expressions report a validation error, rather than silently
approximating their integral. Segments and data profiles integrate analytically.

Outside-range choices are Hold endpoint, Repeat and Require coverage. Holding
velocity continues travel; repetition repeats the prescribed quantity and does
not reset accumulated displacement from an integrated velocity. Repeat expansion
is bounded to 2000 intervals per run. Spline overshoot and discontinuous joins
are warned about; forward-dynamics accuracy near joins still depends on solver
settings. A profile edit invalidates results and requires regeneration, while
previewing does not run the solver. Profiles are saved with their motion/load,
not as separate document objects. Nested-dialog Cancel never writes the profile,
and the enclosing task transaction supports cancelling accepted profile edits.

## Contact groups

The existing Contact tool supports four modes: a single component pair, general
assembly collision detection, **Between component sets**, and **Within a
component set**. Between sets generates A×B pairs; within a set generates each
unordered member pair once. Self-pairs and duplicates are ignored, including
overlapping sets. These sets do not create rigid groups or move components in
the document hierarchy. App::Part components stay consolidated, and links are
selected as distinct occurrences rather than being replaced by their sources.

The contact task has a filterable membership table and buttons to add the current
tree/3D selection to either set. Existing stiffness, damping and friction settings
apply to every generated pair. An expandable exclusion editor removes selected
pairs from this definition; collapsing it does not disable the exclusions. Its
candidate-pair count reflects exclusions and deduplication, but fixed bundles
and rigid groups may reduce the actual solver count further. General detection
retains its small-assembly performance warning.

Exclusions are local to their definition, not assembly-wide vetoes. If active
contact mode is Between two components, exclusions are neither shown nor applied;
their settings are retained for switching back to a multi-pair mode. If active
contact definitions overlap, the first definition in the input order supplies
the response for that pair; forces are never added twice. Global contacts precede
local contacts. For a different local response, suppress or exclude the global
definition's pair rather than relying on a local override. Deleting an excluded
endpoint removes its exclusion; reusing its object name does not resurrect it.

Global contact sets participate in dragging and all simulations. Sets created
while editing a simulation are local to it, just like existing pair contacts.
Native drag activation, drag response and forward dynamics share one pair
expansion implementation. No collision geometry algorithm or solver law changes
are introduced by this feature.

Quick check: create three components A, B and C. Choose Within a component set
and tick A and B. Drag A into B: B should be pushed; C should not participate.
Exclude A–B: neither should push the other through that definition. For a second
check, choose Between component sets, put A in set A and B/C in set B; the task
should report two candidate pairs, with no B–C contact.

Nine Python regressions cover pair expansion, overlap deduplication and force
magnitude, general exclusions, invalid membership, occurrence identity,
save/reopen, deletion/name reuse, global/local scope, result invalidation and UI
editing. The complete GUI Assembly suite passes 197 tests. A native drag
activation/pushing regression is included; its standalone fixture currently
fails before the test body because its embedded Python cannot import Assembly.

## Event-driven dynamics

The simulation task has an **Events** tab. Add opens a dedicated event task;
accept/cancel returns to the simulation. Double-click a saved event to edit it.
Events are simulation-local children. Their actions can target local or global
motions and loads, but modify only native run state, never the target document's
suppression, material, or profile definition. Events require Dynamics; Automatic
selects it when an unsuppressed event is present.

Triggers currently include absolute time, a rising/falling position, distance or
speed threshold, and a delay after another event. Measurement coordinates are
relative to the assembly or a selected reference component. Select the actual
component occurrence (including App::Part and links). The optional point picker
captures the selected vertex/datum/coordinate-system origin in that occurrence's
local coordinates; otherwise it measures the component origin. The captured
point is not an associative topological reference. Position and distance use mm;
speed uses mm/s. Repeat, hysteresis and initially-satisfied handling are explicit.

Actions are ordered rows: Activate, Deactivate, Start profile, or Ramp. A motor
deactivation **releases** its constraint and retains physical momentum. Activation
resumes its profile clock, rebased to its actual position; imposed velocity may
change instantaneously. Start profile restarts the saved profile clock and also
preserves motor position, but may impose a different velocity. Ramp is the smooth
alternative: a quintic velocity transition for motors (mm/s or rad/s), or magnitude
transition for forces/torques (N or N mm), followed by holding the final value.
Position is integrated analytically for a velocity ramp. Springs and bushings can
be activated/deactivated but cannot use magnitude-profile actions.

The scheduler locates crossings within converged integration steps, outputs the
exact event boundary, applies actions, projects the changed constraints and
restarts integration with fresh equation numbering. Velocity jumps caused by
actions are checked for further threshold events before time advances. Dependency
cycles are rejected; cascades and repeated firings have a 10,000-firing safety
limit. Simultaneous events run in study order and action rows in row order; avoid
conflicting actions on the same target at the same time. Firing times appear in
the Events list and as dashed markers on result plots. Clicking a fired event
seeks its first firing in the player. Regeneration is required after editing an
event.
Delayed actions retain their pending firing time when a predecessor repeats.
A one-shot dependent uses its first predecessor occurrence; a repeating dependent
queues each occurrence. Activate also prepares a suppressed input's repeating
profile over the simulation interval. Temporary compiled formulas are restored
after success or failure, so running a study does not overwrite shared profiles.

### Review regression coverage (September 2026)

The Release suites pass 207 Assembly tests and 78 standalone solver tests. Added
coverage includes regeneration with point measurements, event-activated repeats,
queued delays, hard-stop release on both sides of slider/revolute joints and after
load reversal, non-coaxial torsional virtual work/damping and independent Jacobians,
contact exclusion copy/deletion/undo, and native contact double-click before and
after reopening a document. Exclusions now use reference-aware per-pair properties
instead of endpoint names, so copying/importing remaps the endpoints correctly.

Current scope: revolute and slider motor actions, not coupled cylindrical
motions. Thresholds cover point position/distance/speed, not joint-angle,
reaction-force, contact-onset, or arbitrary Boolean conditions. Crossing search
uses eight probe intervals per accepted step; rapidly oscillating measurements
still require an appropriate maximum step size. General contact continues to use
its existing collision refinement independently. No PLC/control-loop language or
event graph editor is introduced.

Quick manual check:

1. Ground one component and connect a moving component with a Z slider. Give the
   moving component a material with density; leave joint limits disabled.
2. Create a one-second simulation, gravity off, and a linear prescribed motion
   `initialValue + 100*time` (100 mm/s).
3. In Events, add a Time event at **0.2 s**. Add a **Ramp** action targeting that
   motion, value **0 mm/s**, duration **0.1 s**.
4. Generate. The component travels 20 mm before the event, another 5 mm during
   deceleration, and then holds at **25 mm** relative to its initial position.
   The event list should report 0.2 s. Changing Ramp to Deactivate instead should
   let the component coast, not stop it.

Validation includes timed force impulse/displacement, exact output boundaries,
suppressed-input activation, delayed/zero-delay cascades, threshold location and
repeat hysteresis, motion release, linear/angular smooth stops, profile restart,
velocity-jump triggering, and preservation of global input definitions. A solver
startup regression also checks a smooth force ramp from rest: first-step growth
must not oscillate between rejected large steps and converged small steps.

The profile increment adds 13 regressions, including solver/preview agreement
for all three motion quantities in kinematics and dynamics, force/impulse tests,
derivatives, integrals, spline joins, units, persistence, repetition and UI undo.
The complete Release GUI Assembly suite passes 173 tests. No additional solver
implementation or dependency is required; profiles compile to existing native
piecewise functions.
