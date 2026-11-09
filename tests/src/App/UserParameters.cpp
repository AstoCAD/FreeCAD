// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <algorithm>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/PropertyStandard.h>
#include <App/PropertyUnits.h>
#include <App/QuantityInput.h>
#include <App/UserParameters.h>
#include <Base/NumericFormatting.h>
#include <Base/Exception.h>
#include <Base/Quantity.h>
#include <src/App/InitApplication.h>

namespace UP = App::UserParameters;

// NOLINTBEGIN(readability-magic-numbers)

class UserParameters: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }

    void SetUp() override
    {
        _docName = App::GetApplication().getUniqueDocumentName("userparams");
        _doc = App::GetApplication().newDocument(_docName.c_str(), "testUser");
        // The holder of the user parameters of the document, as the first parameter creates it
        // (createdOnTheHolderOfTheDocument): the parameters typed in it are its own properties.
        holder = _doc->addObject("App::VarSet", UP::HolderName);
        other = _doc->addObject("App::VarSet", "Other");
        target = other->addDynamicProperty("App::PropertyDistance", "Target", "Base");
    }

    void TearDown() override
    {
        App::GetApplication().closeDocument(_docName.c_str());
    }

    App::Document* doc()
    {
        return _doc;
    }

    std::shared_ptr<App::Expression> parse(const App::DocumentObject* owner, const char* text)
    {
        return std::shared_ptr<App::Expression>(App::ExpressionParser::parse(owner, text));
    }

    App::DocumentObject* holder {};
    App::DocumentObject* other {};
    App::Property* target {};

private:
    std::string _docName;
    App::Document* _doc {};
};

TEST_F(UserParameters, splitAssignment)
{
    std::string name;
    std::string rhs;
    EXPECT_TRUE(UP::splitAssignment("myVar = 23 mm", name, rhs));
    EXPECT_EQ(name, "myVar");
    EXPECT_EQ(rhs, "23 mm");
    EXPECT_TRUE(UP::splitAssignment("  b=2*a  ", name, rhs));
    EXPECT_EQ(name, "b");
    EXPECT_EQ(rhs, "2*a");

    // Not assignments: comparisons, missing parts, qualified targets, plain expressions.
    for (const char* text : {"a == 2", "a<=2", "a >= 2", "a != 2", "= 2", "a =", "a.b = 2",
                             "2*a", "<<label>> = 3", "1a = 2"}) {
        EXPECT_FALSE(UP::splitAssignment(text, name, rhs)) << text;
    }
}

TEST_F(UserParameters, assignmentIsNotValidExpressionSyntax)
{
    // Recognising "name = expr" cannot change the meaning of any existing expression.
    EXPECT_THROW(parse(holder, "myVar = 23 mm"), Base::Exception);
    EXPECT_THROW(parse(holder, "myVar=23"), Base::Exception);
}

TEST_F(UserParameters, checkName)
{
    EXPECT_EQ(UP::checkName(doc(), "myVar", holder), UP::NameStatus::Available);
    for (const char* name : {"", "mm", "in", "pi", "e", "1abc", "my var", "_hidden"}) {
        EXPECT_EQ(UP::checkName(doc(), name, holder), UP::NameStatus::Invalid) << name;
    }
    EXPECT_EQ(UP::checkName(doc(), "Other", holder), UP::NameStatus::UsedByObject);
    other->Label.setValue("SomeLabel");
    EXPECT_EQ(UP::checkName(doc(), "SomeLabel", holder), UP::NameStatus::UsedByObject);
    EXPECT_EQ(UP::checkName(doc(), "Target", other), UP::NameStatus::UsedByOwnerProperty);
    EXPECT_EQ(UP::checkName(doc(), "Label", holder), UP::NameStatus::UsedByOwnerProperty);
    // A property of another object is not a clash: it only shadows the name from that object.
    EXPECT_EQ(UP::checkName(doc(), "Target", holder), UP::NameStatus::Available);

    UP::addParameter(holder, "myVar", Base::Unit::Length);
    EXPECT_EQ(UP::checkName(doc(), "myVar", other), UP::NameStatus::UsedByParameter);
    EXPECT_EQ(UP::checkName(doc(), "myVar", holder), UP::NameStatus::UsedByParameter);
    EXPECT_THROW(UP::addParameter(other, "myVar", Base::Unit::Length), Base::NameError);
    EXPECT_FALSE(UP::nameStatusMessage(UP::NameStatus::UsedByParameter, "myVar").empty());
}

TEST_F(UserParameters, cellAddressNames)
{
    for (const char* name : {"A1", "B5", "AA12", "ZZ16384", "Z00001"}) {
        EXPECT_TRUE(UP::isCellAddressName(name)) << name;
        EXPECT_EQ(UP::checkName(doc(), name, holder), UP::NameStatus::CellAddress) << name;
        EXPECT_EQ(UP::checkName(nullptr, name), UP::NameStatus::CellAddress) << name;
        EXPECT_THROW(UP::addParameter(holder, name, Base::Unit::Length), Base::NameError) << name;
    }
    // Not cells: lower case, three letters, row 0 or out of range, letters after the digits.
    for (const char* name : {"b5", "Ab1", "AAA1", "A0", "ZZ16385", "A123456", "A1x", "x1"}) {
        EXPECT_FALSE(UP::isCellAddressName(name)) << name;
        EXPECT_EQ(UP::checkName(doc(), name, holder), UP::NameStatus::Available) << name;
    }
    EXPECT_FALSE(UP::isCellAddressName(""));
    EXPECT_FALSE(UP::isCellAddressName("A"));
    const std::string message = UP::nameStatusMessage(UP::NameStatus::CellAddress, "B5");
    EXPECT_NE(message.find("B5"), std::string::npos);
    EXPECT_NE(message.find("cell"), std::string::npos);
}

