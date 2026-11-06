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


#include <algorithm>

#include <Inventor/SoPickedPoint.h>
#include <Inventor/actions/SoRayPickAction.h>
#include <Inventor/actions/SoSearchAction.h>
#include <Inventor/nodes/SoBaseColor.h>
#include <Inventor/nodes/SoCamera.h>
#include <Inventor/nodes/SoDirectionalLight.h>
#include <Inventor/nodes/SoDrawStyle.h>
#include <Inventor/nodes/SoFont.h>
#include <Inventor/nodes/SoMaterial.h>
#include <Inventor/nodes/SoPickStyle.h>
#include <Inventor/nodes/SoResetTransform.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>
#include <Inventor/sensors/SoNodeSensor.h>

#include <App/Document.h>
#include <App/GeoFeature.h>
#include <App/Material.h>
#include <App/PropertyGeo.h>

#include "Application.h"
#include "Document.h"
#include "Inventor/SoFCBoundingBox.h"
#include "SoFCSelection.h"
#include "View3DInventorViewer.h"
#include "ViewProviderGeometryObject.h"
#include "ViewProviderGeometryObjectPy.h"

#include <Base/Tools.h>

using namespace Gui;

PROPERTY_SOURCE(Gui::ViewProviderGeometryObject, Gui::ViewProviderDragger)

const App::PropertyIntegerConstraint::Constraints intPercent = {0, 100, 5};

ViewProviderGeometryObject::ViewProviderGeometryObject()
{
    App::Material mat = App::Material::getDefaultAppearance();

    long initialTransparency = Base::toPercent(mat.transparency);

    static const char* dogroup = "Display Options";
    static const char* sgroup = "Selection";
    static const char* osgroup = "Object Style";

    ADD_PROPERTY_TYPE(
        Transparency,
        (initialTransparency),
        osgroup,
        App::Prop_None,
        "Set object transparency"
    );
    Transparency.setConstraints(&intPercent);

    ADD_PROPERTY_TYPE(ShapeAppearance, (mat), osgroup, App::Prop_None, "Shape appearance");
    ADD_PROPERTY_TYPE(
        AppearanceOverrides,
        (),
        osgroup,
        App::Prop_Hidden,
        "Elements whose appearance overrides the look of the physical material"
    );
    ADD_PROPERTY_TYPE(BoundingBox, (false), dogroup, App::Prop_None, "Display object bounding box");
    ADD_PROPERTY_TYPE(
        Selectable,
        (true),
        sgroup,
        App::Prop_None,
        "Set if the object is selectable in the 3d view"
    );

    pickStyle = new SoPickStyle();
    pickStyle->ref();
    pickStyle->style.setValue(SoPickStyle::SHAPE);
    pcRoot->insertChild(pickStyle, 1);
    Selectable.setValue(isSelectionEnabled());

    pcShapeMaterial = new SoMaterial;
    setCoinAppearance(mat);
    pcShapeMaterial->ref();
    pcShapeMaterial->setName("ShapeMaterial");
    initialAppearance = mat;

    sPixmap = "Feature";
}

ViewProviderGeometryObject::~ViewProviderGeometryObject()
{
    if (pcShapeMaterial) {
        pcShapeMaterial->unref();
    }
    if (pcBoundingBox) {
        pcBoundingBox->unref();
    }
    if (pcBoundSwitch) {
        pcBoundSwitch->unref();
    }
    if (pcBoundColor) {
        pcBoundColor->unref();
    }
    delete pcSwitchSensor;
}

bool ViewProviderGeometryObject::isSelectionEnabled() const
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/View"
    );
    return hGrp->GetBool("EnableSelection", true);
}

