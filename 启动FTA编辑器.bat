@echo off
chcp 65001 >nul
title FTA/ETA Editor (中文版)
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    set "PY=C:\Users\Huawei\AppData\Local\Programs\Python\Python311\python.exe"
)
start "" "%PY%" src\FTA_Editor_UI.py
