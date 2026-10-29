// SPDX-License-Identifier: LGPL-2.1-or-later
// Copyright (c) 2026 FreeCAD contributors

#include <Python.h>

#include <gtest/gtest.h>
#include <memory>
#include <string>

#include <CXX/Objects.hxx>
#include <Base/Interpreter.h>
#include <Base/PyObjectBase.h>
#include <Mod/TechDraw/App/Cosmetic.h>

#include "src/App/InitApplication.h"

namespace
{

class InvalidateTwinOnExit
{
public:
    explicit InvalidateTwinOnExit(Base::PyObjectBase* object)
        : object(object)
    {}

    ~InvalidateTwinOnExit()
    {
        // Test-only teardown: keep the unpatched baseline's owning wrapper
        // from deleting the same C++ object again during ordinary cleanup.
        object->setInvalid();
    }

    InvalidateTwinOnExit(const InvalidateTwinOnExit&) = delete;
    InvalidateTwinOnExit& operator=(const InvalidateTwinOnExit&) = delete;

private:
    Base::PyObjectBase* object;
};

class CosmeticEdgeLifetime: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
        Base::PyGILStateLocker lock;
        Base::Interpreter().runString("import TechDraw");
    }
};

TEST_F(CosmeticEdgeLifetime, ValueCopyKeepsOriginalPythonWrapperUsable)
{
    Base::PyGILStateLocker lock;
    auto original = std::make_unique<TechDraw::CosmeticEdge>(
        Base::Vector3d(-5.0, 10.0, 0.0), Base::Vector3d(5.0, 10.0, 0.0)
    );
    Py::Object wrapper(original->getPyObject(), true);
    auto* pythonObject = static_cast<Base::PyObjectBase*>(wrapper.ptr());
    // Declaration order keeps the wrapper and edge alive until invalidation,
    // including every early return caused by a fatal test assertion.
    InvalidateTwinOnExit teardown(pythonObject);

    ASSERT_TRUE(pythonObject->isValid());
    ASSERT_EQ(pythonObject->getTwinPointer(), static_cast<void*>(original.get()));
    const std::string expectedTag = original->getTagAsString();
    ASSERT_FALSE(expectedTag.empty());

    {
        // Exercise the implicit by-value C++ copy, not the pointer-copy
        // constructor or clone(), which create a separate empty Python cache.
        TechDraw::CosmeticEdge copy(*original);
        EXPECT_EQ(copy.getTagAsString(), expectedTag);
    }

    EXPECT_TRUE(pythonObject->isValid());
    EXPECT_EQ(pythonObject->getTwinPointer(), static_cast<void*>(original.get()));
    PyObject* tag = PyObject_GetAttrString(wrapper.ptr(), "Tag");
    if (!tag) {
        PyErr_Clear();
        FAIL() << "Destroying a value copy invalidated the original edge's Python Tag getter";
    }
    Py::Object tagObject(tag, true);
    ASSERT_TRUE(PyUnicode_Check(tagObject.ptr()));
    const int comparison = PyUnicode_CompareWithASCIIString(tagObject.ptr(), expectedTag.c_str());
    if (PyErr_Occurred()) {
        PyErr_Clear();
        FAIL() << "The original Python Tag getter could not return its ordinary edge tag";
    }
    EXPECT_EQ(comparison, 0);
}

}  // namespace
