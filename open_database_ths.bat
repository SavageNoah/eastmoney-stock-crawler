@echo off
chcp 65001 >nul
echo 正在打开 DB Browser for SQLite...
echo 数据库文件: ths_hot_stocks.db
echo.

start "" "DBBrowser\DB Browser for SQLite\DB Browser for SQLite.exe" ths_hot_stocks.db

exit
