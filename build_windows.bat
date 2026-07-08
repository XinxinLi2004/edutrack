@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"
title EduFlow - 打包工具

echo ========================================
echo   EduFlow - Windows 打包
echo ========================================
echo.

:: ====== 第1步：找/装 Python ======
echo [1/4] 查找 Python...
set PYTHON_CMD=
set PYTHON_VER=

for %%C in (python python3 py) do (
    if not defined PYTHON_CMD (
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%V in ('%%C --version 2^>^&1') do set PYTHON_VER=%%V
            set PYTHON_CMD=%%C
        )
    )
)

:: PATH 里没找到，查 AppData 里的 Python 安装
if not defined PYTHON_CMD (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if not defined PYTHON_CMD (
            if exist "%%D\python.exe" (
                set "PYTHON_CMD=%%D\python.exe"
                for /f "tokens=*" %%V in ('"%%D\python.exe" --version 2^>^&1') do set PYTHON_VER=%%V
            )
        )
    )
)

:: 还是没有，尝试自动安装
if "%PYTHON_CMD%"=="" (
    echo   未找到 Python，尝试自动安装...
    echo.
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 (
        echo   安装完成，请关闭此窗口后重新双击 build_windows.bat
        echo   如果窗口自动关闭，请手动重新打开。
        pause >nul
        exit
    )
    echo.
    echo   自动安装失败。请手动安装 Python：
    echo   1. 打开浏览器访问 https://www.python.org/downloads/
    echo   2. 下载并运行安装程序
    echo   3. 务必勾选底部 "Add Python to PATH"
    echo   4. 安装完成后重新双击 build_windows.bat
    echo.
    pause >nul
    exit
)

echo   找到: !PYTHON_VER!
echo.

:: ====== 第2步：安装 PyInstaller ======
echo [2/4] 安装 PyInstaller...
!PYTHON_CMD! -m pip install pyinstaller --quiet --disable-pip-version-check
if !errorlevel! neq 0 (
    echo   安装失败，网络可能有问题，重试中...
    !PYTHON_CMD! -m pip install pyinstaller --quiet --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple
    if !errorlevel! neq 0 (
        echo.
        echo [X] PyInstaller 安装失败
        echo   请检查网络连接，或手动在 cmd 中执行：
        echo   !PYTHON_CMD! -m pip install pyinstaller
        pause >nul
        exit
    )
)
echo   完成
echo.

:: ====== 第3步：打包 ======
echo [3/4] 开始打包（约 1-2 分钟）...
if exist "dist\EduFlow.exe" del /f /q "dist\EduFlow.exe"

!PYTHON_CMD! -m PyInstaller student-system.spec --clean --noconfirm
if !errorlevel! neq 0 (
    echo.
    echo [X] 打包失败
    echo.
    echo 常见原因：
    echo   1. 杀毒软件拦截 → 临时关闭 Windows Defender 实时保护
    echo   2. 路径含中文 → 把整个文件夹放到 C:\myapp 之类不含中文的路径
    echo   3. 磁盘空间不足 → 至少需要 500MB 可用空间
    pause >nul
    exit
)
echo   完成
echo.

:: ====== 第4步：验证 ======
echo [4/4] 验证...
if exist "dist\EduFlow.exe" (
    echo.
    echo ========================================
    echo   打包成功！
    echo.
    echo   输出：dist\EduFlow.exe
    echo.
    echo   双击 EXE 即可启动（浏览器自动打开）
    echo   首次运行自动创建数据库，无需额外配置
    echo ========================================
) else (
    echo [X] 输出文件不存在，打包可能失败
)

echo.
echo 按任意键关闭...
pause >nul
