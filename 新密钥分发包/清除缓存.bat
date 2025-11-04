@echo off
title Clear Cache

echo.
echo ===================================================
echo   O2O Comparison Tool - Clear Fingerprint Cache
echo ===================================================
echo.
echo Clearing cache, please wait...
echo.

set "cleared=0"

REM Clear current directory cache
if exist ".fingerprint_cache" (
    del /f /q ".fingerprint_cache" >nul 2>&1
    if not exist ".fingerprint_cache" (
        echo [OK] Deleted program directory cache
        set /a "cleared+=1"
    )
)

REM Clear user data directory cache
if exist "%APPDATA%\O2OComparison\.fingerprint_cache" (
    del /f /q "%APPDATA%\O2OComparison\.fingerprint_cache" >nul 2>&1
    if not exist "%APPDATA%\O2OComparison\.fingerprint_cache" (
        echo [OK] Deleted user data cache
        set /a "cleared+=1"
    )
)

REM Try to delete other possible locations
for %%d in (
    "%USERPROFILE%\.fingerprint_cache"
    "%TEMP%\.fingerprint_cache"
    "%LOCALAPPDATA%\O2OComparison\.fingerprint_cache"
) do (
    if exist %%d (
        del /f /q %%d >nul 2>&1
        if not exist %%d (
            echo [OK] Deleted extra cache
            set /a "cleared+=1"
        )
    )
)

echo.
if %cleared% GTR 0 (
    echo ===================================================
    echo   Cache cleared! Total: %cleared% files
    echo ===================================================
    echo.
    echo You can now run the comparison tool.
) else (
    echo ===================================================
    echo   No cache files found (may already be cleared)
    echo ===================================================
    echo.
    echo You can run the comparison tool directly.
)

echo.
echo Press any key to exit...
pause >nul