TEST_F(UserParameters, pythonAttributeNames)
{
    // In Python a property hides the attribute of the same name (`obj.Name` would return the
    // parameter): attributes and methods from every level of the type are refused.
    const auto expectRefused = [this](const char* name) {
        EXPECT_EQ(UP::checkName(doc(), name, holder), UP::NameStatus::PythonAttribute) << name;
        // Every owner is a document object, so these are refused before the owner is known.
        EXPECT_EQ(UP::checkName(doc(), name), UP::NameStatus::PythonAttribute) << name;
        EXPECT_EQ(UP::checkName(nullptr, name), UP::NameStatus::PythonAttribute) << name;
        EXPECT_THROW(UP::addParameter(holder, name, Base::Unit::Length), Base::NameError) << name;
        EXPECT_EQ(holder->getDynamicPropertyByName(name), nullptr) << name;
    };
    for (const char* name : {"Name", "Document", "State", "InList", "ViewObject", "ID"}) {
        expectRefused(name);
    }
    for (const char* name : {"PropertiesList", "Content", "TypeId", "Module"}) {
        expectRefused(name);
    }
    for (const char* name : {"recompute", "touch", "addProperty", "setExpression"}) {
        expectRefused(name);
    }

    // The type of the owner decides: a Python feature has its own Python type.
    auto* python = doc()->addObject("App::FeaturePython", "Python");
    ASSERT_NE(python, nullptr);
    EXPECT_EQ(UP::checkName(doc(), "Name", python), UP::NameStatus::PythonAttribute);
    EXPECT_EQ(UP::checkName(doc(), "recompute", python), UP::NameStatus::PythonAttribute);
    EXPECT_EQ(UP::checkName(doc(), "myVar", python), UP::NameStatus::Available);

    // Renaming to such a name is refused as well and leaves the parameter as it was.
    auto* prop = UP::addParameter(holder, "myVar", Base::Unit::Length);
    EXPECT_THROW(UP::rename(prop, "Document"), Base::NameError);
    EXPECT_STREQ(prop->getName(), "myVar");

    // Not attributes of the object: a property keeps its own status, names are case sensitive,
    // and `mro` is an attribute of the type object only.
    EXPECT_EQ(UP::checkName(doc(), "Label", holder), UP::NameStatus::UsedByOwnerProperty);
    for (const char* name : {"name", "document", "Width", "Length", "mro"}) {
        EXPECT_EQ(UP::checkName(doc(), name, holder), UP::NameStatus::Available) << name;
    }

    const std::string message = UP::nameStatusMessage(UP::NameStatus::PythonAttribute, "Name");
    EXPECT_NE(message.find("Name"), std::string::npos);
    EXPECT_NE(message.find("Python"), std::string::npos);
}

TEST_F(UserParameters, propertyTypes)
{
    EXPECT_EQ(UP::propertyTypeForUnit(Base::Unit::One), App::PropertyFloat::getClassTypeId());
    EXPECT_EQ(UP::propertyTypeForUnit(Base::Unit::Length), App::PropertyDistance::getClassTypeId());
    EXPECT_EQ(UP::propertyTypeForUnit(Base::Unit::Force), App::PropertyForce::getClassTypeId());
    EXPECT_EQ(UP::propertyTypeForUnit(Base::Unit::Angle), App::PropertyAngle::getClassTypeId());

    // The unit must be stored by the type: a plain PropertyQuantity loses it on save.
    const Base::Unit noType = Base::Unit::Length * Base::Unit::Force * Base::Unit::Force;
    EXPECT_TRUE(UP::propertyTypeForUnit(noType).isBad());
    EXPECT_THROW(UP::addParameter(holder, "odd", noType), Base::TypeError);
    EXPECT_EQ(holder->getPropertyByName("odd"), nullptr);

    auto* angle = UP::addParameter(holder, "turn", Base::Unit::Angle);
    EXPECT_EQ(angle->getTypeId(), App::PropertyAngle::getClassTypeId());

    // Not named after the unit type, TimeSpan
    EXPECT_EQ(UP::propertyTypeForUnit(Base::Unit::TimeSpan), App::PropertyTime::getClassTypeId());
    // No property type stores a concentration
    EXPECT_TRUE(UP::propertyTypeForUnit(Base::Unit::Concentration).isBad());
}

