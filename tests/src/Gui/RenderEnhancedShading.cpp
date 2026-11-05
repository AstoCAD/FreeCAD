// SPDX-License-Identifier: LGPL-2.1-or-later

// Pixel tests of the optional enhanced face shading (Gui/Render/FaceShading).
// They render through View3DInventorViewer::renderSceneToImage() in an offscreen context, so they
// need OpenGL (xvfb + Mesa on Linux CI) but no FreeCAD window. Classic must stay byte identical;
// Enhanced is checked with relative luminance and exact-colour rules, not baselines.

#include <algorithm>
#include <cmath>

#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLFramebufferObject>
#include <QTest>

#include <Inventor/SoDB.h>
#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/elements/SoLazyElement.h>
#include <Inventor/elements/SoOverrideElement.h>
#include <Inventor/misc/SoState.h>
#include <Inventor/nodes/SoCallback.h>
#include <Inventor/nodes/SoClipPlane.h>
#include <Inventor/nodes/SoLightModel.h>
#include <Inventor/nodes/SoMaterial.h>
#include <Inventor/nodes/SoOrthographicCamera.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoCube.h>
#include <Inventor/nodes/SoSphere.h>
#include <Inventor/nodes/SoTranslation.h>
#include <Inventor/nodes/SoSubNode.h>

#include <Gui/Inventor/So3DAnnotation.h>
#include <Gui/Render/AmbientOcclusion.h>
#include <Gui/Render/FaceShading.h>
#include <Gui/Render/RenderSettings.h>
#include <Gui/Render/ShadowPass.h>
#include <Gui/View3DInventorViewer.h>
#include <Gui/ViewProvider.h>

using Gui::Render::Quality;
using Gui::Render::RenderSettings;

namespace
{

/// A sphere that opts in to the enhanced shading the same way SoBrepFaceSet does.
class ShadedSphere: public SoSphere
{
    SO_NODE_HEADER(ShadedSphere);

public:
    static void initClass()
    {
        SO_NODE_INIT_CLASS(ShadedSphere, SoSphere, "Sphere");
    }
    ShadedSphere()
    {
        SO_NODE_CONSTRUCTOR(ShadedSphere);
    }

    void GLRender(SoGLRenderAction* action) override
    {
        Gui::Render::FaceShadingScope shading(action);
        SoSphere::GLRender(action);
    }

protected:
    ~ShadedSphere() override = default;
};

SO_NODE_SOURCE(ShadedSphere)

/// A box that opts in to the enhanced shading.
class ShadedCube: public SoCube
{
    SO_NODE_HEADER(ShadedCube);

public:
    static void initClass()
    {
        SO_NODE_INIT_CLASS(ShadedCube, SoCube, "Cube");
    }
    ShadedCube()
    {
        SO_NODE_CONSTRUCTOR(ShadedCube);
    }

