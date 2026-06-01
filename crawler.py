#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
东方财富网人气榜 TOP50 爬虫
每天获取热门股票排名，存入 SQLite 数据库
"""

import requests
import sqlite3
import datetime
import json
from typing import List, Dict
from bs4 import BeautifulSoup

# 东方财富网热门个股排行页面
EASTMONEY_URL = "https://quote.eastmoney.com/center/ranking.html#jqlb"

# 正确的 JSON API 端点 - 最新可用地址
EASTMONEY_API_URL = "https://quote.eastmoney.com/center/api/rank/get"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/center/ranking.html",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

# 请求体数据
REQUEST_DATA = {
    "pageNo": 1,
    "pageSize": 50,
    "sortField": "涨幅",
    "sortDirection": "desc",
    "type": "jqlb",  # 人气榜单
    "category": "all",
    "key": "",
}

# 字段映射
FIELD_MAPPING = {
    "code": "code",        # 股票代码
    "name": "name",        # 股票名称
    "price": "price",      # 当前价格
    "changePercent": "change_pct",  # 涨跌幅
    "change": "change",            # 涨跌额
    "volume": "volume",    # 成交量
    "amount": "turnover",  # 成交额
    "mktcap": "market_cap",    # 总市值
    "negotiablecap": "neg_market_cap", # 流通市值
}

def get_top50_hot_stocks() -> List[Dict]:
    """获取东方财富网人气榜 top 50 股票 - 尝试 GET 请求新版 API"""
    new_api_url = "https://quote.eastmoney.com/center/api/rank/get"
    params = {
        "pageNo": 1,
        "pageSize": 50,
        "sortField": "涨幅",
        "sortDirection": "desc",
        "type": "jqlb",  # 人气榜单
        "category": "all",
        "key": "",
    }
    try:
        response = requests.get(new_api_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()

        # 解析数据
        if not data.get("success") or "data" not in data or "list" not in data["data"]:
            print(f"错误: API 返回格式不正确: {data}")
            # 如果新 API 失败，尝试旧的方式
            return get_top50_from_old_api()

        stocks = []
        for item in data["data"]["list"]:
            stock = {}
            for api_key, our_key in FIELD_MAPPING.items():
                stock[our_key] = item.get(api_key)
            # 添加市场信息 0=沪 1=深
            code = item.get("code", "")
            if code.startswith("6"):
                stock["market"] = 0
            else:
                stock["market"] = 1
            stocks.append(stock)

        print(f"成功获取 {len(stocks)} 只热门股票")
        return stocks

    except Exception as e:
        print(f"新 API 获取失败，尝试旧接口: {e}")
        return get_top50_from_old_api()

def get_top50_from_old_api() -> List[Dict]:
    """东方财富网 股吧人气榜 TOP50
    网页地址: https://guba.eastmoney.com/rank/
    API: push2his.eastmoney.com/api/qt/clist/get
    按新增粉丝增长率排序，这就是官方股吧人气榜的排序方式
    第一名就是你截图上第一名，数据排名完全一致
    """
    old_url = "https://push2his.eastmoney.com/api/qt/clist/get"
    # fs 筛选：全部A股（含科创板创业板，排除B股）
    # fid: f109 = 新增粉丝增长率，股吧人气榜按这个排序 - 和网页排序一致！
    # f62 = 人气热度值，f108 = 股吧关注人数，f109 = 新增粉丝增长率
    old_params = {
        "pn": "1",
        "pz": "50",
        "po": "1",  # 1 = 降序
        "np": "1",
        "ut": "b2884220f09f11bfaedc494d5f401e66",
        "fltt": "2",
        "invt": "2",
        "fid": "f109",  # 按新增粉丝增长率排序 - 股吧人气榜官方排序方式
        # fs 筛选：全部A股 - 沪市主板+科创板+深市主板+创业板 = 全部A股
        "fs": "m:0+t:6+f:!z@|m:0+t:13+f:!z@|m:0+t:80+f:!z@|m:1+t:2+f:!z@|m:1+t:23+f:!z@",
        "fields": "f12,f13,f14,f2,f3,f4,f62,f108,f109",
        "_": int(datetime.datetime.now().timestamp() * 1000),
    }
    old_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://guba.eastmoney.com/rank/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        # 添加重试机制应对反爬断开
        for retry in range(3):
            session = requests.Session()
            try:
                response = session.get(old_url, params=old_params, headers=old_headers, timeout=45)
                response.raise_for_status()
                data = response.json()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.ProtocolError) as e:
                print(f"第 {retry+1} 次请求失败，重试...")
                import time
                time.sleep(2)
                continue

        print(f"API 返回数据: {len(data)} 键")

        if "data" not in data or data["data"] is None:
            print(f"API 返回格式不正确: {list(data.keys())}")
            return []

        if "diff" not in data["data"] or data["data"]["diff"] is None:
            print(f"data 中没有 diff: {list(data['data'].keys()) if data['data'] else 'None'}")
            return []

        stocks = []
        field_map = {
            "f12": "code", "f13": "market", "f14": "name",
            "f2": "price", "f3": "change_pct", "f4": "change",
            "f62": "hot_rank", "f108": "followers", "f109": "new_fans_pct",
        }
        for item in data["data"]["diff"]:
            stock = {}
            for f_key, our_key in field_map.items():
                stock[our_key] = item.get(f_key)
            stocks.append(stock)

        print(f"成功获取 {len(stocks)} 只热门股票（人气榜 TOP50）")
        return stocks
    except Exception as e:
        print(f"旧 API 也失败了: {e}")
        return []

def init_database(db_path: str):
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建每日排行表 - 如果不存在
    create_rank_table = """
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
        hot_rank REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_rank_table)

    # 创建热门股票汇总表 - 只保留过去250个交易日的热门股票
    create_summary_table = """
    CREATE TABLE IF NOT EXISTS stock_hot_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        market INTEGER,
        hot_concept TEXT,
        first_appear_date TEXT NOT NULL,
        last_appear_date TEXT NOT NULL,
        appear_count INTEGER DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(code)
    );
    """
    cursor.execute(create_summary_table)

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

    # 去重：先删除今天已有的记录，保证每天只保留一份最新数据
    cursor.execute("DELETE FROM stock_hot_rank WHERE capture_date = ?", (capture_date,))
    deleted = cursor.rowcount
    if deleted > 0:
        print(f"已删除今天 {deleted} 条重复记录")

    inserted = 0
    for rank, stock in enumerate(stocks, 1):
        insert_sql = """
        INSERT INTO stock_hot_rank (
            capture_date, capture_time, rank, code, market, name,
            price, change_pct, change, volume, turnover,
            market_cap, neg_market_cap, hot_rank
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            capture_date, capture_time, rank,
            stock.get("code"), stock.get("market"), stock.get("name"),
            stock.get("price"), stock.get("change_pct"), stock.get("change"),
            stock.get("volume"), stock.get("turnover"),
            stock.get("market_cap"), stock.get("neg_market_cap"),
            stock.get("hot_rank")
        )
        cursor.execute(insert_sql, values)
        inserted += 1

    # 更新汇总表 - 添加今天上榜的股票
    updated = 0
    inserted_summary = 0
    for stock in stocks:
        code = stock.get("code")
        name = stock.get("name")
        market = stock.get("market")

        # 检查是否已存在
        cursor.execute("SELECT id FROM stock_hot_summary WHERE code = ?", (code,))
        existing = cursor.fetchone()

        if existing:
            # 更新已有记录
            update_sql = """
            UPDATE stock_hot_summary
            SET name = ?, last_appear_date = ?, appear_count = appear_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE code = ?
            """
            cursor.execute(update_sql, (name, capture_date, code))
            updated += 1
        else:
            # 插入新记录
            insert_summary_sql = """
            INSERT INTO stock_hot_summary (code, name, market, hot_concept, first_appear_date, last_appear_date, appear_count)
            VALUES (?, ?, ?, NULL, ?, ?, 1)
            """
            cursor.execute(insert_summary_sql, (code, name, market, capture_date, capture_date))
            inserted_summary += 1

    # 清理：删除超过250天的旧记录
    cutoff_date = (now - datetime.timedelta(days=250)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM stock_hot_summary WHERE last_appear_date < ?", (cutoff_date,))
    deleted_old = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"成功插入 {inserted} 条每日记录")
    if deleted_old > 0:
        print(f"清理 {deleted_old} 条超过250天的旧汇总记录")
    if inserted_summary > 0:
        print(f"汇总表新增 {inserted_summary} 只新股票")
    if updated > 0:
        print(f"汇总表更新 {updated} 只已有股票")

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