TEST_F(UserParameters, everyNamedUnitHasAPropertyTypeOfThatUnit)
{
    // Every unit of Base::Unit except Concentration, which no property type has
    const std::vector<Base::Unit> units {
        Base::Unit::Acceleration,
        Base::Unit::AmountOfSubstance,
        Base::Unit::Angle,
        Base::Unit::AngleOfFriction,
        Base::Unit::Area,
        Base::Unit::CompressiveStrength,
        Base::Unit::CurrentDensity,
        Base::Unit::Density,
        Base::Unit::DissipationRate,
        Base::Unit::DynamicViscosity,
        Base::Unit::ElectricalCapacitance,
        Base::Unit::ElectricalConductance,
        Base::Unit::ElectricalConductivity,
        Base::Unit::ElectricalInductance,
        Base::Unit::ElectricalResistance,
        Base::Unit::ElectricCharge,
        Base::Unit::ElectricCurrent,
        Base::Unit::ElectricPotential,
        Base::Unit::ElectromagneticPotential,
        Base::Unit::Force,
        Base::Unit::Frequency,
        Base::Unit::HeatFlux,
        Base::Unit::MassMomentOfInertia,
        Base::Unit::AreaMomentOfInertia,
        Base::Unit::InverseArea,
        Base::Unit::InverseLength,
        Base::Unit::InverseVolume,
        Base::Unit::KinematicViscosity,
        Base::Unit::Length,
        Base::Unit::LuminousIntensity,
        Base::Unit::MagneticFieldStrength,
        Base::Unit::MagneticFlux,
        Base::Unit::MagneticFluxDensity,
        Base::Unit::Magnetization,
        Base::Unit::Mass,
        Base::Unit::Moment,
        Base::Unit::Pressure,
        Base::Unit::Power,
        Base::Unit::ShearModulus,
        Base::Unit::SpecificEnergy,
        Base::Unit::SpecificHeat,
        Base::Unit::Stiffness,
        Base::Unit::StiffnessDensity,
        Base::Unit::Stress,
        Base::Unit::SurfaceChargeDensity,
        Base::Unit::Temperature,
        Base::Unit::TimeSpan,
        Base::Unit::ThermalConductivity,
        Base::Unit::ThermalExpansionCoefficient,
        Base::Unit::ThermalTransferCoefficient,
        Base::Unit::UltimateTensileStrength,
        Base::Unit::VacuumPermittivity,
        Base::Unit::Velocity,
        Base::Unit::Volume,
        Base::Unit::VolumeChargeDensity,
        Base::Unit::VolumeFlowRate,
        Base::Unit::VolumetricThermalExpansionCoefficient,
        Base::Unit::Work,
        Base::Unit::YieldStrength,
        Base::Unit::YoungsModulus,
    };
    int index = 0;
    for (const Base::Unit& unit : units) {
        const std::string name = "u" + std::to_string(index++);
        App::Property* prop = UP::addParameter(holder, name, unit);
        const auto* quantity = freecad_cast<App::PropertyQuantity*>(prop);
        ASSERT_NE(quantity, nullptr) << unit.getTypeString();
        EXPECT_EQ(quantity->getUnit(), unit) << unit.getTypeString();
    }
}

TEST_F(UserParameters, numberWithCompoundUnitIsALiteral)
{
    for (const char* text : {"3 m/s", "-3 m/s", "5 mm^2", "2 m^-1", "9.81 m/s^2"}) {
        auto* prop = UP::createParameter(holder, "v", parse(holder, text));
        const auto quantity = parse(holder, text)->eval();
        EXPECT_DOUBLE_EQ(
            freecad_cast<App::PropertyFloat*>(prop)->getValue(),
            freecad_cast<App::NumberExpression*>(quantity.get())->getQuantity().getValue()
        ) << text;
        EXPECT_EQ(holder->getExpression(App::ObjectIdentifier(*prop)).expression, nullptr) << text;
        UP::removeParameter(prop);
    }
    // A computation is bound
    auto* computed = UP::createParameter(holder, "computed", parse(holder, "3 m/s * 2"));
    EXPECT_NE(holder->getExpression(App::ObjectIdentifier(*computed)).expression, nullptr);
    // A function is not a unit, although FunctionExpression derives from UnitExpression
    for (const char* text : {"10 mm * sin(30 deg)", "10 mm / cos(30 deg)"}) {
        auto* prop = UP::createParameter(holder, "slanted", parse(holder, text));
        EXPECT_NE(holder->getExpression(App::ObjectIdentifier(*prop)).expression, nullptr) << text;
        UP::removeParameter(prop);
    }
}

TEST_F(UserParameters, createLiteralParameter)
{
    auto* prop = UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    ASSERT_NE(prop, nullptr);
    EXPECT_TRUE(UP::isUserParameter(prop));
    EXPECT_STREQ(prop->getGroup(), UP::GroupName);
    EXPECT_EQ(prop->getTypeId(), App::PropertyDistance::getClassTypeId());
    EXPECT_DOUBLE_EQ(freecad_cast<App::PropertyDistance*>(prop)->getValue(), 23.0);
    // A literal is a value, not an expression: it stays editable.
    EXPECT_EQ(holder->getExpression(App::ObjectIdentifier(*prop)).expression, nullptr);

    EXPECT_EQ(UP::findParameter(doc(), "myVar"), prop);
    EXPECT_EQ(UP::findParameter(doc(), "unknown"), nullptr);
    ASSERT_EQ(UP::getParameters(doc()).size(), 1U);
    EXPECT_EQ(UP::getParameters(doc()).front(), prop);
}

TEST_F(UserParameters, dimensionlessValueTakesImpliedUnit)
{
    auto* prop = UP::createParameter(holder, "w", parse(holder, "4"), Base::Unit::Length);
    EXPECT_EQ(prop->getTypeId(), App::PropertyDistance::getClassTypeId());
    auto* plain = UP::createParameter(holder, "ratio", parse(holder, "0.5"));
    EXPECT_EQ(plain->getTypeId(), App::PropertyFloat::getClassTypeId());
}

