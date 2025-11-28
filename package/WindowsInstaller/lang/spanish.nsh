/*
AstoCAD Installer Language File
Language: Spanish
*/

!insertmacro LANGFILE_EXT "Spanish"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Instalado para el actual usuario)"

${LangFileString} TEXT_WELCOME "Este programa instalará AstoCAD en su ordenador.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compilando guiones Python..."

${LangFileString} TEXT_FINISH_DESKTOP "Crear acceso directo en el escritorio"
${LangFileString} TEXT_FINISH_WEBSITE "Visite AstoCAD.com para últimas noticias, ayuda y consejos"

#${LangFileString} FileTypeTitle "Documento AstoCAD"

#${LangFileString} SecAllUsersTitle "Instalar para todos los usuarios"
${LangFileString} SecFileAssocTitle "Asociar ficheros"
${LangFileString} SecDesktopTitle "Icono de escritorio"

${LangFileString} SecCoreDescription "Los ficheros de AstoCAD."
#${LangFileString} SecAllUsersDescription "Instalar AstoCAD para todos los usuarios o sólo para el usuario actual."
${LangFileString} SecFileAssocDescription "Asociar la extensión .FCStd con AstoCAD."
${LangFileString} SecDesktopDescription "Crear un icono de AstoCAD en el escritorio."
#${LangFileString} SecDictionaries "Diccionarios"
#${LangFileString} SecDictionariesDescription "Diccionarios de revisión ortográfica que se pueden descargar e instalar."

#${LangFileString} PathName 'Ruta al fichero $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Imposible encontrar $\"xxx.exe$\".'

#${LangFileString} DictionariesFailed 'La descarga del diccionario para el idioma $\"$R3$\" ha fallado.'

#${LangFileString} ConfigInfo "La siguiente configuración de AstoCAD va a tardar un poco."

#${LangFileString} RunConfigureFailed "Error al intentar ejecutar el programa de configuración"
${LangFileString} InstallRunning "El instalador ya está siendo ejecutado!"
${LangFileString} AlreadyInstalled "¡AstoCAD ${APP_SERIES_KEY2} ya está instalado!$\r$\n\
				Se recomienda no instalar sobre una instalación existente$\r$\n\
				si la versión instalada es de prueba o da problemas.$\r$\n\
				En estos casos es mejor reinstalar AstoCAD.$\r$\n\
				Aún así, ¿quiere instalar AstoCAD sobre la versión existente?"
${LangFileString} NewerInstalled "Está tratando de instalar una versión de AstoCAD más antigua que la que tiene instalada.$\r$\n\
				  Si realmente lo desea, debe desinstalar antes la versión de AstoCAD instalada $OldVersionNumber."

#${LangFileString} FinishPageMessage "¡Enhorabuena! AstoCAD ha sido instalado con éxito.$\r$\n\
#					$\r$\n\
#					(El primer arranque de AstoCAD puede tardar algunos segundos.)"
${LangFileString} FinishPageRun "Ejecutar AstoCAD"

${LangFileString} UnNotInRegistryLabel "Imposible encontrar AstoCAD en el registro.$\r$\n\
					Los accesos rápidos del escritorio y del Menú de Inicio no serán eliminados."
${LangFileString} UnInstallRunning "Antes cierre AstoCAD!"
${LangFileString} UnNotAdminLabel "Necesita privilegios de administrador para desinstalar AstoCAD!"
${LangFileString} UnReallyRemoveLabel "¿Está seguro de que desea eliminar completamente AstoCAD y todos sus componentes?"
${LangFileString} UnAstoCADPreferencesTitle 'Preferencias de usuario de AstoCAD'

#${LangFileString} SecUnProgDescription "Desinstala xxx."
${LangFileString} SecUnPreferencesDescription 'Elimina las carpetas de configuración de AstoCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						de todos los usuarios.'
${LangFileString} DialogUnPreferences 'Eligió eliminar la configuración de usuario de AstoCAD.$\r$\n\
						Esto también eliminará todos los addons de AstoCAD instalados.$\r$\n\
						¿Está de acuerdo con esto?'
${LangFileString} SecUnProgramFilesDescription "Desinstala AstoCAD y todos sus componentes."
