// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2023 David Carter <dcarter@david.carter.ca>             *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 **************************************************************************/

#include <QMetaType>
#include <QTextStream>
#include <QUuid>



#include <App/Application.h>
#include <Base/Writer.h>
#include <Gui/MetaTypes.h>

#include <Base/Console.h>

#include "MaterialLoader.h"
#include "MaterialManager.h"
#include "MaterialPy.h"
#include "PropertyMaterial.h"

using namespace Materials;

/* TRANSLATOR Material::PropertyMaterial */

TYPESYSTEM_SOURCE(Materials::PropertyMaterial, App::Property)

PropertyMaterial::PropertyMaterial() = default;

PropertyMaterial::~PropertyMaterial() = default;

void PropertyMaterial::setValue(const Material& mat)
{
    aboutToSetValue();
    _material = mat;
    hasSetValue();
}

void PropertyMaterial::setValue(const App::Material& mat)
{
    aboutToSetValue();
    _material = mat;
    hasSetValue();
}

const Material& PropertyMaterial::getValue() const
{
    return _material;
}

PyObject* PropertyMaterial::getPyObject()
{
    return new MaterialPy(new Material(_material));
}

void PropertyMaterial::setPyObject(PyObject* value)
{
    if (PyObject_TypeCheck(value, &(MaterialPy::Type))) {
        setValue(*static_cast<MaterialPy*>(value)->getMaterialPtr());
    }
    else {
        std::string error = std::string("type must be 'Material' not ");
        error += value->ob_type->tp_name;
        throw Base::TypeError(error);
    }
}

std::string PropertyMaterial::embeddedCard() const
{
    // Only a material that is not in a library (e.g. built by a script) is embedded: the UUID
    // alone would not bring it back when the document is opened again
    if (MaterialManager::getManager().exists(_material.getUUID())) {
        return {};
    }

    try {
        // Save a copy: saving may change the material (UUID, format flags)
        Material material(_material);
        QString card;
        QTextStream stream(&card);
        material.save(stream, true, false, false);
        stream.flush();
        return card.toStdString();
    }
    catch (const Base::Exception& e) {
        Base::Console().warning("Material '{}' is saved without its properties: {}\n",
                                _material.getName().toStdString(),
                                e.what());
    }
    return {};
}

void PropertyMaterial::Save(Base::Writer& writer) const
{
    writer.Stream() << writer.ind() << "<PropertyMaterial uuid=\""
                    << _material.getUUID().toStdString() << "\"";
    // Older versions read the UUID only and ignore the card
    auto card = embeddedCard();
    if (!card.empty()) {
        writer.Stream() << " card=\"" << encodeAttribute(card) << "\"";
    }
    writer.Stream() << "/>" << std::endl;
}

void PropertyMaterial::Restore(Base::XMLReader& reader)
{
    // read my Element
    reader.readElement("PropertyMaterial");
    // get the value of my Attribute
    auto uuid = QString::fromLatin1(reader.getAttribute<const char*>("uuid"));

    auto& manager = MaterialManager::getManager();
    // A library material wins; the embedded card is for a material no library has
    if (reader.hasAttribute("card") && !manager.exists(uuid)) {
        try {
            auto material =
                MaterialLoader::materialFromYAML(reader.getAttribute<const char*>("card"));
            setValue(*material);
            return;
        }
        catch (const Base::Exception& e) {
            Base::Console().error("Unable to read the embedded material '{}': {}\n",
                                  uuid.toStdString(),
                                  e.what());
        }
        catch (const std::exception& e) {
            Base::Console().error("Unable to read the embedded material '{}': {}\n",
                                  uuid.toStdString(),
                                  e.what());
        }
    }

    setValue(*manager.getMaterial(uuid));
}

const char* PropertyMaterial::getEditorName() const
{
    if (testStatus(MaterialEdit)) {
        return "";  //"Gui::PropertyEditor::PropertyMaterialItem";
    }
    return "";
}

App::Property* PropertyMaterial::Copy() const
{
    PropertyMaterial* p = new PropertyMaterial();
    p->_material = _material;
    return p;
}

void PropertyMaterial::Paste(const App::Property& from)
{
    aboutToSetValue();
    _material = dynamic_cast<const PropertyMaterial&>(from)._material;
    hasSetValue();
}