TEST_F(UserParameters, createExpressionParameterAndFailureLeavesOwnerUnchanged)
{
    UP::createParameter(holder, "base", parse(holder, "10 mm"));
    auto* twice = UP::createParameter(holder, "twice", parse(holder, "2 * base"));
    EXPECT_NE(holder->getExpression(App::ObjectIdentifier(*twice)).expression, nullptr);
    EXPECT_DOUBLE_EQ(freecad_cast<App::PropertyDistance*>(twice)->getValue(), 20.0);

    // A non numeric value or a taken name must not leave a property behind.
    EXPECT_THROW(UP::createParameter(holder, "text", parse(holder, "<<abc>>")), Base::Exception);
    EXPECT_EQ(holder->getPropertyByName("text"), nullptr);
    EXPECT_THROW(UP::createParameter(other, "base", parse(other, "1 mm")), Base::NameError);
}

TEST_F(UserParameters, createTextParameter)
{
    const auto text = UP::ValueKind::NumberOrText;
    // A text is a value only where it is accepted: not in the input of a quantity.
    EXPECT_THROW(UP::createParameter(holder, "label", parse(holder, "<<abc>>")), Base::TypeError);

    const Base::Unit none = Base::Unit::One;
    auto* label = UP::createParameter(holder, "label", parse(holder, "<<abc>>"), none, text);
    ASSERT_TRUE(label->is<App::PropertyString>());
    EXPECT_TRUE(UP::isUserParameter(label));
    EXPECT_STREQ(static_cast<App::PropertyString*>(label)->getValue(), "abc");
    EXPECT_EQ(holder->getExpression(App::ObjectIdentifier(*label)).expression, nullptr);
    EXPECT_EQ(UP::findParameter(doc(), "label"), label);

    // A computed text is bound, and follows what it is computed from.
    auto* computed
        = UP::createParameter(holder, "full", parse(holder, "label + <<def>>"), none, text);
    ASSERT_TRUE(computed->is<App::PropertyString>());
    EXPECT_NE(holder->getExpression(App::ObjectIdentifier(*computed)).expression, nullptr);
    EXPECT_STREQ(static_cast<App::PropertyString*>(computed)->getValue(), "abcdef");
    static_cast<App::PropertyString*>(label)->setValue("xyz");
    doc()->recompute();
    EXPECT_STREQ(static_cast<App::PropertyString*>(computed)->getValue(), "xyzdef");

    // Numbers are created as without it, and the names follow the same rules.
    const Base::Unit length = Base::Unit::Length;
    auto* width = UP::createParameter(holder, "width", parse(holder, "4"), length, text);
    EXPECT_TRUE(width->is<App::PropertyDistance>());
    EXPECT_THROW(
        UP::createParameter(other, "label", parse(other, "<<again>>"), none, text),
        Base::NameError
    );
    EXPECT_THROW(
        UP::createParameter(holder, "list", parse(holder, "list(1, 2)"), none, text),
        Base::TypeError
    );
    EXPECT_EQ(holder->getPropertyByName("list"), nullptr);

    EXPECT_TRUE(UP::rename(label, "title"));
    EXPECT_EQ(UP::findParameter(doc(), "title"), holder->getPropertyByName("title"));
    EXPECT_TRUE(UP::removeParameter(holder->getPropertyByName("title")));
}

TEST_F(UserParameters, qualifyReferencesOnlyAsFallback)
{
    auto* prop = UP::createParameter(holder, "myVar", parse(holder, "23 mm"));

    auto expr = parse(other, "2 * myVar");
    EXPECT_EQ(UP::qualifyReferences(other, *expr), 1);
    EXPECT_EQ(expr->toString(), "2 * UserParameters.myVar");

    // Owner-local reference: resolves today, left alone.
    auto local = parse(holder, "myVar + 1 mm");
    EXPECT_EQ(UP::qualifyReferences(holder, *local), 0);
    EXPECT_EQ(local->toString(), "myVar + 1 mm");

    // An owner property with the same name keeps its meaning.
    other->addDynamicProperty("App::PropertyDistance", "myVar", "Base");
    auto shadowed = parse(other, "myVar");
    EXPECT_EQ(UP::qualifyReferences(other, *shadowed), 0);
    EXPECT_EQ(shadowed->toString(), "myVar");

    // Explicit references are untouched.
    auto explicitRef = parse(other, "UserParameters.myVar");
    EXPECT_EQ(UP::qualifyReferences(other, *explicitRef), 0);
    EXPECT_EQ(prop, UP::findParameter(doc(), "myVar"));
}

TEST_F(UserParameters, ambiguousNamesAreNotResolved)
{
    UP::createParameter(holder, "dup", parse(holder, "1 mm"));
    // e.g. after copying the holder: the same name twice in UserParameters groups
    other->addDynamicProperty("App::PropertyDistance", "dup", UP::GroupName);
    EXPECT_EQ(UP::findParameter(doc(), "dup"), nullptr);
    auto* third = doc()->addObject("App::VarSet", "Third");
    auto expr = parse(third, "dup");
    EXPECT_EQ(UP::qualifyReferences(third, *expr), 0);
}

