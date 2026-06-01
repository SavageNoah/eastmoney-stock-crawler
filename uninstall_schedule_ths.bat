@echo off
chcp 65001 >nul
echo ========================================
echo 删除同花顺热榜TOP50爬虫定时任务
echo ========================================
echo.

schtasks /delete /tn "同花顺热榜TOP50爬虫" /f

if %ERRORLEVEL% EQU 0 (
    echo 成功删除定时任务!
) else (
    echo 删除定时任务失败，可能任务不存在
)

echo.
pause