void ViewProviderGeometryObject::onChanged(const App::Property* prop)
{
    // Actually, the properties 'ShapeColor' and 'Transparency' are part of the property
    // 'ShapeMaterial'. Both redundant properties are kept due to more convenience for the user. But
    // we must keep the values consistent of all these properties.
    std::string propName = prop->getName();
    if (prop == &Selectable) {
        bool Sel = Selectable.getValue();
        setSelectable(Sel);
    }
    else if (prop == &Transparency) {
        long value = Base::toPercent(ShapeAppearance.getTransparency());
        float trans = Base::fromPercent(Transparency.getValue());
        if (value != Transparency.getValue()) {
            ShapeAppearance.setTransparency(trans);
        }

        pcShapeMaterial->transparency = trans;
    }
    else if (prop == &ShapeAppearance) {
        if (getObject() && getObject()->testStatus(App::ObjectStatus::TouchOnColorChange)) {
            getObject()->touch(true);
        }
        long value = Base::toPercent(ShapeAppearance.getTransparency());
        if (value != Transparency.getValue()) {
            Transparency.setValue(value);
        }
        if (ShapeAppearance.getSize() == 1) {
            const App::Material& Mat = ShapeAppearance[0];
            setCoinAppearance(Mat);
        }
        // An appearance set by anything but the material overrides the material look. Loading
        // and undo restore the saved overrides together with the appearance.
        if (!appearanceBefore.empty() && !settingFromMaterial && temporaryAppearance == 0
            && !isLoadingOrUndoing() && hasPhysicalMaterial()) {
            auto names = App::AppearanceOverrides::afterChange(
                AppearanceOverrides.getValues(),
                appearanceBefore,
                ShapeAppearance.getValues(),
                getMaterialLook()
            );
            if (names != AppearanceOverrides.getValues()) {
                AppearanceOverrides.setValues(names);
            }
        }
        appearanceBefore.clear();
    }
    else if (prop == &AppearanceOverrides) {
        if (isRestoring()) {
            overridesRestored = true;
        }
    }
    else if (prop == &BoundingBox) {
        showBoundingBox(BoundingBox.getValue());
    }

    ViewProviderDragger::onChanged(prop);
}

void ViewProviderGeometryObject::attach(App::DocumentObject* pcObj)
{
    ViewProviderDragger::attach(pcObj);
}

void ViewProviderGeometryObject::updateData(const App::Property* prop)
{
    if (prop->isDerivedFrom<App::PropertyComplexGeoData>()) {
        updateBoundingBox();
    }
    else if (prop->getName() && std::string(prop->getName()) == "ShapeMaterial") {
        auto doc = getObject() ? getObject()->getDocument() : nullptr;
        if (!doc || doc->isPerformingTransaction()) {
            // Undo and redo restore the appearance together with the material
        }
        else if (isLoadingOrUndoing()) {
            /*
             * While a file is loaded the saved appearance and overrides are read after the
             * material. Until then show the material look on a still untouched appearance, as
             * files written without a GUI have no saved appearance.
             */
            App::Material defaultMaterial;
            auto material = getMaterialLook();
            App::Material strippedMaterial = material;
            strippedMaterial.uuid.clear();  // Prevent equal UUID from always meaning equal material
            if ((ShapeAppearance.getSize() == 1)
                && (ShapeAppearance[0] == defaultMaterial || ShapeAppearance[0] == initialAppearance)
                && (material != defaultMaterial) && (ShapeAppearance[0] != strippedMaterial)) {
                setAppearanceFromMaterial({material});
            }
        }
        else {
            followMaterial();
        }
    }

    ViewProviderDragger::updateData(prop);
}

void ViewProviderGeometryObject::onBeforeChange(const App::Property* prop)
{
    if (prop == &ShapeAppearance) {
        appearanceBefore = ShapeAppearance.getValues();
    }
    ViewProviderDragger::onBeforeChange(prop);
}

void ViewProviderGeometryObject::finishRestoring()
{
    // A file written before the overrides were saved, or by a version that does not know them
    if (!overridesRestored && hasPhysicalMaterial()) {
        auto names = App::AppearanceOverrides::guess(
            ShapeAppearance.getValues(),
            getMaterialLook(),
            App::Material::getDefaultAppearance()
        );
        if (names != AppearanceOverrides.getValues()) {
            AppearanceOverrides.setValues(names);
        }
    }
    overridesRestored = false;
    ViewProviderDragger::finishRestoring();
}