TEST_F(UserParameters, dependencyAndRecompute)
{
    auto* prop = UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    auto expr = parse(other, "2 * myVar");
    UP::qualifyReferences(other, *expr);
    other->setExpression(App::ObjectIdentifier(*target), expr);

    const auto outList = other->getOutList();
    EXPECT_NE(std::find(outList.begin(), outList.end(), holder), outList.end());

    doc()->recompute();
    EXPECT_DOUBLE_EQ(freecad_cast<App::PropertyDistance*>(target)->getValue(), 46.0);
    freecad_cast<App::PropertyDistance*>(prop)->setValue(5.0);
    doc()->recompute();
    EXPECT_DOUBLE_EQ(freecad_cast<App::PropertyDistance*>(target)->getValue(), 10.0);
}

TEST_F(UserParameters, renameUpdatesReferences)
{
    auto* prop = UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    auto expr = parse(other, "2 * myVar");
    UP::qualifyReferences(other, *expr);
    other->setExpression(App::ObjectIdentifier(*target), expr);
    auto* local = holder->addDynamicProperty("App::PropertyDistance", "Local", "Base");
    holder->setExpression(App::ObjectIdentifier(*local), parse(holder, "myVar"));

    EXPECT_THROW(UP::rename(prop, "Other"), Base::NameError);
    EXPECT_TRUE(UP::rename(prop, "width"));
    EXPECT_EQ(holder->getPropertyByName("myVar"), nullptr);
    EXPECT_EQ(holder->getPropertyByName("width"), prop);
    EXPECT_EQ(other->getExpression(App::ObjectIdentifier(*target)).expression->toString(),
              "2 * UserParameters.width");
    EXPECT_EQ(holder->getExpression(App::ObjectIdentifier(*local)).expression->toString(),
              "width");
    doc()->recompute();
    EXPECT_DOUBLE_EQ(freecad_cast<App::PropertyDistance*>(target)->getValue(), 46.0);
}

TEST_F(UserParameters, displayStringIsShortWhenUnambiguous)
{
    UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    auto expr = parse(other, "2 * myVar");
    UP::qualifyReferences(other, *expr);
    EXPECT_EQ(UP::toDisplayString(other, *expr), "2 * myVar");
    // The stored, persistent form stays qualified.
    EXPECT_EQ(expr->toString(true), "2 * UserParameters.myVar");

    // A reference written explicitly and re-parsed (as after a file load) is shortened too.
    auto reparsed = parse(other, "UserParameters.myVar / 2");
    EXPECT_EQ(UP::toDisplayString(other, *reparsed), "myVar / 2");

    // Not shortened when the short name would mean something else for the owner.
    other->addDynamicProperty("App::PropertyDistance", "myVar", "Base");
    EXPECT_EQ(UP::toDisplayString(other, *reparsed), "UserParameters.myVar / 2");
}

TEST_F(UserParameters, quantityInputResolvesUserParameters)
{
    const Base::NumericLocaleContext enUs {"en_US", ".", ",", "+", "-", 3, 3, "0"};
    const auto interpret = [&](const char* text) {
        return App::interpretQuantityInput(
            text,
            App::QuantityInputGrammar::Expression,
            App::ObjectIdentifier(*target),
            App::QuantityInputUnit(Base::Unit::Length),
            enUs,
            App::InputPhase::Commit,
            App::QuantityConstraints {}
        );
    };

    // Before the parameter exists the name is an error, exactly as today.
    const auto missing = interpret("2 * myVar");
    EXPECT_EQ(missing.status, App::InputStatus::Invalid);

    UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    const auto result = interpret("2 * myVar");
    ASSERT_EQ(result.status, App::InputStatus::Acceptable);
    EXPECT_DOUBLE_EQ(result.quantity->getValue(), 46.0);
    ASSERT_NE(result.expression, nullptr);
    EXPECT_EQ(result.expression->toString(), "2 * UserParameters.myVar");
    EXPECT_EQ(result.userParameterReferences, 1);

    // Ordinary input is unchanged and reports no user parameter.
    const auto plain = interpret("2 * 3 mm");
    ASSERT_EQ(plain.status, App::InputStatus::Acceptable);
    EXPECT_EQ(plain.userParameterReferences, 0);
}

TEST_F(UserParameters, pendingParametersAreKnownInTheirScope)
{
    const Base::NumericLocaleContext enUs {"en_US", ".", ",", "+", "-", 3, 3, "0"};
    const auto interpret = [&](const char* text) {
        return App::interpretQuantityInput(
            text,
            App::QuantityInputGrammar::Expression,
            App::ObjectIdentifier(*target),
            App::QuantityInputUnit(Base::Unit::Length),
            enUs,
            App::InputPhase::Commit,
            App::QuantityConstraints {}
        );
    };
    const Base::Quantity height(10.0, Base::Unit::Length);

    {
        UP::PendingScope scope(other, {{"height", height}});
        const auto result = interpret("2 * height + 1");
        ASSERT_EQ(result.status, App::InputStatus::Acceptable);
        EXPECT_DOUBLE_EQ(result.quantity->getValue(), 21.0);
        // The expression keeps the bare name: it refers to the parameter once it is created.
        ASSERT_NE(result.expression, nullptr);
        EXPECT_EQ(result.expression->toString(), "2 * height + 1 mm");
        EXPECT_EQ(result.userParameterReferences, 0);
        // Bare names only, and only for the expressions of the owner of the scope
        EXPECT_EQ(interpret("Other.height").status, App::InputStatus::Invalid);
        EXPECT_EQ(interpret("UserParameters.height").status, App::InputStatus::Invalid);
        UP::PendingScope holderScope(holder, {{"width", height}});
        EXPECT_EQ(interpret("width").status, App::InputStatus::Invalid);
        EXPECT_EQ(interpret("height").status, App::InputStatus::Acceptable);
    }
    EXPECT_EQ(interpret("2 * height").status, App::InputStatus::Invalid);

    // Existing names keep their meaning
    UP::createParameter(holder, "myVar", parse(holder, "23 mm"));
    {
        UP::PendingScope scope(other, {{"myVar", height}, {"Target", height}});
        const auto parameter = interpret("myVar");
        ASSERT_EQ(parameter.status, App::InputStatus::Acceptable);
        EXPECT_DOUBLE_EQ(parameter.quantity->getValue(), 23.0);
        static_cast<App::PropertyDistance*>(target)->setValue(5.0);
        const auto property = interpret("Target");
        ASSERT_EQ(property.status, App::InputStatus::Acceptable);
        EXPECT_DOUBLE_EQ(property.quantity->getValue(), 5.0);
    }
    // Nothing was added to the document
    EXPECT_EQ(other->getPropertyByName("height"), nullptr);
}

