# SPDX-License-Identifier: LGPL-2.1-or-later

"""Exits with non-zero return code if the VTK Python package
at FREECAD_FEM_VTK_PYTHON_PATH is not compatible with the loaded VTK library

Meant to be run in a subprocess by vtk_module_handling.vtk_module_compatible.
FreeCAD runs a .py file given on the command line as a module named after the
file, not as "__main__", so the check is gated on an environment variable set
by the caller. Importing this module anywhere else (e.g. by the FEM test that
imports all modules) must not terminate FreeCAD."""

import os
import sys

import Fem

if os.environ.get("FREECAD_FEM_VTK_PYTHON_PATH") is not None:
    try:
        folder = os.environ.get("FREECAD_FEM_VTK_PYTHON_PATH")
        if folder:
            sys.path = [folder]

        from vtkmodules.vtkCommonCore import vtkBitArray, vtkVersion

        compatible = Fem.getVtkVersion() == vtkVersion.GetVTKVersion()
        compatible = compatible and Fem.isVtkCompatible(vtkBitArray())
    except Exception:
        compatible = False

    os._exit(0 if compatible else 1)
