@echo off
echo Starting copy all demos to UISuite_SB...

:: Remove Directory that are not needed in UISuite
echo Removing Directory from UISuite...
if exist "scheduler" rmdir "scheduler" /s /q
if exist "kanban" rmdir "kanban" /s /q
if exist "SB" rmdir "SB" /s /q


echo Renaming folder...
ren "UIKeySampleBrowser" "SB"


@echo off
setlocal
echo Process completed successfully!
(goto) 2>nul & del "%~f0"