bool ViewProviderGeometryObject::isLoadingOrUndoing() const
{
    auto obj = getObject();
    auto doc = obj ? obj->getDocument() : nullptr;
    if (!doc || testStatus(Gui::isRestoring) || obj->isRestoring()) {
        return true;
    }
    return doc->testStatus(App::Document::Restoring) || doc->isPerformingTransaction();
}

void ViewProviderGeometryObject::beginTemporaryAppearance()
{
    ++temporaryAppearance;
}

void ViewProviderGeometryObject::endTemporaryAppearance()
{
    if (temporaryAppearance > 0) {
        --temporaryAppearance;
    }
}

bool ViewProviderGeometryObject::hasPhysicalMaterial() const
{
    auto obj = getObject();
    return obj && obj->getPropertyByName("ShapeMaterial");
}

App::Material ViewProviderGeometryObject::getMaterialLook() const
{
    if (auto geometry = getObject<App::GeoFeature>()) {
        return geometry->getMaterialAppearance();
    }
    return App::Material(App::Material::DEFAULT);
}

bool ViewProviderGeometryObject::isLookFromMaterial(const std::string& element) const
{
    const auto& names = AppearanceOverrides.getValues();
    auto has = [&names](const std::string& name) {
        return std::find(names.begin(), names.end(), name) != names.end();
    };
    if (element.empty()) {
        return names.empty();
    }
    return !has(App::AppearanceOverrides::objectName()) && !has(element);
}

void ViewProviderGeometryObject::resetToMaterial(const std::vector<std::string>& faces)
{
    std::vector<std::size_t> indices;
    for (const auto& name : faces) {
        int index = App::AppearanceOverrides::faceIndex(name);
        if (index >= 0) {
            indices.push_back(static_cast<std::size_t>(index));
        }
    }
    if (!faces.empty() && indices.empty()) {
        return;
    }

    App::Material look = getMaterialLook();
    if (!App::AppearanceOverrides::hasLook(look)) {
        look = App::Material::getDefaultAppearance();
    }
    auto names = AppearanceOverrides.getValues();
    auto values = ShapeAppearance.getValues();
    App::AppearanceOverrides::reset(names, values, look, indices);
    setAppearanceFromMaterial(values);
    if (names != AppearanceOverrides.getValues()) {
        AppearanceOverrides.setValues(names);
    }
}

void ViewProviderGeometryObject::followMaterial()
{
    std::vector<App::Material> values;
    if (App::AppearanceOverrides::followMaterial(
            AppearanceOverrides.getValues(),
            ShapeAppearance.getValues(),
            getMaterialLook(),
            values
        )) {
        setAppearanceFromMaterial(values);
    }
}

void ViewProviderGeometryObject::setAppearanceFromMaterial(const std::vector<App::Material>& values)
{
    Base::FlagToggler<> flag(settingFromMaterial, false);
    ShapeAppearance.setValues(values);
}

void ViewProviderGeometryObject::updateBoundingBox()
{
    if (pcBoundingBox) {
        Base::BoundBox3d box = this->getBoundingBox(nullptr, nullptr, false);
        if (!box.IsValid()) {
            return;
        }
        pcBoundingBox->minBounds.setValue(box.MinX, box.MinY, box.MinZ);
        pcBoundingBox->maxBounds.setValue(box.MaxX, box.MaxY, box.MaxZ);
    }
}

