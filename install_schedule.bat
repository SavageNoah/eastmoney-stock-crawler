@echo off
chcp 65001 >nul
echo ========================================
echo 安装每天 晚上 8:00 定时任务
echo ========================================

SET SCRIPT_PATH=%~dp0run_crawler.bat

echo 脚本路径: %SCRIPT_PATH%

schtasks /create /tn "东方财富人气榜TOP50爬虫" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 20:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 成功创建定时任务!
    echo 每天晚上 8:00 将自动运行获取数据
) else (
    echo.
    echo 创建定时任务失败，请检查权限
)

pause
