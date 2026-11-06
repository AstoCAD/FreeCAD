/***************************************************************************
 *   Copyright (c) 2006 Werner Mayer <wmayer[at]users.sourceforge.net>     *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/


#pragma once

#include "ViewProviderDragger.h"
#include <Inventor/lists/SoPickedPointList.h>

class SoPickedPointList;
class SoPickStyle;
class SoSwitch;
class SoSensor;
class SbVec2s;
class SoBaseColor;
class SoNodeSensor;

namespace Gui
{

class SoFCSelection;
class SoFCBoundingBox;
class View3DInventorViewer;

/**
 * The base class for all view providers that display geometric data, like mesh, point clouds and
 * shapes.
 * @author Werner Mayer
 */
class GuiExport ViewProviderGeometryObject: public ViewProviderDragger
{
    PROPERTY_HEADER_WITH_OVERRIDE(Gui::ViewProviderGeometryObject);

    typedef ViewProviderDragger inherited;

public:
    /// constructor.
    ViewProviderGeometryObject();

    /// destructor.
    ~ViewProviderGeometryObject() override;

    // Display properties
    App::PropertyPercent Transparency;
    App::PropertyMaterialList ShapeAppearance;  // May be different from material
    /// Elements whose look overrides the physical material (see App::AppearanceOverrides)
    App::PropertyStringList AppearanceOverrides;
    App::PropertyBool BoundingBox;
    App::PropertyBool Selectable;

    /**
     * Attaches the document object to this view provider.
     */
    void attach(App::DocumentObject* pcObject) override;
    void updateData(const App::Property*) override;
    void finishRestoring() override;

    /** @name Temporary appearance
     * Between begin and end, changes of 'ShapeAppearance' are temporary (the highlight of a tool,
     * restored afterwards): they neither record nor clear appearance overrides. Calls can nest.
     */
    //@{
    void beginTemporaryAppearance();
    void endTemporaryAppearance();

    /// Scoped temporary change of the appearance
    class TemporaryAppearance
    {
    public:
        explicit TemporaryAppearance(ViewProviderGeometryObject* viewProvider)
            : vp(viewProvider)
        {
            if (vp) {
                vp->beginTemporaryAppearance();
            }
        }
        ~TemporaryAppearance()
        {
            if (vp) {
                vp->endTemporaryAppearance();
            }
        }
        TemporaryAppearance(const TemporaryAppearance&) = delete;
        TemporaryAppearance& operator=(const TemporaryAppearance&) = delete;
        TemporaryAppearance(TemporaryAppearance&&) = delete;
        TemporaryAppearance& operator=(TemporaryAppearance&&) = delete;

    private:
        ViewProviderGeometryObject* vp;
    };
    //@}

    /** @name Look of the physical material
     * The look follows the appearance of the physical material ('ShapeMaterial' of the object)
     * unless it is overridden. Any change of 'ShapeAppearance' other than by the material is an
     * override, of the whole object or of single faces.
     */
    //@{
    /// Whether the object has a physical material that can give its look
    bool hasPhysicalMaterial() const;
    /// The look of the physical material
    App::Material getMaterialLook() const;
    /** Whether the look comes from the physical material: of the whole object if @a element is
     * empty, else of the face @a element ("Face1" ...).
     */
    bool isLookFromMaterial(const std::string& element = {}) const;
    /** Clears the overrides of @a faces ("Face1" ...), or all of them if @a faces is empty, so
     * that their look comes from the physical material again.
     */
    void resetToMaterial(const std::vector<std::string>& faces = {});
    //@}

    bool isSelectable() const override
    {
        return Selectable.getValue();
    }

    /**
     * Returns a list of picked points from the geometry under \a getRoot().
     * If \a pickAll is false (the default) only the intersection point closest to the camera will
     * be picked, otherwise all intersection points will be picked.
     */
    SoPickedPointList getPickedPoints(
        const SbVec2s& pos,
        const View3DInventorViewer& viewer,
        bool pickAll = false
    ) const;
    /**
     * This method is provided for convenience and does basically the same as getPickedPoints()
     * unless that only the closest point to the camera will be picked. \note It is in the response
     * of the client programmer to delete the returned SoPickedPoint object.
     */
    SoPickedPoint* getPickedPoint(const SbVec2s& pos, const View3DInventorViewer& viewer) const;

    /** @name Edit methods */
    //@{
    virtual void showBoundingBox(bool);
    //@}

    void hide() override;
    void show() override;

    /// Get the python wrapper for that ViewProvider
    PyObject* getPyObject() override;

protected:
    /// get called by the container whenever a property has been changed
    void onChanged(const App::Property* prop) override;
    void onBeforeChange(const App::Property* prop) override;
    void setSelectable(bool Selectable = true);

    virtual unsigned long getBoundColor() const;
    void updateBoundingBox();
    void addBoundSwitch();

    void handleChangedPropertyName(
        Base::XMLReader& reader,
        const char* TypeName,
        const char* PropName
    ) override;
    void setCoinAppearance(const App::Material& source);

private:
    bool isSelectionEnabled() const;
    bool isLoadingOrUndoing() const;
    void followMaterial();
    void setAppearanceFromMaterial(const std::vector<App::Material>& values);

protected:
    SoMaterial* pcShapeMaterial {nullptr};
    SoFCBoundingBox* pcBoundingBox {nullptr};
    SoSwitch* pcBoundSwitch {nullptr};
    SoBaseColor* pcBoundColor {nullptr};
    SoPickStyle* pickStyle {nullptr};
    SoNodeSensor* pcSwitchSensor {nullptr};

private:
    /// The look before anything was loaded, only used while a file is loaded
    App::Material initialAppearance;
    /// The appearance before its current change
    std::vector<App::Material> appearanceBefore;
    /// The material is changing the appearance: this is no override
    bool settingFromMaterial {false};
    /// Nesting depth of temporary appearance changes: they are no override
    int temporaryAppearance {0};
    /// The overrides were read from the file
    bool overridesRestored {false};
};

}  // namespace Gui
