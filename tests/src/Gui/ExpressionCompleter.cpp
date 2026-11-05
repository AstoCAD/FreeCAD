// SPDX-License-Identifier: LGPL-2.1-or-later

#include <string>

#include <QAbstractProxyModel>
#include <QStringList>
#include <QTest>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Property.h>
#include <App/PropertyUnits.h>
#include <Base/Quantity.h>
#include <Base/Unit.h>
#include <Base/UnitsApi.h>

#include "Gui/ExpressionCompleter.h"
#include <src/App/InitApplication.h>

// NOLINTBEGIN(readability-magic-numbers)

namespace
{
/// A document with a user parameter `myVar` (23 mm) on `Holder` and an expression owner `Other`.
class ScopedParameterDocument
{
public:
    ScopedParameterDocument()
        : documentName {App::GetApplication().getUniqueDocumentName("expression_completer")}
        , document {App::GetApplication().newDocument(documentName.c_str(), "testUser")}
        , holder {document->addObject("App::VarSet", "Holder")}
        , other {document->addObject("App::VarSet", "Other")}
    {
        auto* param = holder->addDynamicProperty("App::PropertyDistance", "myVar", "UserParameters");
        static_cast<App::PropertyDistance*>(param)->setValue(23.0);
        other->addDynamicProperty("App::PropertyDistance", "Target", "Base");
    }

    ~ScopedParameterDocument()
    {
        App::GetApplication().closeDocument(documentName.c_str());
    }

    ScopedParameterDocument(const ScopedParameterDocument&) = delete;
    ScopedParameterDocument& operator=(const ScopedParameterDocument&) = delete;

    std::string documentName;
    App::Document* document;
    App::DocumentObject* holder;
    App::DocumentObject* other;
};

struct Row
{
    QString display;
    QString edit;
    QString toolTip;
    QString completion;  // pathFromIndex(), the text the editor inserts
};

/// The rows offered for @p prefix typed at the end of the editor text.
QList<Row> completions(Gui::ExpressionLineEdit& edit, const QString& prefix)
{
    Gui::ExpressionCompleter* completer = edit.getCompleter();
    completer->slotUpdate(prefix, static_cast<int>(prefix.size()));
    QList<Row> rows;
    auto* model = qobject_cast<QAbstractProxyModel*>(completer->completionModel());
    if (!model) {
        return rows;
    }
    for (int row = 0; row < model->rowCount(); ++row) {
        const QModelIndex index = model->index(row, 0);
        const QModelIndex source = model->mapToSource(index);
        rows.push_back(
            {index.data(Qt::DisplayRole).toString(),
             index.data(Qt::EditRole).toString(),
             index.data(Qt::ToolTipRole).toString(),
             static_cast<QCompleter*>(completer)->pathFromIndex(source)}
        );
    }
    return rows;
}

const Row* findDisplay(const QList<Row>& rows, const QString& display)
{
    for (const auto& row : rows) {
        if (row.display == display) {
            return &row;
        }
    }
    return nullptr;
}

bool hasCompletion(const QList<Row>& rows, const QString& completion)
{
    for (const auto& row : rows) {
        if (row.completion == completion) {
            return true;
        }
    }
    return false;
}

int countBareParameterRows(const QList<Row>& rows)
{
    int count = 0;
    for (const auto& row : rows) {
        if (row.display.contains(QString::fromUtf8(" \xe2\x80\x94 "))) {
            ++count;
        }
    }
    return count;
}

QString expectedDisplay()
{
    const Base::Quantity value(23.0, Base::Unit::Length);
    return QString::fromUtf8("myVar \xe2\x80\x94 Holder.myVar = ")
        + QString::fromStdString(value.getUserString());
}
}  // namespace

class testExpressionCompleter: public QObject
{
    Q_OBJECT

public:
    testExpressionCompleter()
    {
        tests::initApplication();
    }

private Q_SLOTS:
    void initTestCase()
    {
        Base::UnitsApi::setSchema("Internal");
    }

    void test_BareUserParameterOfferedInFuzzyMode()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit;
        edit.setDocumentObject(doc.other);

