// SPDX-License-Identifier: LGPL-2.1-or-later

#include <array>

#include <QColor>
#include <QImage>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLFramebufferObject>
#include <QOpenGLFunctions>
#include <QOpenGLWidget>
#include <QPoint>
#include <QRect>
#include <QSurfaceFormat>
#include <QTest>

#include <Inventor/SoDB.h>

#include <Gui/GLPainter.h>

namespace
{
struct ColoredPixels
{
    QRect bounds;
    int count {0};
};

ColoredPixels findColor(const QImage& image, const QColor& wanted)
{
    ColoredPixels result;
    for (int y = 0; y < image.height(); ++y) {
        for (int x = 0; x < image.width(); ++x) {
            const QColor actual = image.pixelColor(x, y);
            if (actual.alpha() >= 220 && qAbs(actual.red() - wanted.red()) <= 35
                && qAbs(actual.green() - wanted.green()) <= 35
                && qAbs(actual.blue() - wanted.blue()) <= 35) {
                result.bounds = result.bounds.united(QRect(x, y, 1, 1));
                ++result.count;
            }
        }
    }
    return result;
}

bool boundsMatch(const QRect& actual, const QRect& expected)
{
    // Independent of camera internals: allow only rasterization at pixel edges.
    constexpr int tolerance = 2;
    return !actual.isEmpty() && qAbs(actual.left() - expected.left()) <= tolerance
        && qAbs(actual.right() - expected.right()) <= tolerance
        && qAbs(actual.top() - expected.top()) <= tolerance
        && qAbs(actual.bottom() - expected.bottom()) <= tolerance;
}
}  // namespace

class GLPainterProjectionTest: public QObject
{
    Q_OBJECT

private:
    QOpenGLContext context;
    QOffscreenSurface surface;
    QOpenGLFunctions* functions {nullptr};

private Q_SLOTS:
    void initTestCase()
    {
        SoDB::init();
        QSurfaceFormat format;
        format.setRenderableType(QSurfaceFormat::OpenGL);
        format.setVersion(2, 1);
        format.setProfile(QSurfaceFormat::NoProfile);
        format.setDepthBufferSize(24);
        format.setStencilBufferSize(8);
        format.setSamples(0);
        context.setFormat(format);
        QVERIFY2(context.create(), "A desktop OpenGL context is required for the actual Coin renderer");
        QVERIFY2(!context.isOpenGLES(), "The Coin drawing path requires desktop OpenGL");
        QVERIFY2(context.format().profile() != QSurfaceFormat::CoreProfile,
                 "The Coin drawing path requires a compatibility OpenGL context");
        surface.setFormat(context.format());
        surface.create();
        QVERIFY2(surface.isValid(), "An actual offscreen OpenGL surface is required");
        QVERIFY(context.makeCurrent(&surface));
        functions = context.functions();
        QVERIFY(functions);
        functions->initializeOpenGLFunctions();
    }

    void publicDrawingUsesRequestedPixels_data()
    {
        QTest::addColumn<QSize>("logicalSize");
        QTest::addColumn<int>("primitive");
        for (int primitive = 0; primitive < 3; ++primitive) {
            const char* names[] = {"rectangle", "point", "line"};
            QTest::newRow(qPrintable(QString("portrait-%1").arg(names[primitive])))
                << QSize(160, 360) << primitive;
            QTest::newRow(qPrintable(QString("square-%1").arg(names[primitive])))
                << QSize(240, 240) << primitive;
            QTest::newRow(qPrintable(QString("landscape-%1").arg(names[primitive])))
                << QSize(360, 160) << primitive;
        }
    }

