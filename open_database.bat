@echo off
chcp 65001 >nul
echo 正在打开 DB Browser for SQLite...
echo 数据库文件: eastmoney_stock_hot.db
echo.

start "" "DBBrowser\DB Browser for SQLite\DB Browser for SQLite.exe" eastmoney_stock_hot.db

exit
