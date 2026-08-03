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

:: 预设 Python 版本
set "PYTHON_VERSION=3.12.9"
set "PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe"
set PYTHON_CMD=
set PYTHON_VER=

:: --- 1a. 检查 PATH ---
for %%C in (python python3 py) do (
    if not defined PYTHON_CMD (
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%V in ('%%C --version 2^>^&1') do set PYTHON_VER=%%V
            set PYTHON_CMD=%%C
        )
    )
)

:: --- 1b. 检查 AppData ---
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

:: --- 1c. 自动安装 Python（国内镜像，多重兜底） ---
if "%PYTHON_CMD%"=="" (
    echo   未找到 Python，开始自动安装 v%PYTHON_VERSION% ...
    echo.

    :: 方案A：winget（Windows 10/11 自带，最快）
    echo   [方案A] 尝试 winget ...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 (
        echo   winget 安装完成。请重新双击 build_windows.bat 继续。
        pause >nul
        exit
    )

    echo   winget 不可用，使用镜像下载...
    echo.

    :: 下载目录
    set "DL_DIR=%TEMP%\eduflow_python"
    if not exist "!DL_DIR!" mkdir "!DL_DIR!"
    set "DL_PATH=!DL_DIR!\!PYTHON_INSTALLER!"

    :: 镜像源列表（按优先级）
    ::   M1=清华大学 TUNA（直连无重定向，最稳定）
    ::   M2=华为云（直连无重定向）
    ::   M3=阿里 npmmirror（有 302 重定向，放最后）
    set "MIRROR_COUNT=3"
    set "MIRROR1_NAME=清华大学 TUNA"
    set "MIRROR1_URL=https://mirrors.tuna.tsinghua.edu.cn/python/%PYTHON_VERSION%/!PYTHON_INSTALLER!"
    set "MIRROR2_NAME=华为云"
    set "MIRROR2_URL=https://mirrors.huaweicloud.com/python/%PYTHON_VERSION%/!PYTHON_INSTALLER!"
    set "MIRROR3_NAME=阿里 npmmirror"
    set "MIRROR3_URL=https://npmmirror.com/mirrors/python/%PYTHON_VERSION%/!PYTHON_INSTALLER!"

    :: 逐个镜像尝试：PowerShell → curl → certutil
    for /L %%M in (1,1,!MIRROR_COUNT!) do (
        if not exist "!DL_PATH!" (
            set "MNAME=!MIRROR%%M_NAME!"
            set "MURL=!MIRROR%%M_URL!"
            echo   [方案B%%M] !MNAME! ...
            echo   URL: !MURL!

            :: 方法1：PowerShell Invoke-WebRequest
            echo     尝试 PowerShell ...
            powershell -NoProfile -ExecutionPolicy Bypass -Command ^
                "$ProgressPreference='SilentlyContinue';" ^
                "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
                "try { Invoke-WebRequest -UseBasicParsing -Uri '!MURL!' -OutFile '!DL_PATH!' -ErrorAction Stop }" ^
                "catch { exit 1 }" >nul 2>&1

            :: 方法2：curl（Windows 10+ 内置）
            if not exist "!DL_PATH!" (
                echo     PowerShell 失败，尝试 curl ...
                curl -L -o "!DL_PATH!" "!MURL!" --connect-timeout 30 --max-time 300 -# 2>nul
            )

            :: 方法3：certutil（Windows 7/8 终极兜底）
            if not exist "!DL_PATH!" (
                echo     curl 失败，尝试 certutil ...
                certutil -urlcache -split -f "!MURL!" "!DL_PATH!" >nul 2>&1
            )

            if exist "!DL_PATH!" (
                echo     [!MNAME!] 下载成功
            ) else (
                echo     [!MNAME!] 下载失败，尝试下一个源...
            )
        )
    )

    :: 检查下载结果
    if not exist "!DL_PATH!" (
        echo.
        echo   ============================================
        echo   [X] 自动下载失败，请手动安装 Python：
        echo.
        echo   方案A - 浏览器下载（推荐）：
        echo     打开 https://mirrors.tuna.tsinghua.edu.cn/python/%PYTHON_VERSION%/
        echo     下载 !PYTHON_INSTALLER!
        echo.
        echo   方案B - winget 命令行：
        echo     以管理员身份打开 PowerShell，执行：
        echo     winget install Python.Python.3.12
        echo.
        echo   安装时务必勾选底部 "Add Python to PATH"！
        echo   安装完成后重新双击 build_windows.bat
        echo   ============================================
        echo.
        pause >nul
        exit
    )

    :: 静默安装
    echo   下载完成，正在安装（静默，约15秒）...
    "!DL_PATH!" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del /f /q "!DL_PATH!" >nul 2>&1

    :: 安装后重新检查 PATH
    echo   安装完成，重新检测 Python...
    set PYTHON_CMD=
    for %%C in (python python3 py) do (
        if not defined PYTHON_CMD (
            %%C --version >nul 2>&1
            if !errorlevel! equ 0 (
                for /f "tokens=*" %%V in ('%%C --version 2^>^&1') do set PYTHON_VER=%%V
                set PYTHON_CMD=%%C
            )
        )
    )

    :: 重试：查 AppData
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

    if "%PYTHON_CMD%"=="" (
        echo.
        echo   [X] Python 安装后仍无法检测，请重启电脑后重试。
        echo   或手动安装：https://npmmirror.com/mirrors/python/%PYTHON_VERSION%/
        pause >nul
        exit
    )
)

echo   找到: !PYTHON_VER!
echo.

:: ====== 第2步：安装 PyInstaller ======
echo [2/4] 安装 PyInstaller...
!PYTHON_CMD! -m pip install pyinstaller --quiet --disable-pip-version-check
if !errorlevel! neq 0 (
    echo   安装失败，重试清华镜像...
    !PYTHON_CMD! -m pip install pyinstaller --quiet --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple
    if !errorlevel! neq 0 (
        echo   清华镜像失败，重试阿里镜像...
        !PYTHON_CMD! -m pip install pyinstaller --quiet --disable-pip-version-check -i https://mirrors.aliyun.com/pypi/simple
        if !errorlevel! neq 0 (
            echo.
            echo [X] PyInstaller 安装失败
            echo   请检查网络连接，或手动在 cmd 中执行：
            echo   !PYTHON_CMD! -m pip install pyinstaller
            pause >nul
            exit
        )
    )
)
echo   完成
echo.

:: ====== 第3步：打包 ======
echo [3/4] 开始打包（约 1-2 分钟）...
if exist "dist\EduFlow.exe" del /f /q "dist\EduFlow.exe"

!PYTHON_CMD! -m PyInstaller Eduflow.spec --clean --noconfirm
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