    void GLRender(SoGLRenderAction* action) override
    {
        Gui::Render::FaceShadingScope shading(action);
        SoCube::GLRender(action);
    }

protected:
    ~ShadedCube() override = default;
};

SO_NODE_SOURCE(ShadedCube)

constexpr int shadowImageSize = 128;
constexpr float shadowPixelsPerUnit = 32.0F;  // camera height 4

/// A grey plate (top at z = 0) with a sphere floating above it, seen from above. The fixed sun
/// (towards +x, +y, +z) casts the sphere's shadow towards -x, -y on the plate.
QImage renderShadowScene(bool shaded)
{
    const Gui::CoinPtr<SoSeparator> scene(new SoSeparator);
    auto* material = new SoMaterial;
    material->diffuseColor.setValue(0.8F, 0.8F, 0.8F);
    material->specularColor.setValue(0.5333F, 0.5333F, 0.5333F);
    material->shininess = 0.9F;
    scene->addChild(material);

    auto* plate = new SoSeparator;
    auto* plateOffset = new SoTranslation;
    plateOffset->translation.setValue(0.0F, 0.0F, -0.05F);
    plate->addChild(plateOffset);
    SoCube* plateShape = shaded ? new ShadedCube : new SoCube;
    plateShape->width = 4.0F;
    plateShape->height = 4.0F;
    plateShape->depth = 0.1F;
    plate->addChild(plateShape);
    scene->addChild(plate);

    auto* ball = new SoSeparator;
    auto* ballOffset = new SoTranslation;
    ballOffset->translation.setValue(0.0F, 0.0F, 1.0F);
    ball->addChild(ballOffset);
    SoSphere* sphere = shaded ? new ShadedSphere : new SoSphere;
    sphere->radius = 0.5F;
    ball->addChild(sphere);
    scene->addChild(ball);

    const Gui::CoinPtr<SoOrthographicCamera> camera(new SoOrthographicCamera);
    camera->position.setValue(0.0F, 0.0F, 5.0F);
    camera->height = 4.0F;
    camera->nearDistance = 1.0F;
    camera->farDistance = 10.0F;

    Gui::View3DInventorViewer::RenderImageOptions options;
    options.width = shadowImageSize;
    options.height = shadowImageSize;
    options.samples = 0;
    options.background = Qt::black;
    options.camera = camera;
    options.scene = scene;
    return Gui::View3DInventorViewer::renderSceneToImage(options).convertToFormat(QImage::Format_RGB32);
}

/// A plate with a low step (1 x 1 x 0.1 box) on it, seen from above: ambient occlusion darkens
/// the plate along the step.
QImage renderStepScene()
{
    const Gui::CoinPtr<SoSeparator> scene(new SoSeparator);
    auto* material = new SoMaterial;
    material->diffuseColor.setValue(0.8F, 0.8F, 0.8F);
    scene->addChild(material);
    auto* plate = new SoSeparator;
    auto* plateOffset = new SoTranslation;
    plateOffset->translation.setValue(0.0F, 0.0F, -0.05F);
    plate->addChild(plateOffset);
    auto* plateShape = new ShadedCube;
    plateShape->width = 4.0F;
    plateShape->height = 4.0F;
    plateShape->depth = 0.1F;
    plate->addChild(plateShape);
    scene->addChild(plate);
    auto* step = new SoSeparator;
    auto* stepOffset = new SoTranslation;
    stepOffset->translation.setValue(0.0F, 0.0F, 0.05F);
    step->addChild(stepOffset);
    auto* stepShape = new ShadedCube;
    stepShape->width = 1.0F;
    stepShape->height = 1.0F;
    stepShape->depth = 0.1F;
    step->addChild(stepShape);
    scene->addChild(step);

    const Gui::CoinPtr<SoOrthographicCamera> camera(new SoOrthographicCamera);
    camera->position.setValue(0.0F, 0.0F, 5.0F);
    camera->height = 4.0F;
    camera->nearDistance = 1.0F;
    camera->farDistance = 10.0F;
    Gui::View3DInventorViewer::RenderImageOptions options;
    options.width = shadowImageSize;
    options.height = shadowImageSize;
    options.samples = 0;
    options.background = Qt::black;
    options.camera = camera;
    options.scene = scene;
    return Gui::View3DInventorViewer::renderSceneToImage(options).convertToFormat(QImage::Format_RGB32);
}

QPoint shadowScenePixel(float x, float y)
{
    return {
        int(shadowImageSize / 2 + x * shadowPixelsPerUnit),
        int(shadowImageSize / 2 - y * shadowPixelsPerUnit),
    };
}

struct SceneOptions
{
    bool shaded = true;
    bool baseColor = false;
    bool emissive = false;
    bool clipRightHalf = false;
    float transparency = 0.0F;
    bool selectedWhole = false;  // emissive colour override, as SoFCSelection / SoFCSelectionRoot
};

/// Default FreeCAD selection green.
const SbColor selectionGreen(0.11F, 0.69F, 0.11F);

void setSelectionOverride(void* data, SoAction* action)
{
    if (!action->isOfType(SoGLRenderAction::getClassTypeId())) {
        return;
    }
    SoState* state = action->getState();
    SoLazyElement::setEmissive(state, &selectionGreen);
    SoOverrideElement::setEmissiveColorOverride(state, static_cast<SoNode*>(data), TRUE);
}

constexpr int imageSize = 64;
constexpr int centre = imageSize / 2;

QImage render(const SceneOptions& opts)
{
    const Gui::CoinPtr<SoSeparator> scene(new SoSeparator);
    if (opts.clipRightHalf) {
        auto* clip = new SoClipPlane;
        clip->plane.setValue(SbPlane(SbVec3f(-1.0F, 0.0F, 0.0F), 0.0F));  // keep x <= 0
        scene->addChild(clip);
    }
    if (opts.baseColor) {
        auto* lightModel = new SoLightModel;
        lightModel->model = SoLightModel::BASE_COLOR;
        scene->addChild(lightModel);
    }
    if (opts.selectedWhole) {
        auto* selection = new SoCallback;
        selection->setCallback(setSelectionOverride, selection);
        scene->addChild(selection);
    }
    auto* material = new SoMaterial;
    material->diffuseColor.setValue(0.8F, 0.8F, 0.9F);
    material->specularColor.setValue(0.5333F, 0.5333F, 0.5333F);
    material->shininess = 0.9F;
    material->transparency = opts.transparency;
    if (opts.emissive) {
        material->emissiveColor.setValue(0.0F, 0.6F, 0.0F);
    }
    scene->addChild(material);
    if (opts.shaded) {
        scene->addChild(new ShadedSphere);
    }
    else {
        scene->addChild(new SoSphere);
    }

    const Gui::CoinPtr<SoOrthographicCamera> camera(new SoOrthographicCamera);
    camera->position.setValue(0.0F, 0.0F, 5.0F);
    camera->height = 3.0F;
    camera->nearDistance = 1.0F;
    camera->farDistance = 10.0F;

    Gui::View3DInventorViewer::RenderImageOptions options;
    options.width = imageSize;
    options.height = imageSize;
    options.samples = 0;
    options.background = Qt::black;
    options.camera = camera;
    options.scene = scene;
    return Gui::View3DInventorViewer::renderSceneToImage(options).convertToFormat(QImage::Format_RGB32);
}

double luminance(const QColor& c)
{
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF();
}

/// Mean luminance of a (2 r + 1)^2 block, robust to screen-door transparency patterns.
double meanLuminance(const QImage& image, int x, int y, int r = 4)
{
    double sum = 0.0;
    int count = 0;
    for (int j = y - r; j <= y + r; ++j) {
        for (int i = x - r; i <= x + r; ++i) {
            sum += luminance(image.pixelColor(i, j));
            ++count;
        }
    }
    return sum / count;
}

}  // namespace

