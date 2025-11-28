import json
import os
import platform
import sys
import freecad
import FreeCAD as App
from addonmanager_installer import AddonInstaller
import Addon

conda_env=os.path.join(os.getcwd(),sys.argv[1])
if platform.system() != 'Windows':
    modspath = os.path.join(conda_env,'Mod')
    prefpackspath = os.path.join(conda_env,'share','Gui','PreferencePacks')
else:
    modspath = os.path.join(conda_env,'Library','Mod')
    prefpackspath = os.path.join(conda_env,'Library','data','Gui','PreferencePacks')

params = App.ParamGet("User parameter:BaseApp/Preferences/Addons")
params.SetBool('disableGit', True)

def install_mod(name,url,branch,installation_path = modspath):
    installer = AddonInstaller(Addon.Addon(name,url,branch=branch))
    installer.installation_path = installation_path
    installer.run()

install_mod("sheetmetal", "https://github.com/shaise/FreeCAD_SheetMetal", "master")

#for mod in mods["preferencePacks"]:
#    install_mod(mod["name"],mod["url"],mod['branch'],prefpackspath)