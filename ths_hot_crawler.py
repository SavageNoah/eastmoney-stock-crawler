#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门股票 TOP50 爬虫
原同花顺官方热榜API已下线，现在使用 **雪球热门关注榜** 获取数据
每天获取热门股票排名（按关注人数排序就是热门榜），包含热门概念标签，存入 SQLite 数据库
"""

import requests
import sqlite3
import datetime
import json
import time
import pandas as pd
from typing import List, Dict
from bs4 import BeautifulSoup
import akshare as ak

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://xueqiu.com/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def get_top50_hot_stocks() -> List[Dict]:
    """获取雪球热门关注榜 top 50 股票，按关注人数排序就是热门榜
    关注人数越多股票越热门，这就是真正的热门股票排名
    """
    try:
        # 使用 akshare 获取雪球热门关注榜
        # 返回已经按关注人数降序排序，我们取前 50
        df = ak.stock_hot_follow_xq()
        if df is None or df.empty:
            print("akshare 返回空数据")
            return []

        stocks = []
        # 列对应关系（来自 akshare）：
        # 0: 股票代码 (SHxxxxxx/SZxxxxxx), 1: 股票名称, 2: 关注人数, 3: 当前价格
        # 我们需要获取涨跌幅数据，所以挨个查询
        from akshare import stock_zh_a_spot
        df_spot = stock_zh_a_spot()
        if df_spot is not None and not df_spot.empty:
            # 创建代码 -> 涨跌幅映射，列名是中文
            # 列: 代码, 名称, 最新价, 涨跌幅, 涨跌额, ...
            spot_map = {}
            for _, row in df_spot.iterrows():
                # 处理各种代码格式：纯数字代码、带前缀 bj/sh/sz 等格式
                raw_code = str(row.iloc[0])
                # 提取纯数字部分，只保留数字
                pure_code = ''.join([c for c in raw_code if c.isdigit()])
                if len(pure_code) >= 6:
                    code = pure_code[-6:].zfill(6)
                elif pure_code:
                    code = pure_code.zfill(6)
                else:
                    continue
                change_pct = row.iloc[3]  # 涨跌幅
                change = row.iloc[4]     # 涨跌额
                spot_map[code] = (change_pct, change)
        else:
            spot_map = {}

        # 取前 50 名，已经按关注人数降序排序
        for rank, (_, row) in enumerate(df.head(50).iterrows(), 1):
            # 列对应关系（来自 akshare）：
            # 0: 股票代码 (SHxxxxxx/SZxxxxxx), 1: 股票名称, 2: 关注人数, 3: 当前价格
            code_full = str(row.iloc[0])
            name = str(row.iloc[1])
            price = float(row.iloc[3]) if pd.notna(row.iloc[3]) else None

            # 提取纯代码
            if code_full.startswith(('SH', 'SZ', 'sh', 'sz')):
                code = code_full[2:]
            else:
                code = code_full
            code = code.zfill(6)  # 补零到 6 位

            # 从最新行情获取涨跌幅
            change_pct = None
            change = None
            if code in spot_map:
                change_pct, change = spot_map[code]

            stock = {
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "change": change,
                "rank": rank,
            }
            # 判断市场 0=沪 1=深
            code_str = str(stock["code"])
            if code_str.startswith("6") or code_str.startswith("5") or code_str.startswith("9"):
                stock["market"] = 0
            else:
                stock["market"] = 1
            stocks.append(stock)

        print(f"成功获取 {len(stocks)} 只热门股票（雪球热门关注榜 TOP50）")

        # 获取每个股票的概念标签
        print("正在获取概念标签...")
        concept_count = 0
        for stock in stocks:
            try:
                code = stock["code"]
                concepts = get_stock_concepts_akshare(code)
                if concepts:
                    stock["hot_concept"] = " ".join(concepts)
                    concept_count += 1
                else:
                    stock["hot_concept"] = None
                # 限速，防止反爬
                time.sleep(0.3)
            except Exception as e:
                print(f"获取 {stock['code']} {stock['name']} 概念失败: {e}")
                stock["hot_concept"] = None

        print(f"成功获取 {concept_count} 只股票的概念标签")
        return stocks

    except Exception as e:
        print(f"获取失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_stock_concepts_akshare(code: str) -> List[str]:
    """从东方财富 API 获取股票所属概念板块，带重试
    """
    for retry in range(3):
        try:
            # 格式化为东方财富API需要的代码格式
            if str(code).startswith("6") or str(code).startswith("5") or str(code).startswith("9"):
                full_code = f"1.{code}"  # 1=上海
            else:
                full_code = f"0.{code}"  # 0=深圳
            # 使用东方财富 API 获取个股详情
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={full_code}&fields=f59,f12,f13,f14,f58"
            # f58 是业务板块，f59 是概念板块？让我们试试
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    # 尝试获取概念字段
                    for key in ["f58", "f59"]:
                        if key in data["data"]:
                            concept_str = data["data"][key]
                            if concept_str and isinstance(concept_str, str):
                                # 拆分概念
                                concepts = [c.strip() for c in concept_str.split(";") if c.strip()]
                                if concepts:
                                    return concepts
            # 如果上面不行，试另一个接口
            try:
                url2 = f"http://f10.eastmoney.com/CoreConception/CoreConceptionAjax?code={full_code}"
                response2 = requests.get(url2, headers=HEADERS, timeout=10)
                if response2.status_code == 200:
                    data = response2.json()
                    if "hyzx" in data and data["hyzx"]:
                        concepts = [item["gxmc"] for item in data["hyzx"] if item.get("gxmc")]
                        if concepts:
                            return concepts
                    if "gnry" in data and data["gnry"]:
                        concepts = [item["gxmc"] for item in data["gnry"] if item.get("gxmc")]
                        if concepts:
                            return concepts
            except Exception:
                pass
            time.sleep(2)
        except Exception as e:
            # retry after sleep
            time.sleep(3)
            continue
    return []

def init_database(db_path: str):
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建每日热门榜表
    create_rank_table = """
    CREATE TABLE IF NOT EXISTS ths_hot_rank (
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
        hot_concept TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_rank_table)

    # 创建汇总表 - 只保留最近250个交易日，每个股票一条记录，带热门概念
    create_summary_table = """
    CREATE TABLE IF NOT EXISTS ths_hot_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        market INTEGER,
        hot_concept TEXT,
        first_appear_date TEXT NOT NULL,
        last_appear_date TEXT NOT NULL,
        appear_count INTEGER DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    # 去重：先删除今天已有的记录
    cursor.execute("DELETE FROM ths_hot_rank WHERE capture_date = ?", (capture_date,))
    deleted = cursor.rowcount
    if deleted > 0:
        print(f"已删除今天 {deleted} 条重复记录")

    inserted = 0
    for stock in stocks:
        insert_sql = """
        INSERT INTO ths_hot_rank (
            capture_date, capture_time, rank, code, market, name,
            price, change_pct, change, hot_concept
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            capture_date, capture_time, stock.get("rank"),
            stock.get("code"), stock.get("market"), stock.get("name"),
            stock.get("price"), stock.get("change_pct"), stock.get("change"), stock.get("hot_concept")
        )
        cursor.execute(insert_sql, values)
        inserted += 1

        # 更新汇总表
        code = stock.get("code")
        name = stock.get("name")
        market = stock.get("market")
        hot_concept = stock.get("hot_concept")

        cursor.execute("SELECT id FROM ths_hot_summary WHERE code = ?", (code,))
        existing = cursor.fetchone()

        if existing:
            # 更新已有记录
            update_sql = """
            UPDATE ths_hot_summary
            SET name = ?, market = ?, hot_concept = ?, last_appear_date = ?, appear_count = appear_count + 1, updated_at = CURRENT_TIMESTAMP
            WHERE code = ?
            """
            cursor.execute(update_sql, (name, market, hot_concept, capture_date, code))
        else:
            # 插入新记录
            insert_summary_sql = """
            INSERT INTO ths_hot_summary (code, name, market, hot_concept, first_appear_date, last_appear_date, appear_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """
            cursor.execute(insert_summary_sql, (code, name, market, hot_concept, capture_date, capture_date))

    # 清理：删除超过250天的旧汇总记录
    cutoff_date = (now - datetime.timedelta(days=250)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM ths_hot_summary WHERE last_appear_date < ?", (cutoff_date,))
    deleted_old = cursor.rowcount
    if deleted_old > 0:
        print(f"清理汇总表：删除 {deleted_old} 条超过250天的旧记录")

    conn.commit()
    conn.close()
    print(f"成功插入 {inserted} 条每日记录")
    return inserted

def query_latest(db_path: str):
    """查询今天最新的数据，输出到控制台"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT rank, code, name, price, change_pct, hot_concept
    FROM ths_hot_rank
    WHERE capture_date = (SELECT MAX(capture_date) FROM ths_hot_rank)
    ORDER BY rank
    """)
    rows = cursor.fetchall()

    print(f"\n=== 最新 {len(rows)} 条记录 ===")
    print(f"{'排名':<4} {'代码':<6} {'名称':<8} {'价格':<8} {'涨跌幅':<8} {'热门概念'}")
    print("-" * 70)
    for row in rows:
        rank, code, name, price, change_pct, concept = row
        price_str = f"{price:.2f}" if price else "-"
        change_str = f"{change_pct:.2f}%" if change_pct else "-"
        concept_str = concept if concept else "-"
        if concept_str and len(concept_str) > 30:
            concept_str = concept_str[:27] + "..."
        print(f"{rank:<4} {code:<6} {name:<8} {price_str:<8} {change_str:<8} {concept_str}")

    conn.close()

def main():
    """主函数"""
    db_path = "ths_hot_stocks.db"

    # 初始化数据库
    init_database(db_path)

    # 获取数据
    print("正在获取雪球热门关注榜 TOP50 ...")
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
