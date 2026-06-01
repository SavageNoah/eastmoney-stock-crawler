@echo off
chcp 65001 >nul
echo ========================================
echo 东方财富网人气榜 TOP50 爬虫
echo 抓取时间: %date% %time%
echo ========================================

cd /d "%~dp0"
python crawler.py

echo.
echo 按任意键退出...
pause >nul
