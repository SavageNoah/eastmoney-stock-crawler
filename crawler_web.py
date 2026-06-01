#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
东方财富网人气榜 TOP50 爬虫 - 网页爬取版本
直接从网页爬取表格数据，不依赖API
"""

import requests
import sqlite3
import datetime
import json
from typing import List, Dict
from bs4 import BeautifulSoup

# 东方财富网热门个股排行页面
EASTMONEY_URL = "https://quote.eastmoney.com/center/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/center/ranking.html",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def get_top50_hot_stocks() -> List[Dict]:
    """从网页获取东方财富网人气榜 top 50 股票"""
    try:
        # 打开排行页面
        response = requests.get(EASTMONEY_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 人气榜表格
        # 找到数据表格
        table = soup.find('table', {'id': 'table_wrapper'})
        if not table:
            # 找任意表格
            tables = soup.find_all('table')
            for t in tables:
                if len(t.find_all('tr')) > 10:
                    table = t
                    break

        if not table:
            print("找不到数据表格")
            return []

        stocks = []
        rows = table.find_all('tr')[1:]  # 跳过表头
        for row in rows[:50]:  # 只取前50
            cols = row.find_all('td')
            if len(cols) >= 8:
                # 提取数据
                # 通常顺序：排名 代码 名称 最新 涨跌幅 涨跌 成交量 成交额 ...
                code_col = cols[1].get_text(strip=True)
                name_col = cols[2].get_text(strip=True)
                price_col = cols[3].get_text(strip=True)
                change_pct_col = cols[4].get_text(strip=True)
                change_col = cols[5].get_text(strip=True)
                volume_col = cols[6].get_text(strip=True)
                turnover_col = cols[7].get_text(strip=True)

                # 去掉%符号
                change_pct = float(change_pct.replace('%', '')) if change_pct else None
                price = float(price_col) if price_col else None
                change = float(change_col) if change_col else None

                # 判断市场
                market = 0 if code_col.startswith('6') else 1

                stock = {
                    "code": code_col,
                    "name": name_col,
                    "price": price,
                    "change_pct": change_pct,
                    "change": change,
                    "volume": int(float(volume_col)) if volume_col else None,
                    "turnover": float(turnover_col) if turnover_col else None,
                    "market": market,
                }
                stocks.append(stock)

        print(f"成功从网页获取 {len(stocks)} 只热门股票")
        return stocks

    except Exception as e:
        print(f"网页爬取失败: {e}")
        return []

def init_database(db_path: str):
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建表 - 如果不存在
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS stock_hot_rank (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        capture_date TEXT NOT NULL,
        capture_time TEXT NOT NULL,
        rank INTEGER NOT NULL,
        code TEXT NOT NULL,
        market INTEGER,
        name TEXT NOT NULL,
        price REAL,
        change_pct REAL,
        change REAL,
        volume INTEGER,
        turnover REAL,
        market_cap REAL,
        neg_market_cap REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_table_sql)
    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {db_path}")

def save_to_database(db_path: str, stocks: List[Dict]):
    """保存股票数据到数据库"""
    now = datetime.datetime.now()
    capture_date = now.strftime("%Y-%m-%d")
    capture_time = now.strftime("%H:%M:%S")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    for rank, stock in enumerate(stocks, 1):
        insert_sql = """
        INSERT INTO stock_hot_rank (
            capture_date, capture_time, rank, code, market, name,
            price, change_pct, change, volume, turnover,
            market_cap, neg_market_cap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            capture_date, capture_time, rank,
            stock.get("code"), stock.get("market"), stock.get("name"),
            stock.get("price"), stock.get("change_pct"), stock.get("change"),
            stock.get("volume"), stock.get("turnover"),
            None, None
        )
        cursor.execute(insert_sql, values)
        inserted += 1

    conn.commit()
    conn.close()
    print(f"成功插入 {inserted} 条记录")
    return inserted

def query_latest(db_path: str):
    """查询最近一次的数据，输出到控制台"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查询最近一次日期的所有记录
    query_sql = """
    SELECT capture_date, capture_time, rank, code, name, price, change_pct
    FROM stock_hot_rank
    WHERE capture_date = (SELECT MAX(capture_date) FROM stock_hot_rank)
    ORDER BY rank
    """
    cursor.execute(query_sql)
    rows = cursor.fetchall()

    print(f"\n=== 最新 {len(rows)} 条记录 ===")
    print(f"{'排名':<4} {'代码':<6} {'名称':<8} {'价格':<8} {'涨跌幅':<8}")
    print("-" * 40)
    for row in rows:
        date, time, rank, code, name, price, change_pct = row
        price_str = f"{price:.2f}" if price else "-"
        change_str = f"{change_pct:.2f}%" if change_pct else "-"
        print(f"{rank:<4} {code:<6} {name:<8} {price_str:<8} {change_str:<8}")

    conn.close()

def main():
    """主函数"""
    db_path = "eastmoney_stock_hot.db"

    # 初始化数据库
    init_database(db_path)

    # 获取数据
    print("正在获取东方财富网人气榜 TOP50 ...")
    stocks = get_top50_hot_stocks()

    if not stocks:
        print("没有获取到数据，退出")
        return 1

    # 保存到数据库
    save_to_database(db_path, stocks)

    # 查询并显示
    query_latest(db_path)

    print(f"\n完成! 数据已保存到 {db_path}")
    return 0

if __name__ == "__main__":
    exit(main())
