/*
AstoCAD Installer Language File
Language: Portuguese
*/

!insertmacro LANGFILE_EXT "Portuguese"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Instalado para o Utilizador Atual)"

${LangFileString} TEXT_WELCOME "Este assistente de instalação irá guiá-lo através da instalação do AstoCAD.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compilando os scripts de Python..."

${LangFileString} TEXT_FINISH_DESKTOP "Criar um atalho no ambiente de trabalho"
${LangFileString} TEXT_FINISH_WEBSITE "Visite AstoCAD.com para as últimas notícias, suporte e dicas"

#${LangFileString} FileTypeTitle "Documento AstoCAD"

#${LangFileString} SecAllUsersTitle "Instalar para todos os utilizadores?"
${LangFileString} SecFileAssocTitle "Associação dos ficheiros"
${LangFileString} SecDesktopTitle "Icone do ambiente de trabalho"

${LangFileString} SecCoreDescription "Os ficheiros AstoCAD."
#${LangFileString} SecAllUsersDescription "Instalar o AstoCAD para todos os utilizadores ou apenas para o presente utilizador."
${LangFileString} SecFileAssocDescription "Os ficheiros com a extensão .FCStd irão abrir automaticamente no AstoCAD."
${LangFileString} SecDesktopDescription "Um icone do AstoCAD no ambiente de trabalho."
#${LangFileString} SecDictionaries "Dicionários"
#${LangFileString} SecDictionariesDescription "Dicionários do corretor ortográfico que podem ser descarregados e instalados."

#${LangFileString} PathName 'Caminho ao ficheiro $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'O ficheiro $\"xxx.exe$\" não está no caminho especificado.'

#${LangFileString} DictionariesFailed 'Falha ao descarregar o dicionário para o idioma $\"$R3$\".'

#${LangFileString} ConfigInfo "A configuração seguinte do AstoCAD irá demorar um bocado."

#${LangFileString} RunConfigureFailed "Não foi possível executar o script de configuração"
${LangFileString} InstallRunning "O instalador já está a correr!"
${LangFileString} AlreadyInstalled "O AstoCAD ${APP_SERIES_KEY2} já está instalado!$\r$\n\
				Não é recomendado instalar sobre uma instalação já existente se a versão instalada$\r$\n\
				é uma versão de teste ou se tiver problemas com a instalação atual.$\r$\n\
				Nestes casos é melhor reinstalar o AstoCAD$\r$\n\
				Quer continuar na mesma a instalar o AstoCAD sobre a versão existente?"
${LangFileString} NewerInstalled "Está a tentar instalar uma versão mais antiga do que a que tem instalada.$\r$\n\
				  Se realmente quer fazer isto deve antes desinstalar o AstoCAD $OldVersionNumber."

#${LangFileString} FinishPageMessage "Parabéns! O AstoCAD foi instalado com sucesso.$\r$\n\
#					$\r$\n\
#					(O primeiro início do AstoCAD pode levar alguns segundos.)"
${LangFileString} FinishPageRun "Lançar o AstoCAD"

${LangFileString} UnNotInRegistryLabel "Incapaz de encontrar o AstoCAD no registry.$\r$\n\
					Os atalhos para o ambiente de trabalho no menu Start não serão removidos."
${LangFileString} UnInstallRunning "Deve fechar o AstoCAD em primeiro lugar!"
${LangFileString} UnNotAdminLabel "Precisa de privilégios de administrador para desinstalar o AstoCAD!"
${LangFileString} UnReallyRemoveLabel "Tem a certeza que quer remover completamente o AstoCAD e todas as suas componentes?"
${LangFileString} UnAstoCADPreferencesTitle 'Preferências de utilizador do AstoCAD'

#${LangFileString} SecUnProgDescription "Desinstala xxx."
${LangFileString} SecUnPreferencesDescription 'Apaga as pastas de configuração do  AstoCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						de todos os utilizadores.'
${LangFileString} DialogUnPreferences 'You chose to delete the AstoCADs user configuration.$\r$\n\
						This will also delete all installed AstoCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Desinstala AstoCAD e todas as suas componentes."
