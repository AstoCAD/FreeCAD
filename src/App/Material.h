// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2005 Jürgen Riegel <juergen.riegel@web.de>              *
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

#include <cstddef>
#include <string>
#include <vector>

#include <Base/Color.h>

namespace App
{

/** Material class
 */
class AppExport Material
{
public:
    enum MaterialType
    {
        BRASS,
        BRONZE,
        COPPER,
        GOLD,
        PEWTER,
        PLASTER,
        PLASTIC,
        SILVER,
        STEEL,
        STONE,
        SHINY_PLASTIC,
        SATIN,
        METALIZED,
        NEON_GNC,
        CHROME,
        ALUMINIUM,
        OBSIDIAN,
        NEON_PHC,
        JADE,
        RUBY,
        EMERALD,
        DEFAULT,
        USER_DEFINED
    };

public:
    /** @name Constructors
     */
    //@{
    /** Sets the USER_DEFINED material type. The user must set the colors afterwards. */
    Material();
    ~Material() = default;
    /** Copy constructor. */
    Material(const Material& other) = default;
    Material(Material&& other) = default;
    /** Defines the colors and shininess for the material \a MatName. If \a MatName isn't defined
     * then USER_DEFINED is set and the user must define the colors itself.
     */
    explicit Material(const char* MatName);
    /** Does basically the same as the constructor above unless that it accepts a MaterialType as
     * argument. */
    explicit Material(MaterialType MatType);
    //@}

    /** Set a material by name
     *  There are some standard materials defined which are:
     *  \li Brass
     *  \li Bronze
     *  \li Copper
     *  \li Gold
     *  \li Pewter
     *  \li Plaster
     *  \li Plastic
     *  \li Silver
     *  \li Steel
     *  \li Stone
     *  \li Shiny plastic
     *  \li Satin
     *  \li Metalized
     *  \li Neon GNC
     *  \li Chrome
     *  \li Aluminium
     *  \li Obsidian
     *  \li Neon PHC
     *  \li Jade
     *  \li Ruby
     *  \li Emerald
     * Furthermore there two additional modes \a Default which defines a kind of grey metallic and
     * user defined that does nothing. The Base::Color and the other properties of the material are
     * defined in the range [0-1]. If \a MatName is an unknown material name then the type
     * USER_DEFINED is set and the material doesn't get changed.
     */
    void set(const char* MatName);
    /**
     * This method is provided for convenience which does basically the same as the method above
     * unless that it accepts a MaterialType as argument.
     */
    void setType(MaterialType MatType);
    /**
     * Returns the currently set material type.
     */
    MaterialType getType() const
    {
        return _matType;
    }

    /** @name Properties */
    //@{
    // NOLINTBEGIN
    Base::Color ambientColor;  /**< Defines the ambient color. */
    Base::Color diffuseColor;  /**< Defines the diffuse color. */
    Base::Color specularColor; /**< Defines the specular color. */
    Base::Color emissiveColor; /**< Defines the emissive color. */
    float shininess;
    float transparency;
    std::string image;
    std::string imagePath;
    std::string uuid;
    // NOLINTEND
    //@}

    bool operator==(const Material& m) const
    {
        // clang-format off
        if (!uuid.empty() && uuid == m.uuid) {
            return true;
        }
        return shininess == m.shininess
            && transparency == m.transparency
            && ambientColor == m.ambientColor
            && diffuseColor == m.diffuseColor
            && specularColor == m.specularColor
            && emissiveColor == m.emissiveColor
            && image == m.image
            && imagePath == m.imagePath;
        // clang-format on
    }
    bool operator!=(const Material& m) const
    {
        return !operator==(m);
    }
    Material& operator=(const Material& other) = default;
    Material& operator=(Material&& other) = default;

    static Material getDefaultAppearance();

private:
    MaterialType _matType;
};

/** Appearance overrides on top of the look of the physical material
 *
 * The look of a shape follows the appearance of its physical material unless it is overridden.
 * The view providers save the overrides as a list of names: objectName() when the look of the
 * whole object is overridden and faceName() for a face with its own look. Other kinds of names
 * (feature overrides, mapped element names) can be added later: names that are not understood are
 * kept as they are.
 *
 * The appearance is a list with one entry for the whole object or one entry per face. The
 * functions are pure so that the rules can be tested without a GUI.
 */
class AppExport AppearanceOverrides
{
public:
    /// The name that marks the look of the whole object as overridden
    static const char* objectName();
    /// The name of the face with the zero-based @a index ("Face1" for 0)
    static std::string faceName(std::size_t index);
    /// The zero-based index of a face name, or -1 if @a name is not a face name
    static int faceIndex(const std::string& name);

    /** Whether both looks are the same, regardless of the card (UUID) they come from and of the
     * transparency: the transparency is set on its own and is kept when the material changes.
     */
    static bool sameLook(const Material& first, const Material& second);
    /// Whether a material look has an appearance of its own (Air for example has none)
    static bool hasLook(const Material& materialLook);

    /** The overrides after something other than the material replaced the appearance
     * @a before by @a after: an appearance that differs from the material look is an override.
     */
    static std::vector<std::string> afterChange(
        const std::vector<std::string>& overrides,
        const std::vector<Material>& before,
        const std::vector<Material>& after,
        const Material& materialLook
    );

    /** The appearance after the material look changed to @a materialLook: every face that is not
     * overridden takes the new look and keeps its transparency. Returns false if the appearance
     * does not change.
     */
    static bool followMaterial(
        const std::vector<std::string>& overrides,
        const std::vector<Material>& appearance,
        const Material& materialLook,
        std::vector<Material>& result
    );

    /** Clears the overrides of @a faces (zero-based), or all overrides if @a faces is empty, and
     * gives these faces the look they inherit: the object override if there is one, else
     * @a materialLook. The faces keep their transparency.
     */
    static void reset(
        std::vector<std::string>& overrides,
        std::vector<Material>& appearance,
        const Material& materialLook,
        const std::vector<std::size_t>& faces = {}
    );

    /** The overrides of an appearance saved before they were recorded. A look that equals the
     * material look or one of the default looks follows the material, anything else is an
     * override.
     */
    static std::vector<std::string> guess(
        const std::vector<Material>& appearance,
        const Material& materialLook,
        const Material& defaultLook
    );
};

}  // namespace App