SoPickedPointList ViewProviderGeometryObject::getPickedPoints(
    const SbVec2s& pos,
    const View3DInventorViewer& viewer,
    bool pickAll
) const
{
    auto root = new SoSeparator;
    root->ref();
    root->addChild(viewer.getHeadlight());
    root->addChild(viewer.getSoRenderManager()->getCamera());
    root->addChild(getRoot());

    SoRayPickAction rp(viewer.getSoRenderManager()->getViewportRegion());
    rp.setPickAll(pickAll);
    rp.setRadius(viewer.getPickRadius());
    rp.setPoint(pos);
    rp.apply(root);
    root->unref();

    // returns a copy of the list
    return rp.getPickedPointList();
}

SoPickedPoint* ViewProviderGeometryObject::getPickedPoint(
    const SbVec2s& pos,
    const View3DInventorViewer& viewer
) const
{
    auto root = new SoSeparator;
    root->ref();
    root->addChild(viewer.getHeadlight());
    root->addChild(viewer.getSoRenderManager()->getCamera());
    root->addChild(getRoot());

    SoRayPickAction rp(viewer.getSoRenderManager()->getViewportRegion());
    rp.setPoint(pos);
    rp.setRadius(viewer.getPickRadius());
    rp.apply(root);
    root->unref();

    // returns a copy of the point
    SoPickedPoint* pick = rp.getPickedPoint();
    // return (pick ? pick->copy() : 0); // needs the same instance of CRT under MS Windows
    return (pick ? new SoPickedPoint(*pick) : nullptr);
}

unsigned long ViewProviderGeometryObject::getBoundColor() const
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/View"
    );
    // white (255,255,255)
    unsigned long bbcol = hGrp->GetUnsigned("BoundingBoxColor", 4294967295UL);
    return bbcol;
}

void ViewProviderGeometryObject::setCoinAppearance(const App::Material& source)
{
    pcShapeMaterial->ambientColor
        .setValue(source.ambientColor.r, source.ambientColor.g, source.ambientColor.b);
    pcShapeMaterial->diffuseColor
        .setValue(source.diffuseColor.r, source.diffuseColor.g, source.diffuseColor.b);
    pcShapeMaterial->specularColor
        .setValue(source.specularColor.r, source.specularColor.g, source.specularColor.b);
    pcShapeMaterial->emissiveColor
        .setValue(source.emissiveColor.r, source.emissiveColor.g, source.emissiveColor.b);
    pcShapeMaterial->shininess.setValue(source.shininess);
    pcShapeMaterial->transparency.setValue(source.transparency);
}

void ViewProviderGeometryObject::addBoundSwitch()
{
    if (!pcBoundSwitch) {
        return;
    }

    for (int i = 0; i < pcModeSwitch->getNumChildren(); ++i) {
        auto node = pcModeSwitch->getChild(i);
        if (!node->isOfType(SoGroup::getClassTypeId())) {
            continue;
        }
        auto group = static_cast<SoGroup*>(node);
        int idx = group->findChild(pcBoundSwitch);
        if (idx >= 0) {
            // make sure we are added last
            if (idx == group->getNumChildren() - 1) {
                continue;
            }
            group->removeChild(idx);
        }
        group->addChild(pcBoundSwitch);
    }
}

namespace
{
float getBoundBoxFontSize()
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/View"
    );
    return hGrp->GetFloat("BoundingBoxFontSize", 10.0);
}
}  // namespace

