@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo 同花顺热榜TOP50爬虫
echo ========================================
echo.

python ths_hot_crawler.py

echo.
pause
