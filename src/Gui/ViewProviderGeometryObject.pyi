# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

from typing import List, Optional

from Base.Metadata import constmethod, no_args
from ViewProviderDocumentObject import ViewProviderDocumentObject

class ViewProviderGeometryObject(ViewProviderDocumentObject):
    """
    This is the ViewProvider geometry class

    Author: Werner Mayer (wmayer@users.sourceforge.net)
    Licence: LGPL
    """

    @staticmethod
    @no_args
    def getUserDefinedMaterial() -> object:
        """
        Get a material object with the user-defined colors.
        """
        ...

    def beginTemporaryAppearance(self) -> None:
        """
        Starts temporary changes of ShapeAppearance (DiffuseColor, ShapeColor), like the
        highlight of a tool that is restored afterwards: they are no appearance override.
        Each call needs a call of endTemporaryAppearance(), use try/finally.
        """
        ...

    def endTemporaryAppearance(self) -> None:
        """
        Ends temporary changes of ShapeAppearance started with beginTemporaryAppearance().
        """
        ...

    @constmethod
    def isLookFromMaterial(self, element: str = "", /) -> bool:
        """
        Whether the look comes from the physical material instead of an appearance override.

        element : str
            A face name like 'Face1' for the look of that face. Empty for the whole object:
            then the look comes from the material only if nothing overrides it.
        """
        ...

    def resetToMaterial(self, faces: Optional[List[str]] = None, /) -> None:
        """
        Clears appearance overrides so that the look comes from the physical material again.

        faces : list of str
            Face names like 'Face1' whose override is cleared. If omitted, all overrides of
            the object and of its faces are cleared.
        """
        ...