TEST_F(UserParameters, createdOnTheHolderOfTheDocument)
{
    // A document without holder: the first parameter creates it, whatever object it is typed in.
    const std::string name = App::GetApplication().getUniqueDocumentName("userparamsholder");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    App::DocumentObject* typed = fresh->addObject("App::VarSet", "Typed");
    EXPECT_EQ(UP::findHolder(fresh), nullptr);

    App::Property* width = UP::createParameter(typed, "width", parse(typed, "10 mm"));
    App::DocumentObject* created = UP::findHolder(fresh);
    ASSERT_NE(created, nullptr);
    EXPECT_TRUE(UP::isHolder(created));
    EXPECT_FALSE(UP::isHolder(typed));
    EXPECT_STREQ(created->getNameInDocument(), UP::HolderName);
    EXPECT_STREQ(created->Label.getValue(), UP::HolderLabel);
    EXPECT_EQ(width->getContainer(), created);
    EXPECT_EQ(typed->getPropertyByName("width"), nullptr);
    EXPECT_EQ(UP::holder(fresh), created);

    // The second one goes to the same holder
    App::Property* height = UP::createParameter(typed, "height", parse(typed, "2 mm"));
    EXPECT_EQ(height->getContainer(), created);
    EXPECT_EQ(fresh->getObjects().size(), 2U);

    // A property is bound to a parameter with its qualified name, the holder with the bare one
    EXPECT_EQ(UP::referenceTo(typed, width)->toString(), "UserParameters.width");
    EXPECT_EQ(UP::referenceTo(created, width)->toString(), "width");
    EXPECT_EQ(UP::referenceTo(typed, typed->getPropertyByName("Label")), nullptr);

    EXPECT_TRUE(UP::removeParameter(height));
    EXPECT_EQ(created->getPropertyByName("height"), nullptr);
    EXPECT_FALSE(UP::removeParameter(typed->getPropertyByName("Label")));

    App::GetApplication().closeDocument(name.c_str());
}

TEST_F(UserParameters, refusedParameterLeavesNoHolder)
{
    const std::string name = App::GetApplication().getUniqueDocumentName("userparamsrefused");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    App::DocumentObject* typed = fresh->addObject("App::VarSet", "Typed");

    // The name, the value and the expression are refused at different steps of the creation
    EXPECT_THROW(UP::createParameter(typed, "Label", parse(typed, "1 mm")), Base::Exception);
    EXPECT_THROW(UP::createParameter(typed, "mm", parse(typed, "1 mm")), Base::Exception);
    EXPECT_THROW(UP::createParameter(typed, "x", parse(typed, "missing + 1")), Base::Exception);
    EXPECT_EQ(UP::findHolder(fresh), nullptr);
    EXPECT_EQ(fresh->getObjects().size(), 1U);

    // An object of another kind has the name of the holder
    const std::string taken = App::GetApplication().getUniqueDocumentName("userparamstaken");
    App::Document* other = App::GetApplication().newDocument(taken.c_str(), "testUser");
    App::DocumentObject* feature = other->addObject("App::FeaturePython", UP::HolderName);
    EXPECT_EQ(UP::findHolder(other), nullptr);
    EXPECT_THROW(UP::holder(other), Base::RuntimeError);
    EXPECT_THROW(UP::createParameter(feature, "x", parse(feature, "1 mm")), Base::RuntimeError);
    EXPECT_EQ(other->getObjects().size(), 1U);

    App::GetApplication().closeDocument(taken.c_str());
    App::GetApplication().closeDocument(name.c_str());
}

TEST_F(UserParameters, valueTypedInAnObjectIsWrittenForTheHolder)
{
    // `Target` typed in Other means Other.Target; a user parameter keeps its meaning.
    static_cast<App::PropertyDistance*>(target)->setValue(8.0);
    UP::createParameter(other, "base", parse(other, "3 mm"));
    auto value = parse(other, "Target + base");
    UP::qualifyReferences(other, *value);
    App::Property* sum = UP::createParameter(other, "sum", value);
    ASSERT_EQ(sum->getContainer(), holder);
    EXPECT_EQ(other->getPropertyByName("sum"), nullptr);
    EXPECT_EQ(
        holder->getExpression(App::ObjectIdentifier(*sum)).expression->toString(),
        "Other.Target + base"
    );
    EXPECT_DOUBLE_EQ(static_cast<App::PropertyFloat*>(sum)->getValue(), 11.0);

    // The local spelling too
    App::Property* local = UP::createParameter(other, "local", parse(other, ".Target * 2"));
    EXPECT_EQ(
        holder->getExpression(App::ObjectIdentifier(*local)).expression->toString(),
        "Other.Target * 2"
    );
}

