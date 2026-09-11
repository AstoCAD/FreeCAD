// SPDX-License-Identifier: LGPL-2.1-or-later

#include <App/Document.h>
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/Control.h>

DEF_STD_CMD_A(CmdSurfaceGordonSurface)
CmdSurfaceGordonSurface::CmdSurfaceGordonSurface()
    : Command("Surface_GordonSurface")
{
    sAppModule = "Surface";
    sGroup = QT_TR_NOOP("Surface");
    sMenuText = QT_TR_NOOP("Gordon Surface");
    sToolTipText = QT_TR_NOOP(
        "Creates a surface through a network of intersecting profiles and guides"
    );
    sStatusTip = sToolTipText;
    sPixmap = "Surface_GordonSurface";
}
bool CmdSurfaceGordonSurface::isActive()
{
    return hasActiveDocument() && !Gui::Control().activeDialog();
}
void CmdSurfaceGordonSurface::activated(int)
{
    auto name = getUniqueObjectName("GordonSurface");
    openCommand(QT_TRANSLATE_NOOP("Command", "Create Gordon surface"));
    doCommand(Doc, "App.ActiveDocument.addObject('Surface::GordonSurface', '%s')", name.c_str());
    doCommand(Gui, "Gui.ActiveDocument.setEdit('%s')", name.c_str());
}

void CreateSurfaceGordonSurfaceCommands()
{
    Gui::Application::Instance->commandManager().addCommand(new CmdSurfaceGordonSurface);
}