        const auto rows = completions(edit, QStringLiteral("myV"));
        const Row* row = findDisplay(rows, expectedDisplay());
        QVERIFY2(row, "the bare user parameter is listed");
        QCOMPARE(row->completion, QStringLiteral("myVar"));
        QCOMPARE(row->edit, QStringLiteral("myVar"));
        QVERIFY(row->toolTip.contains(QStringLiteral("Holder.myVar")));
        // The qualified form stays available as before, after the bare name on equal score.
        QVERIFY(hasCompletion(rows, QStringLiteral("Holder.myVar")));
        int bare = -1;
        int qualified = -1;
        for (int i = 0; i < rows.size(); ++i) {
            if (rows[i].completion == QStringLiteral("myVar") && bare < 0) {
                bare = i;
            }
            if (rows[i].completion == QStringLiteral("Holder.myVar") && qualified < 0) {
                qualified = i;
            }
        }
        QVERIFY(bare >= 0 && bare < qualified);
    }

    void test_BareUserParameterOfferedInExactMatchMode()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit;
        edit.setDocumentObject(doc.other);
        edit.setExactMatch(true);

        const auto rows = completions(edit, QStringLiteral("my"));
        const Row* row = findDisplay(rows, expectedDisplay());
        QVERIFY2(row, "the bare user parameter is listed at the top level");
        QCOMPARE(row->completion, QStringLiteral("myVar"));
        QCOMPARE(row->edit, QStringLiteral("myVar"));
        QVERIFY(row->toolTip.contains(QStringLiteral("Holder.myVar")));
        QCOMPARE(countBareParameterRows(rows), 1);
    }

    void test_ExistingCompletionsUnchanged()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit;
        edit.setDocumentObject(doc.other);
        edit.setExactMatch(true);

        auto rows = completions(edit, QStringLiteral("Hol"));
        QVERIFY(hasCompletion(rows, QStringLiteral("Holder.")));
        QCOMPARE(countBareParameterRows(rows), 0);

        rows = completions(edit, QStringLiteral("Holder.my"));
        QVERIFY(hasCompletion(rows, QStringLiteral("Holder.myVar")));
        QCOMPARE(countBareParameterRows(rows), 0);

        rows = completions(edit, QStringLiteral("Targ"));
        QVERIFY(hasCompletion(rows, QStringLiteral("Target")));
        QCOMPARE(countBareParameterRows(rows), 0);
    }

    void test_OwnParameterNotDuplicated()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit;
        edit.setDocumentObject(doc.holder);

        const auto rows = completions(edit, QStringLiteral("myV"));
        QVERIFY(hasCompletion(rows, QStringLiteral("myVar")));
        QCOMPARE(countBareParameterRows(rows), 0);
    }

    void test_ShadowedOrAmbiguousNameNotOffered()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit;
        edit.setDocumentObject(doc.other);

        // The owner's own property wins over the parameter: `myVar` means Other.myVar there.
        auto* own = doc.other->addDynamicProperty("App::PropertyDistance", "myVar", "Base");
        QCOMPARE(countBareParameterRows(completions(edit, QStringLiteral("myV"))), 0);
        doc.other->removeDynamicProperty(own->getName());
        QCOMPARE(countBareParameterRows(completions(edit, QStringLiteral("myV"))), 1);

        // Two parameters with the same name: the bare name refers to neither.
        auto* copy = doc.document->addObject("App::VarSet", "Copy");
        copy->addDynamicProperty("App::PropertyDistance", "myVar", "UserParameters");
        QCOMPARE(countBareParameterRows(completions(edit, QStringLiteral("myV"))), 0);
    }

    void test_UserParametersCanBeDisabled()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit before;
        before.setUserParameters(false);  // before the completer exists
        before.setDocumentObject(doc.other);
        auto rows = completions(before, QStringLiteral("myV"));
        QCOMPARE(countBareParameterRows(rows), 0);
        QVERIFY(hasCompletion(rows, QStringLiteral("Holder.myVar")));

        Gui::ExpressionLineEdit after;
        after.setDocumentObject(doc.other);
        QCOMPARE(countBareParameterRows(completions(after, QStringLiteral("myV"))), 1);
        after.setUserParameters(false);  // on an existing completer
        QCOMPARE(countBareParameterRows(completions(after, QStringLiteral("myV"))), 0);
        after.setUserParameters(true);
        QCOMPARE(countBareParameterRows(completions(after, QStringLiteral("myV"))), 1);
    }

    void test_NoPropertyCompleterUnchanged()  // NOLINT
    {
        ScopedParameterDocument doc;
        Gui::ExpressionLineEdit edit(nullptr, true);
        edit.setDocumentObject(doc.other);

        QCOMPARE(countBareParameterRows(completions(edit, QStringLiteral("myV"))), 0);
    }
};

// NOLINTEND(readability-magic-numbers)

QTEST_MAIN(testExpressionCompleter)

#include "ExpressionCompleter.moc"
