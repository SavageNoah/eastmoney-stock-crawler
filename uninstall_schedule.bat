@echo off
chcp 65001 >nul
echo ========================================
echo 删除定时任务
echo ========================================

schtasks /delete /tn "东方财富人气榜TOP50爬虫" /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 成功删除定时任务!
) else (
    echo.
    echo 删除定时任务失败，可能任务不存在
)

pause