TEST_F(UserParameters, parametersOfOlderDocumentsAreStillUserParameters)
{
    // Before the holder existed, a parameter was a property of the object it was typed in.
    App::DocumentObject* old = doc()->addObject("App::VarSet", "Old");
    App::Property* legacy = old->addDynamicProperty("App::PropertyDistance", "legacy", UP::GroupName);
    static_cast<App::PropertyDistance*>(legacy)->setValue(5.0);

    EXPECT_TRUE(UP::isUserParameter(legacy));
    EXPECT_EQ(UP::findParameter(doc(), "legacy"), legacy);
    EXPECT_EQ(UP::checkName(doc(), "legacy", other), UP::NameStatus::UsedByParameter);
    EXPECT_EQ(UP::referenceTo(other, legacy)->toString(), "Old.legacy");

    auto expr = parse(other, "2 * legacy");
    EXPECT_EQ(UP::qualifyReferences(other, *expr), 1);
    EXPECT_EQ(expr->toString(), "2 * Old.legacy");

    EXPECT_TRUE(UP::rename(legacy, "renamed"));
    EXPECT_EQ(old->getPropertyByName("renamed"), legacy);
    // A new parameter is not added to that object
    App::Property* fresh = UP::createParameter(old, "fresh", parse(old, "1 mm"));
    EXPECT_EQ(fresh->getContainer(), holder);
}

namespace
{
// An object with a length bound to the user parameter `name` of its document
App::DocumentObject* addUser(App::Document* doc, const char* objName, const char* name)
{
    App::DocumentObject* user = doc->addObject("App::VarSet", objName);
    App::Property* length = user->addDynamicProperty("App::PropertyDistance", "L", "Base");
    user->setExpression(
        App::ObjectIdentifier(*length),
        UP::referenceTo(user, UP::findParameter(doc, name))
    );
    return user;
}

std::string boundTo(const App::DocumentObject* user)
{
    const auto expressions = user->ExpressionEngine.getExpressions();
    return expressions.empty() ? std::string() : expressions.begin()->second->toString();
}

// What Copy exports for obj (the holder is a dependency), pasted into doc
std::vector<App::DocumentObject*> copyTo(App::Document* doc, App::DocumentObject* obj)
{
    return doc->copyObject(
        App::Document::getDependencyList({obj}, App::Document::DepSort),
        false,
        true
    );
}

double valueOf(const App::Document* doc, const char* name)
{
    auto* prop = static_cast<App::PropertyFloat*>(UP::findParameter(doc, name));
    return prop ? prop->getValue() : -1.0;
}
}  // namespace

TEST_F(UserParameters, pastedInTheSameDocumentUsesItsParameters)
{
    UP::createParameter(other, "width", parse(other, "10 mm"));
    UP::createParameter(other, "unused", parse(other, "3 mm"));
    App::DocumentObject* user = addUser(doc(), "User", "width");
    ASSERT_EQ(boundTo(user), "UserParameters.width");
    const std::size_t parameters = UP::getParameters(doc()).size();

    auto pasted = copyTo(doc(), user);
    ASSERT_EQ(pasted.size(), 2U);  // a copy of the holder and of the user
    EXPECT_TRUE(UP::pastedConflicts(pasted).empty());
    UP::mergePasted(pasted);

    ASSERT_EQ(pasted.size(), 1U);
    EXPECT_NE(pasted.front(), user);
    EXPECT_EQ(boundTo(pasted.front()), "UserParameters.width");
    EXPECT_EQ(doc()->getObject("UserParameters001"), nullptr);
    EXPECT_EQ(UP::getParameters(doc()).size(), parameters);
    EXPECT_EQ(UP::findHolder(doc()), holder);

    // Also when the value changed since the copy was made: it is the same parameter
    static_cast<App::PropertyFloat*>(UP::findParameter(doc(), "width"))->setValue(12.0);
    pasted = copyTo(doc(), user);
    static_cast<App::PropertyFloat*>(holder->getPropertyByName("width"))->setValue(15.0);
    UP::mergePasted(pasted);
    EXPECT_EQ(boundTo(pasted.front()), "UserParameters.width");
    EXPECT_DOUBLE_EQ(valueOf(doc(), "width"), 15.0);
}

TEST_F(UserParameters, pastedInADocumentWithoutParametersBringsTheUsedOnes)
{
    UP::createParameter(other, "width", parse(other, "10 mm"));
    UP::createParameter(holder, "twice", parse(holder, "2 * width"));
    UP::createParameter(other, "unused", parse(other, "3 mm"));
    App::DocumentObject* user = addUser(doc(), "User", "twice");

    const std::string name = App::GetApplication().getUniqueDocumentName("userparamspaste");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    auto pasted = copyTo(fresh, user);
    EXPECT_TRUE(UP::pastedConflicts(pasted).empty());
    UP::mergePasted(pasted);

    ASSERT_EQ(pasted.size(), 1U);
    App::DocumentObject* created = UP::findHolder(fresh);
    ASSERT_NE(created, nullptr);
    EXPECT_EQ(fresh->getObjects().size(), 2U);
    EXPECT_EQ(boundTo(pasted.front()), "UserParameters.twice");
    // `twice` is computed from `width`, which comes along; `unused` does not
    EXPECT_EQ(UP::getParameters(fresh).size(), 2U);
    EXPECT_NE(UP::findParameter(fresh, "width"), nullptr);
    EXPECT_EQ(UP::findParameter(fresh, "unused"), nullptr);
    fresh->recompute();
    EXPECT_DOUBLE_EQ(valueOf(fresh, "twice"), 20.0);

    App::GetApplication().closeDocument(name.c_str());
}

