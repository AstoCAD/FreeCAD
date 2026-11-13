# SPDX-License-Identifier: LGPL-2.1-or-later

from Base.Metadata import constmethod, export
from GeoFeature import GeoFeature


@export(Include="App/Datums.h", )
class LocalCoordinateSystem(GeoFeature):
    """
    App.LocalCoordinateSystem class.

    A coordinate system made of an origin point, three axes and three base planes.
    It is also the base class of the origin of a Part or a Body.
    """

    @constmethod
    def getOrigin(self) -> GeoFeature:
        """
        Returns the origin point of the coordinate system.
        """

    @constmethod
    def getX(self) -> GeoFeature:
        """
        Returns the X axis of the coordinate system.
        """

    @constmethod
    def getY(self) -> GeoFeature:
        """
        Returns the Y axis of the coordinate system.
        """

    @constmethod
    def getZ(self) -> GeoFeature:
        """
        Returns the Z axis of the coordinate system.
        """

    @constmethod
    def getXY(self) -> GeoFeature:
        """
        Returns the XY plane of the coordinate system.
        """

    @constmethod
    def getXZ(self) -> GeoFeature:
        """
        Returns the XZ plane of the coordinate system.
        """

    @constmethod
    def getYZ(self) -> GeoFeature:
        """
        Returns the YZ plane of the coordinate system.
        """