    void publicDrawingUsesRequestedPixels()
    {
        QFETCH(QSize, logicalSize);
        QFETCH(int, primitive);
        QVERIFY(context.makeCurrent(&surface));

        // The unshown device supplies public pixel dimensions only. It has no
        // initialized widget context, so begin() must preserve this actual FBO.
        QOpenGLWidget device;
        device.resize(logicalSize);
        QVERIFY(!device.isVisible());
        QVERIFY2(!device.isValid(), "The drawing device must remain uninitialized");
        const qreal dpr = device.devicePixelRatioF();
        const QSize pixels(static_cast<int>(device.width() * dpr),
                           static_cast<int>(device.height() * dpr));
        QVERIFY(pixels.width() >= 100 && pixels.height() >= 100);

        QOpenGLFramebufferObjectFormat framebufferFormat;
        framebufferFormat.setAttachment(QOpenGLFramebufferObject::CombinedDepthStencil);
        framebufferFormat.setSamples(0);
        QOpenGLFramebufferObject framebuffer(pixels, framebufferFormat);
        QVERIFY2(framebuffer.isValid(), "The native backend must provide a real framebuffer");
        QVERIFY(framebuffer.bind());
        functions->glViewport(0, 0, pixels.width(), pixels.height());
        functions->glClearColor(0.0F, 0.0F, 0.0F, 1.0F);
        functions->glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
        GLint beforeFramebuffer = 0;
        functions->glGetIntegerv(GL_FRAMEBUFFER_BINDING, &beforeFramebuffer);
        QCOMPARE(beforeFramebuffer, static_cast<GLint>(framebuffer.handle()));

        Gui::GLPainter painter;
        QVERIFY(painter.begin(&device));
        QVERIFY(painter.isActive());
        QVERIFY(!device.isValid());
        QCOMPARE(QOpenGLContext::currentContext(), &context);
        QCOMPARE(context.surface(), &surface);
        GLint afterBeginFramebuffer = 0;
        functions->glGetIntegerv(GL_FRAMEBUFFER_BINDING, &afterBeginFramebuffer);
        QCOMPARE(afterBeginFramebuffer, beforeFramebuffer);
        painter.setLineWidth(1.0F);
        painter.setPointSize(5.0F);

        constexpr int margin = 18;
        constexpr int extentX = 18;
        constexpr int extentY = 14;
        const std::array<QPoint, 4> corners {
            QPoint(margin, margin),
            QPoint(pixels.width() - margin - extentX, margin),
            QPoint(margin, pixels.height() - margin - extentY),
            QPoint(pixels.width() - margin - extentX, pixels.height() - margin - extentY),
        };
        const std::array<QColor, 4> colors {
            QColor(Qt::red), QColor(Qt::green), QColor(Qt::blue), QColor(Qt::yellow),
        };
        std::array<QRect, 4> expected;
        for (std::size_t i = 0; i < corners.size(); ++i) {
            const QPoint first = corners[i];
            const QPoint last = first + QPoint(extentX, extentY);
            painter.setColor(colors[i].redF(), colors[i].greenF(), colors[i].blueF(), 1.0F);
            if (primitive == 0) {
                // GLPainter takes two opposite corners, not width and height.
                painter.drawRect(first.x(), first.y(), last.x(), last.y());
                expected[i] = QRect(first, last);
            }
            else if (primitive == 1) {
                const QPoint center = first + QPoint(extentX / 2, extentY / 2);
                painter.drawPoint(center.x(), center.y());
                expected[i] = QRect(center - QPoint(2, 2), QSize(5, 5));
            }
            else {
                painter.drawLine(first.x(), first.y(), last.x(), last.y());
                expected[i] = QRect(first, last);
            }
            QCOMPARE(QOpenGLContext::currentContext(), &context);
            GLint currentFramebuffer = 0;
            functions->glGetIntegerv(GL_FRAMEBUFFER_BINDING, &currentFramebuffer);
            QCOMPARE(currentFramebuffer, beforeFramebuffer);
        }
        QVERIFY(painter.end());
        QVERIFY(!painter.isActive());
        functions->glFinish();
        QCOMPARE(functions->glGetError(), static_cast<GLenum>(GL_NO_ERROR));
        const QImage image = framebuffer.toImage(true);
        QVERIFY(!image.isNull());
        QCOMPARE(image.size(), pixels);
        QCOMPARE(QOpenGLContext::currentContext(), &context);
        QVERIFY(!device.isValid());

        bool allNonblank = true;
        bool allBoundsMatch = true;
        const int minimumPixels = primitive == 0 ? 20 : primitive == 1 ? 9 : 5;
        for (std::size_t i = 0; i < colors.size(); ++i) {
            const ColoredPixels actual = findColor(image, colors[i]);
            qInfo() << "GLPainter pixels" << pixels << "primitive" << primitive
                    << "corner" << i << "count" << actual.count
                    << "actual" << actual.bounds << "requested" << expected[i];
            allNonblank = allNonblank && actual.count >= minimumPixels;
            allBoundsMatch = allBoundsMatch && boundsMatch(actual.bounds, expected[i]);
        }
        QVERIFY2(allNonblank, "Every corner must contain actual opaque colored rendered pixels");
        QVERIFY2(allBoundsMatch, "Rendered pixel bounds must match every requested corner");
    }

    void cleanupTestCase()
    {
        context.doneCurrent();
    }
};

QTEST_MAIN(GLPainterProjectionTest)

#include "GLPainterProjection.moc"