class RenderEnhancedShadingTest: public QObject
{
    Q_OBJECT

    QString unavailable;

    void requireEnhanced()
    {
        RenderSettings::clearSessionFallbackForTest();
        RenderSettings::setRequestedQuality(Quality::Enhanced);
        // Post passes off unless a test asks for them: the exactness checks compare silhouettes.
        RenderSettings::setFxaaEnabled(false);
        RenderSettings::setAmbientOcclusionEnabled(false);
    }

private Q_SLOTS:
    void initTestCase()
    {
        SoDB::init();
        ShadedSphere::initClass();
        ShadedCube::initClass();

        QOpenGLContext context;
        QOffscreenSurface surface;
        if (!context.create()) {
            unavailable = QStringLiteral("no OpenGL context on this platform");
            return;
        }
        surface.setFormat(context.format());
        surface.create();
        if (!context.makeCurrent(&surface)) {
            unavailable = QStringLiteral("cannot make an OpenGL context current");
            return;
        }
        unavailable = QString::fromStdString(Gui::Render::validateFaceShaderInCurrentContext());
        context.doneCurrent();
        if (RenderSettings::isForcedClassicByEnvironment()) {
            unavailable = QStringLiteral("FC_RENDER_CLASSIC is set");
        }
    }

    void cleanup()
    {
        RenderSettings::clearSessionFallbackForTest();
        RenderSettings::setRequestedQuality(Quality::Classic);
        RenderSettings::setShadowsEnabled(false);
        RenderSettings::setFxaaEnabled(true);
        RenderSettings::setAmbientOcclusionEnabled(false);
    }

    void classicIgnoresThePostPasses()
    {
        RenderSettings::setRequestedQuality(Quality::Classic);
        RenderSettings::setFxaaEnabled(false);
        RenderSettings::setAmbientOcclusionEnabled(false);
        const QImage plain = render({.baseColor = true});
        RenderSettings::setFxaaEnabled(true);
        RenderSettings::setAmbientOcclusionEnabled(true);
        QCOMPARE(render({.baseColor = true}), plain);
        QCOMPARE(renderShadowScene(true), renderShadowScene(false));
    }

