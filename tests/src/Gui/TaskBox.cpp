// SPDX-License-Identifier: LGPL-2.1-or-later

#include <QTest>
#include <QVBoxLayout>

#include "Gui/TaskView/TaskView.h"
#include <src/App/InitApplication.h>

// NOLINTBEGIN(readability-magic-numbers)

class testTaskBox: public QObject
{
    Q_OBJECT

public:
    testTaskBox()
    {
        tests::initApplication();
    }

private Q_SLOTS:
    void test_FollowsContentsAfterFoldAndUnfold()  // NOLINT
    {
        // A task box must keep following the size of its contents after the user folded and
        // unfolded it. See https://github.com/AstoCAD/FreeCAD/issues/166
        QWidget panel;
        auto* panelLayout = new QVBoxLayout(&panel);
        auto* box = new Gui::TaskView::TaskBox(QStringLiteral("Box"), true, &panel);
        panelLayout->addWidget(box);
        auto* content = new QWidget();
        content->setMinimumHeight(200);
        box->groupLayout()->addWidget(content);
        panel.show();
        QVERIFY(QTest::qWaitForWindowExposed(&panel));

        box->showHide();  // fold
        QTRY_VERIFY(box->maximumHeight() < 200);
        box->showHide();  // unfold
        QTRY_COMPARE(box->maximumHeight(), QWIDGETSIZE_MAX);

        // the contents grow, as when the settings of a sketch layer are shown
        content->setMinimumHeight(600);
        QTRY_VERIFY(panelLayout->minimumSize().height() >= 600);
        QTRY_VERIFY(box->height() >= 600);

        // and shrink again
        content->setMinimumHeight(200);
        QTRY_VERIFY(panelLayout->minimumSize().height() < 600);
    }
};

// NOLINTEND(readability-magic-numbers)

QTEST_MAIN(testTaskBox)

#include "TaskBox.moc"