void ViewProviderGeometryObject::showBoundingBox(bool show)
{
    if (!pcBoundSwitch && show) {
        unsigned long bbcol = getBoundColor();
        float red {};
        float green {};
        float blue {};
        red = ((bbcol >> 24) & 0xff) / 255.0F;
        green = ((bbcol >> 16) & 0xff) / 255.0F;
        blue = ((bbcol >> 8) & 0xff) / 255.0F;

        pcBoundSwitch = new SoSwitch();
        pcBoundSwitch->ref();
        pcBoundSwitch->setName("BoundSwitch");
        auto pBoundingSep = new SoSeparator();
        auto lineStyle = new SoDrawStyle;
        lineStyle->lineWidth = 2.0F;
        pBoundingSep->addChild(lineStyle);

        if (!pcBoundColor) {
            pcBoundColor = new SoBaseColor;
            pcBoundColor->ref();
            pcBoundColor->setName("BoundColor");
        }
        pcBoundColor->rgb.setValue(red, green, blue);
        pBoundingSep->addChild(pcBoundColor);
        auto font = new SoFont();
        font->size.setValue(getBoundBoxFontSize());
        pBoundingSep->addChild(font);

        if (!pcBoundingBox) {
            pcBoundingBox = new SoFCBoundingBox;
            pcBoundingBox->ref();
            pcBoundingBox->setName("BoundingBox");
        }
        pBoundingSep->addChild(pcBoundingBox);
        pcBoundingBox->coordsOn.setValue(false);
        pcBoundingBox->dimensionsOn.setValue(true);

        // add to the highlight node
        pcBoundSwitch->addChild(pBoundingSep);

        updateBoundingBox();

        addBoundSwitch();
        pcSwitchSensor = new SoNodeSensor;
        pcSwitchSensor->setData(this);
        pcSwitchSensor->attach(pcModeSwitch);
        pcSwitchSensor->setFunction([](void* data, SoSensor*) {
            static_cast<ViewProviderGeometryObject*>(data)->addBoundSwitch();
        });
    }

    if (pcBoundSwitch) {
        // Respect object visibility: never show bounding box on a hidden object
        pcBoundSwitch->whichChild = (show && isShow()) ? 0 : -1;
    }
}

void ViewProviderGeometryObject::hide()
{
    if (pcBoundSwitch) {
        pcBoundSwitch->whichChild = -1;
    }
    ViewProviderDragger::hide();
}

void ViewProviderGeometryObject::show()
{
    ViewProviderDragger::show();
    showBoundingBox(BoundingBox.getValue());
}

void ViewProviderGeometryObject::setSelectable(bool selectable)
{
    SoSearchAction sa;
    sa.setInterest(SoSearchAction::ALL);
    sa.setSearchingAll(true);
    sa.setType(Gui::SoFCSelection::getClassTypeId());
    sa.apply(pcRoot);

    SoPathList& pathList = sa.getPaths();

    for (int i = 0; i < pathList.getLength(); i++) {
        auto selNode = dynamic_cast<SoFCSelection*>(pathList[i]->getTail());
        if (selectable) {
            if (selNode) {
                selNode->selectionMode = SoFCSelection::SEL_ON;
                selNode->preselectionMode = SoFCSelection::AUTO;
            }
        }
        else {
            if (selNode) {
                selNode->selectionMode = SoFCSelection::SEL_OFF;
                selNode->preselectionMode = SoFCSelection::OFF;
                selNode->selected = SoFCSelection::NOTSELECTED;
            }
        }
    }

    pickStyle->style.setValue(selectable ? SoPickStyle::SHAPE : SoPickStyle::UNPICKABLE);
}

PyObject* ViewProviderGeometryObject::getPyObject()
{
    if (!pyViewObject) {
        pyViewObject = new ViewProviderGeometryObjectPy(this);
    }
    pyViewObject->IncRef();
    return pyViewObject;
}

void ViewProviderGeometryObject::handleChangedPropertyName(
    Base::XMLReader& reader,
    const char* TypeName,
    const char* PropName
)
{
    if (strcmp(PropName, "ShapeColor") == 0
        && TypeName == App::PropertyColor::getClassTypeId().getName()) {
        App::PropertyColor prop;
        prop.Restore(reader);
        ShapeAppearance.setDiffuseColor(prop.getValue());
    }
    else if (
        strcmp(PropName, "ShapeMaterial") == 0
        && TypeName == App::PropertyMaterial::getClassTypeId().getName()
    ) {
        App::PropertyMaterial prop;
        prop.Restore(reader);
        ShapeAppearance.setValue(prop.getValue());
    }
    else {
        ViewProviderDragger::handleChangedPropertyName(reader, TypeName, PropName);
    }
}