    void fxaaSmoothsSilhouettesOnly()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        requireEnhanced();
        // An unlit (base colour) sphere: a hard, aliased silhouette on black.
        const QImage hard = render({.baseColor = true});
        RenderSettings::setFxaaEnabled(true);
        const QImage smooth = render({.baseColor = true});
        if (!RenderSettings::fxaaActive()) {
            QSKIP("FXAA is not supported by this OpenGL context");
        }
        auto intermediate = [](const QImage& image) {
            int count = 0;
            for (int y = 0; y < image.height(); ++y) {
                for (int x = 0; x < image.width(); ++x) {
                    const int g = qGray(image.pixel(x, y));
                    count += (g > 10 && g < 190) ? 1 : 0;
                }
            }
            return count;
        };
        QVERIFY2(
            intermediate(smooth) > intermediate(hard),
            qPrintable(QStringLiteral("edge pixels %1 -> %2").arg(intermediate(hard)).arg(intermediate(smooth)))
        );
        // Flat areas keep their exact colour (selection colours stay exact).
        QCOMPARE(smooth.pixelColor(centre, centre), hard.pixelColor(centre, centre));
        QCOMPARE(smooth.pixelColor(1, 1), hard.pixelColor(1, 1));
    }

    void ambientOcclusionDarkensCreasesOnly()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        const QPoint crease = shadowScenePixel(0.56F, 0.0F);  // plate, just outside the step
        const QPoint open = shadowScenePixel(1.6F, -1.6F);    // plate, far from anything
        requireEnhanced();
        const QImage without = renderStepScene();
        RenderSettings::setAmbientOcclusionEnabled(true);
        const QImage with = renderStepScene();
        if (RenderSettings::isAmbientOcclusionDisabledForSession()) {
            QSKIP("ambient occlusion is not supported by this OpenGL context");
        }
        const double creaseWithout = meanLuminance(without, crease.x(), crease.y(), 1);
        const double creaseWith = meanLuminance(with, crease.x(), crease.y(), 1);
        QVERIFY2(
            creaseWith < creaseWithout - 0.02,
            qPrintable(QStringLiteral("crease %1 -> %2").arg(creaseWithout).arg(creaseWith))
        );
        QVERIFY(std::abs(meanLuminance(with, open.x(), open.y(), 2) - meanLuminance(without, open.x(), open.y(), 2))
                < 0.02);
        // The background (no face) is never darkened.
        QCOMPARE(with.pixelColor(0, 0), without.pixelColor(0, 0));
    }

    void shadowsDoNotBrightenLitAreas()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        const QPoint lit = shadowScenePixel(0.7F, 0.3F);
        requireEnhanced();
        const QImage without = renderShadowScene(true);
        RenderSettings::setShadowsEnabled(true);
        const QImage with = renderShadowScene(true);
        if (RenderSettings::areShadowsDisabledForSession()) {
            QSKIP("shadows are not supported by this OpenGL context");
        }
        QVERIFY(std::abs(meanLuminance(with, lit.x(), lit.y(), 2) - meanLuminance(without, lit.x(), lit.y(), 2))
                < 0.02);
    }

    void classicIgnoresTheShadowSetting()
    {
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage plain = renderShadowScene(false);
        RenderSettings::setShadowsEnabled(true);
        QCOMPARE(renderShadowScene(true), plain);
        QCOMPARE(renderShadowScene(false), plain);
    }

    void shadowsDarkenTheShadowedSide()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        // Mirror points on the plate, both outside the sphere seen from above: (-0.7, -0.3) is in
        // the sphere's shadow, (0.7, 0.3) is not.
        const QPoint shadowed = shadowScenePixel(-0.7F, -0.3F);
        const QPoint lit = shadowScenePixel(0.7F, 0.3F);

        requireEnhanced();
        const QImage noShadows = renderShadowScene(true);
        QVERIFY(std::abs(meanLuminance(noShadows, shadowed.x(), shadowed.y(), 2)
                         - meanLuminance(noShadows, lit.x(), lit.y(), 2))
                < 0.01);

        RenderSettings::setShadowsEnabled(true);
        const QImage withShadows = renderShadowScene(true);
        if (RenderSettings::areShadowsDisabledForSession()) {
            QSKIP("shadows are not supported by this OpenGL context");
        }
        const double inShadow = meanLuminance(withShadows, shadowed.x(), shadowed.y(), 2);
        const double inLight = meanLuminance(withShadows, lit.x(), lit.y(), 2);
        QVERIFY2(
            inShadow < inLight - 0.08,
            qPrintable(QStringLiteral("shadow %1 light %2").arg(inShadow).arg(inLight))
        );
        // The shadow darkens, it does not black out (ambient and headlight remain).
        QVERIFY(inShadow > 0.15);
        // No shadow acne on the lit plate: a lit block is uniform.
        double minimum = 1.0;
        double maximum = 0.0;
        for (int dy = -3; dy <= 3; ++dy) {
            for (int dx = -3; dx <= 3; ++dx) {
                const double l = luminance(withShadows.pixelColor(lit.x() + dx, lit.y() + dy));
                minimum = std::min(minimum, l);
                maximum = std::max(maximum, l);
            }
        }
        QVERIFY2(maximum - minimum < 0.03, qPrintable(QStringLiteral("acne %1").arg(maximum - minimum)));
    }

    void classicIsUnchanged()
    {
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage plain = render({.shaded = false});
        const QImage optIn = render({.shaded = true});
        QVERIFY(!plain.isNull());
        QCOMPARE(optIn, plain);
    }

    void shaderCompilesOnThisContext()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        // initTestCase compiled and linked the face program with the real driver.
        QVERIFY(unavailable.isEmpty());
    }

    void enhancedShadesLitFaces()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage classic = render({});
        requireEnhanced();
        const QImage enhanced = render({});
        QVERIFY2(!RenderSettings::isDisabledForSession(), RenderSettings::fallbackReason().c_str());
        QVERIFY(!enhanced.isNull());
        QVERIFY(enhanced != classic);

        // The background and the silhouette are where they were.
        QCOMPARE(enhanced.pixelColor(0, 0), classic.pixelColor(0, 0));
        QCOMPARE(enhanced.pixelColor(2, centre), QColor(Qt::black));
        const QColor middle = enhanced.pixelColor(centre, centre);
        QVERIFY(middle != QColor(Qt::black));
        // Lit by the headlight: the centre faces the light and is brighter than the rim.
        const QColor rim = enhanced.pixelColor(centre + 18, centre);
        QVERIFY2(
            luminance(middle) > luminance(rim) + 0.05,
            qPrintable(QStringLiteral("centre %1 rim %2").arg(luminance(middle)).arg(luminance(rim)))
        );
        // Away from the specular highlight, a light grey-blue part stays a light grey-blue part:
        // neither burnt out nor dark, and still bluish.
        const QColor body = enhanced.pixelColor(centre - 10, centre);
        QVERIFY2(
            luminance(body) > 0.3 && luminance(body) < 0.97,
            qPrintable(QStringLiteral("body luminance %1").arg(luminance(body)))
        );
        QVERIFY(body.blue() >= body.red());
    }

    void enhancedIsDeterministicAcrossContexts()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        requireEnhanced();
        // Every renderSceneToImage() without a viewer uses a new offscreen context.
        QCOMPARE(render({}), render({}));
    }

    void enhancedKeepsUnlitColoursExact()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage classic = render({.baseColor = true});
        requireEnhanced();
        QCOMPARE(render({.baseColor = true}), classic);
    }

    void enhancedLeavesEmissiveHighlightClassic()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage classic = render({.emissive = true});
        requireEnhanced();
        QCOMPARE(render({.emissive = true}), classic);
    }

    void enhancedHonoursClipPlanes()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        requireEnhanced();
        const QImage clipped = render({.clipRightHalf = true});
        QVERIFY(clipped.pixelColor(centre - 8, centre) != QColor(Qt::black));
        QCOMPARE(clipped.pixelColor(centre + 8, centre), QColor(Qt::black));
    }

    void enhancedKeepsTransparency()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        requireEnhanced();
        const QImage opaque = render({});
        const QImage halfTransparent = render({.transparency = 0.5F});
        // Blended over a black background, the transparent sphere is darker.
        QVERIFY(
            meanLuminance(halfTransparent, centre - 8, centre)
            < meanLuminance(opaque, centre - 8, centre) - 0.1
        );
    }

    void sessionFallbackRendersClassic()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        RenderSettings::setRequestedQuality(Quality::Classic);
        const QImage classic = render({});
        requireEnhanced();
        RenderSettings::disableForSession("forced by RenderEnhancedShading test");
        QCOMPARE(render({}), classic);
    }

    void classicKeepsTheEmissiveSelection()
    {
        RenderSettings::setRequestedQuality(Quality::Classic);
        QCOMPARE(render({.shaded = true, .selectedWhole = true}), render({.shaded = false, .selectedWhole = true}));
    }

    void enhancedTintsWholeObjectSelection()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        requireEnhanced();
        const QImage plain = render({});
        const QImage selected = render({.selectedWhole = true});
        QVERIFY(selected != plain);
        // Shaded, not a flat silhouette: the rim is darker than the lit centre.
        const QColor middle = selected.pixelColor(centre, centre);
        const QColor rim = selected.pixelColor(centre + 18, centre);
        QVERIFY2(
            luminance(middle) > luminance(rim) + 0.05,
            qPrintable(QStringLiteral("centre %1 rim %2").arg(luminance(middle)).arg(luminance(rim)))
        );
        // The exact preference colour shows where the part is well lit.
        const QColor expected = QColor::fromRgbF(selectionGreen[0], selectionGreen[1], selectionGreen[2]);
        QVERIFY2(
            std::abs(middle.red() - expected.red()) <= 8 && std::abs(middle.green() - expected.green()) <= 8
                && std::abs(middle.blue() - expected.blue()) <= 8,
            qPrintable(QStringLiteral("centre %1 expected %2").arg(middle.name(), expected.name()))
        );
        // A transparent part stays transparent when selected.
        const QImage transparentSelected = render({.transparency = 0.5F, .selectedWhole = true});
        QVERIFY(
            meanLuminance(transparentSelected, centre - 8, centre)
            < meanLuminance(selected, centre - 8, centre) - 0.1
        );
    }

    void prepassesReleaseDelayedAnnotations()
    {
        if (!unavailable.isEmpty()) {
            QSKIP(qPrintable(unavailable));
        }
        if (Gui::So3DAnnotation::getClassTypeId() == SoType::badType()) {
            Gui::SoDelayedAnnotationsElement::initClass();
            Gui::So3DAnnotation::initClass();
        }
        requireEnhanced();
        RenderSettings::setShadowsEnabled(true);
        RenderSettings::setAmbientOcclusionEnabled(true);

        // A shaded plate and an annotation (like a datum plane) seen from above.
        const Gui::CoinPtr<SoSeparator> scene(new SoSeparator);
        auto* camera = new SoOrthographicCamera;
        camera->position.setValue(0.0F, 0.0F, 5.0F);
        camera->height = 4.0F;
        scene->addChild(camera);
        auto* plate = new ShadedCube;
        plate->depth = 0.1F;
        scene->addChild(plate);
        const Gui::CoinPtr<Gui::So3DAnnotation> annotation(new Gui::So3DAnnotation);
        annotation->addChild(new SoCube);
        scene->addChild(annotation);
        const int references = annotation->getRefCount();

        QOpenGLContext context;
        QOffscreenSurface surface;
        QVERIFY(context.create());
        surface.setFormat(context.format());
        surface.create();
        QVERIFY(context.makeCurrent(&surface));
        {
            QOpenGLFramebufferObject fbo(64, 64, QOpenGLFramebufferObject::Depth);
            QVERIFY(fbo.bind());
            SoGLRenderAction action(SbViewportRegion(64, 64));
            const Gui::CoinPtr<Gui::Render::SoFCShadowPass> shadows(Gui::Render::createShadowPass(scene));
            action.apply(shadows);
            const Gui::CoinPtr<Gui::Render::SoFCAmbientOcclusionPass> occlusion(
                Gui::Render::createAmbientOcclusionPass(scene)
            );
            action.apply(occlusion);
            fbo.release();
        }
        const bool ranPasses = !RenderSettings::areShadowsDisabledForSession()
            || !RenderSettings::isAmbientOcclusionDisabledForSession();
        context.doneCurrent();
        if (!ranPasses) {
            QSKIP("neither shadows nor ambient occlusion are supported by this OpenGL context");
        }
        // Each prepass used to keep a copied path to the annotation (never deleted).
        QCOMPARE(annotation->getRefCount(), references);
    }
};

QTEST_MAIN(RenderEnhancedShadingTest)

#include "RenderEnhancedShading.moc"