TEST_F(UserParameters, pastedInADocumentWithParametersAddsTheMissingOnes)
{
    UP::createParameter(other, "width", parse(other, "10 mm"));
    UP::createParameter(holder, "twice", parse(holder, "2 * width"));
    App::DocumentObject* user = addUser(doc(), "User", "twice");

    const std::string name = App::GetApplication().getUniqueDocumentName("userparamspaste");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    App::DocumentObject* typed = fresh->addObject("App::VarSet", "Typed");
    UP::createParameter(typed, "width", parse(typed, "10 mm"));
    UP::createParameter(typed, "depth", parse(typed, "7 mm"));
    App::DocumentObject* existing = UP::findHolder(fresh);

    auto pasted = copyTo(fresh, user);
    // Same name and value: it is used as it is
    EXPECT_TRUE(UP::pastedConflicts(pasted).empty());
    UP::mergePasted(pasted);

    ASSERT_EQ(pasted.size(), 1U);
    EXPECT_EQ(UP::findHolder(fresh), existing);
    EXPECT_EQ(fresh->getObject("UserParameters001"), nullptr);
    EXPECT_EQ(boundTo(pasted.front()), "UserParameters.twice");
    EXPECT_EQ(UP::getParameters(fresh).size(), 3U);
    App::Property* twice = UP::findParameter(fresh, "twice");
    ASSERT_NE(twice, nullptr);
    EXPECT_EQ(twice->getContainer(), existing);
    // `twice` follows the width of this document
    static_cast<App::PropertyFloat*>(UP::findParameter(fresh, "width"))->setValue(4.0);
    fresh->recompute();
    EXPECT_DOUBLE_EQ(valueOf(fresh, "twice"), 8.0);

    App::GetApplication().closeDocument(name.c_str());
}

TEST_F(UserParameters, pastedParameterThatExistsWithAnotherValueIsAConflict)
{
    UP::createParameter(other, "width", parse(other, "10 mm"));
    UP::createParameter(holder, "twice", parse(holder, "2 * width"));
    App::DocumentObject* user = addUser(doc(), "User", "twice");

    const std::string name = App::GetApplication().getUniqueDocumentName("userparamspaste");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    App::DocumentObject* typed = fresh->addObject("App::VarSet", "Typed");
    UP::createParameter(typed, "width", parse(typed, "25 mm"));

    // The values of the document
    auto pasted = copyTo(fresh, user);
    auto conflicts = UP::pastedConflicts(pasted);
    ASSERT_EQ(conflicts.size(), 1U);
    EXPECT_EQ(conflicts.front().name, "width");
    EXPECT_NE(conflicts.front().existing, conflicts.front().pasted);
    UP::mergePasted(pasted, UP::PastePolicy::UseExisting);
    ASSERT_EQ(pasted.size(), 1U);
    fresh->recompute();
    EXPECT_DOUBLE_EQ(valueOf(fresh, "width"), 25.0);
    EXPECT_DOUBLE_EQ(valueOf(fresh, "twice"), 50.0);
    EXPECT_EQ(UP::getParameters(fresh).size(), 2U);
    EXPECT_EQ(fresh->getObject("UserParameters001"), nullptr);

    // The pasted values, under a new name
    App::DocumentObject* direct = addUser(doc(), "Direct", "width");
    pasted = copyTo(fresh, direct);
    ASSERT_EQ(UP::pastedConflicts(pasted).size(), 1U);
    UP::mergePasted(pasted, UP::PastePolicy::KeepPasted);
    ASSERT_EQ(pasted.size(), 1U);
    EXPECT_EQ(boundTo(pasted.front()), "UserParameters.width_2");
    fresh->recompute();
    EXPECT_DOUBLE_EQ(valueOf(fresh, "width"), 25.0);
    EXPECT_DOUBLE_EQ(valueOf(fresh, "width_2"), 10.0);
    EXPECT_EQ(fresh->getObject("UserParameters001"), nullptr);

    App::GetApplication().closeDocument(name.c_str());
}

TEST_F(UserParameters, holderPastedAloneBringsAllItsParameters)
{
    UP::createParameter(other, "width", parse(other, "10 mm"));
    UP::createParameter(other, "height", parse(other, "3 mm"));

    const std::string name = App::GetApplication().getUniqueDocumentName("userparamspaste");
    App::Document* fresh = App::GetApplication().newDocument(name.c_str(), "testUser");
    App::DocumentObject* typed = fresh->addObject("App::VarSet", "Typed");
    UP::createParameter(typed, "depth", parse(typed, "7 mm"));

    auto pasted = fresh->copyObject({holder}, false, true);
    UP::mergePasted(pasted);
    EXPECT_TRUE(pasted.empty());
    EXPECT_EQ(UP::getParameters(fresh).size(), 3U);
    EXPECT_EQ(fresh->getObjects().size(), 2U);

    App::GetApplication().closeDocument(name.c_str());
}

// NOLINTEND(readability-magic-numbers)
