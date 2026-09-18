@echo off
chcp 65001 >nul
rem Сборка «Календаря дней» под Windows прямо на своём компьютере.
rem Нужен установленный Python 3.10 или новее (галочка "Add Python to PATH").
rem Результат появится в папке dist\KalendarDney — её целиком можно переносить
rem на другой компьютер, Python там уже не понадобится.

cd /d "%~dp0"

echo Шаг 1 из 4: ставлю библиотеки...
python -m pip install --user --upgrade pip
python -m pip install --user -r requirements.txt
if errorlevel 1 goto error

echo Шаг 2 из 4: ставлю сборщик...
python -m pip install --user pyinstaller
if errorlevel 1 goto error

echo Шаг 3 из 4: проверяю, что всё работает...
set QT_QPA_PLATFORM=offscreen
python smoke_test.py
if errorlevel 1 goto error
set QT_QPA_PLATFORM=

echo Шаг 4 из 4: собираю приложение...
python -m PyInstaller --noconfirm --clean cyclease.spec
if errorlevel 1 goto error

echo.
echo Готово. Приложение лежит в папке dist\KalendarDney
echo Запускать файл KalendarDney.exe
pause
exit /b 0

:error
echo.
echo Не получилось. Скорее всего не установлен Python — скачайте его
echo с сайта python.org и при установке отметьте галочку "Add Python to PATH".
pause
exit /b 1
