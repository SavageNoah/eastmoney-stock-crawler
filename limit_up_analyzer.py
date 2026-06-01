#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股涨停股票概念分析系统
- 获取每日涨停股票列表
- 抓取每只股票所属概念标签
- 统计概念热度，生成分析报告
"""

# 必须在导入 akshare 之前设置环境变量
import os
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['no_proxy'] = '*'

import requests
import sqlite3
import datetime
import json
import time
import re
import akshare as ak
import pandas as pd
from typing import List, Dict, Set, Tuple
from collections import Counter, defaultdict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.eastmoney.com/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 创建不使用代理的 session
SESSION = requests.Session()
SESSION.trust_env = False

DB_PATH = "limit_up_analysis.db"


def get_daily_limit_up() -> List[Dict]:
    """直接调用东方财富API获取当日涨停股票"""
    try:
        print("正在获取涨停股票数据...")
        session = requests.Session()
        session.trust_env = False

        # 使用东方财富行情API
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "500",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f2,f3,f12,f13,f14",
            "_": int(time.time() * 1000)
        }

        response = session.get(url, params=params, timeout=30)
        data = response.json()

        if not data.get("data") or "diff" not in data["data"]:
            print("未获取到行情数据")
            return []

        stocks = []
        for item in data["data"]["diff"]:
            change_pct = float(item.get("f3", 0))
            if change_pct >= 9.9:  # 筛选涨停股
                code = str(item.get("f12", "")).zfill(6)
                name = item.get("f14", "")

                # 判断市场
                if code.startswith("6") or code.startswith("5") or code.startswith("9"):
                    market = 0  # 上海
                else:
                    market = 1  # 深圳

                stocks.append({
                    "code": code,
                    "name": name,
                    "price": float(item.get("f2", 0)),
                    "change_pct": change_pct,
                    "volume": 0,
                    "turnover": 0,
                    "market_cap": 0,
                    "neg_market_cap": 0,
                    "market": market,
                })

        print(f"成功获取 {len(stocks)} 只涨停股票")
        return stocks

    except Exception as e:
        print(f"获取涨停列表失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_stock_concepts(code: str, market: int) -> List[str]:
    """从东方财富 API 获取股票所属概念板块"""
    # 禁用代理
    proxy_dict = {
        "http": None,
        "https": None,
    }

    for retry in range(3):
        try:
            # 市场代码转换：0->1(沪)，1->0(深)
            secid = f"1.{code}" if market == 0 else f"0.{code}"

            # 使用东方财富 API 获取个股详情
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f59,f12,f13,f14,f58"
            response = requests.get(url, headers=HEADERS, timeout=10, proxies=proxy_dict)
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

            # 备用接口
            url2 = f"http://f10.eastmoney.com/CoreConception/CoreConceptionAjax?code={secid}"
            response2 = requests.get(url2, headers=HEADERS, timeout=10, proxies=proxy_dict)
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

            time.sleep(2)
        except Exception as e:
            time.sleep(3)
            continue

    return []


def batch_get_concepts(stocks: List[Dict], delay: float = 0.5) -> List[Dict]:
    """批量获取股票概念标签"""
    print(f"正在批量获取 {len(stocks)} 只股票的概念标签...")
    success_count = 0

    for i, stock in enumerate(stocks, 1):
        try:
            concepts = get_stock_concepts(stock["code"], stock["market"])
            if concepts:
                stock["concepts"] = concepts
                stock["concepts_str"] = " ".join(concepts)
                success_count += 1
            else:
                stock["concepts"] = []
                stock["concepts_str"] = ""

            if i % 10 == 0:
                print(f"已处理 {i}/{len(stocks)} 只股票，成功获取概念: {success_count}")

            time.sleep(delay)
        except Exception as e:
            print(f"获取 {stock['code']} {stock['name']} 概念失败: {e}")
            stock["concepts"] = []
            stock["concepts_str"] = ""

    print(f"概念标签获取完成: {success_count}/{len(stocks)} 只股票成功")
    return stocks


def analyze_concept_heat(stocks: List[Dict]) -> Dict:
    """分析概念热度"""
    all_concepts = []
    concept_stocks = defaultdict(list)  # 概念 -> 股票列表

    for stock in stocks:
        concepts = stock.get("concepts", [])
        for concept in concepts:
            all_concepts.append(concept)
            concept_stocks[concept].append(stock)

    # 统计概念出现次数
    concept_counter = Counter(all_concepts)

    # 构建热度分析结果
    heat_analysis = []
    for concept, count in concept_counter.most_common():
        stocks_in_concept = concept_stocks[concept]
        avg_market_cap = sum(s.get("neg_market_cap", 0) for s in stocks_in_concept) / len(stocks_in_concept) if stocks_in_concept else 0

        heat_analysis.append({
            "concept": concept,
            "limit_up_count": count,
            "ratio": round(count / len(stocks) * 100, 2) if stocks else 0,
            "avg_market_cap": round(avg_market_cap / 100000000, 2),  # 转换为亿元
            "stocks": [(s["code"], s["name"]) for s in stocks_in_concept],
        })

    return {
        "total_limit_up": len(stocks),
        "concepts_with_limit_up": len(heat_analysis),
        "heat_ranking": heat_analysis,
    }


def init_database():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 每日涨停表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_limit_up (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        capture_date TEXT NOT NULL,
        capture_time TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        market INTEGER,
        price REAL,
        change_pct REAL,
        volume REAL,
        turnover REAL,
        market_cap REAL,
        neg_market_cap REAL,
        concepts TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 概念统计表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concept_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        capture_date TEXT NOT NULL,
        concept TEXT NOT NULL,
        limit_up_count INTEGER NOT NULL,
        ratio REAL,
        avg_market_cap REAL,
        stock_codes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 分析报告表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analysis_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        capture_date TEXT NOT NULL UNIQUE,
        total_limit_up INTEGER,
        top_concepts TEXT,
        report_content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("数据库初始化完成")


def save_to_database(stocks: List[Dict], analysis: Dict):
    """保存数据到数据库"""
    now = datetime.datetime.now()
    capture_date = now.strftime("%Y-%m-%d")
    capture_time = now.strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 清除当天旧数据
    cursor.execute("DELETE FROM daily_limit_up WHERE capture_date = ?", (capture_date,))
    cursor.execute("DELETE FROM concept_stats WHERE capture_date = ?", (capture_date,))

    # 保存涨停股票
    for stock in stocks:
        cursor.execute("""
        INSERT INTO daily_limit_up (
            capture_date, capture_time, code, name, market, price,
            change_pct, volume, turnover, market_cap, neg_market_cap, concepts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            capture_date, capture_time, stock["code"], stock["name"], stock["market"],
            stock["price"], stock["change_pct"], stock["volume"], stock["turnover"],
            stock["market_cap"], stock["neg_market_cap"], stock["concepts_str"]
        ))

    # 保存概念统计
    for item in analysis["heat_ranking"]:
        cursor.execute("""
        INSERT INTO concept_stats (
            capture_date, concept, limit_up_count, ratio, avg_market_cap, stock_codes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            capture_date, item["concept"], item["limit_up_count"], item["ratio"],
            item["avg_market_cap"], ",".join([s[0] for s in item["stocks"]])
        ))

    conn.commit()
    conn.close()
    print(f"数据已保存到数据库: {len(stocks)} 只涨停股票，{len(analysis['heat_ranking'])} 个概念")


def generate_text_report(analysis: Dict) -> str:
    """生成文本格式分析报告"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y年%m月%d日")

    report = [
        f"{'='*60}",
        f"A股涨停概念分析报告 - {date_str}",
        f"{'='*60}",
        "",
        f"📊 今日概览",
        f"   涨停股票总数: {analysis['total_limit_up']} 只",
        f"   涉及概念数量: {analysis['concepts_with_limit_up']} 个",
        "",
        f"🔥 热门概念 TOP 20",
        f"   {'排名':<4} {'概念名称':<20} {'涨停家数':<10} {'占比':<8} {'平均流通市值(亿)'}",
        f"   {'-'*56}",
    ]

    for i, item in enumerate(analysis["heat_ranking"][:20], 1):
        stock_names = " ".join([s[1] for s in item["stocks"][:5]])
        if len(item["stocks"]) > 5:
            stock_names += f" 等{len(item['stocks'])}只"

        report.append(f"   {i:<4} {item['concept']:<20} {item['limit_up_count']:<10} {item['ratio']:<8.2f}% {item['avg_market_cap']:.2f}")
        report.append(f"        相关个股: {stock_names}")
        report.append("")

    # 市值分布分析
    small_cap = sum(1 for s in analysis["heat_ranking"] if s["avg_market_cap"] < 50)
    mid_cap = sum(1 for s in analysis["heat_ranking"] if 50 <= s["avg_market_cap"] < 150)
    large_cap = sum(1 for s in analysis["heat_ranking"] if s["avg_market_cap"] >= 150)

    report.extend([
        f"📈 概念市值分布",
        f"   小盘概念(<50亿): {small_cap} 个",
        f"   中盘概念(50-150亿): {mid_cap} 个",
        f"   大盘概念(>150亿): {large_cap} 个",
        "",
        f"💡 分析结论",
    ])

    # 简单结论
    top_3 = analysis["heat_ranking"][:3] if len(analysis["heat_ranking"]) >= 3 else analysis["heat_ranking"]
    if top_3:
        report.append(f"   今日最强主线: {top_3[0]['concept']} ({top_3[0]['limit_up_count']}股涨停)")
        if len(top_3) > 1:
            report.append(f"   次要热点: {', '.join([t['concept'] for t in top_3[1:]])}")

    report.extend([
        "",
        f"{'='*60}",
        f"报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"{'='*60}",
    ])

    return "\n".join(report)


def generate_html_report(analysis: Dict) -> str:
    """生成HTML格式分析报告"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y年%m月%d日")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股涨停概念分析报告 - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f5f7fa; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3); }}
        .header h1 {{ font-size: 28px; font-weight: 600; margin-bottom: 8px; }}
        .header .date {{ font-size: 14px; opacity: 0.9; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .stat-card .value {{ font-size: 32px; font-weight: 700; color: #333; }}
        .stat-card .label {{ font-size: 14px; color: #666; margin-top: 4px; }}
        .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .section h2 {{ font-size: 20px; font-weight: 600; color: #333; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f8f9fa; color: #333; font-weight: 600; text-align: left; padding: 12px 16px; border-bottom: 2px solid #e9ecef; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }}
        tr:hover {{ background: #f8f9fa; }}
        .rank-badge {{ display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; font-weight: 600; font-size: 14px; }}
        .rank-1 {{ background: #ffd700; color: #333; }}
        .rank-2 {{ background: #c0c0c0; color: #333; }}
        .rank-3 {{ background: #cd7f32; color: white; }}
        .rank-other {{ background: #e9ecef; color: #666; }}
        .stock-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }}
        .stock-tag {{ background: #e3f2fd; color: #1976d2; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
        .highlight {{ color: #f44336; font-weight: 600; }}
        .footer {{ text-align: center; color: #999; font-size: 13px; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 A股涨停概念分析</h1>
            <div class="date">{date_str}</div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="value highlight">{analysis['total_limit_up']}</div>
                <div class="label">涨停股票总数</div>
            </div>
            <div class="stat-card">
                <div class="value">{analysis['concepts_with_limit_up']}</div>
                <div class="label">涉及概念数量</div>
            </div>
            <div class="stat-card">
                <div class="value">{len([c for c in analysis['heat_ranking'] if c['limit_up_count'] >= 3])}</div>
                <div class="label">3股以上涨停概念</div>
            </div>
        </div>

        <div class="section">
            <h2>🔥 概念热度排行榜</h2>
            <table>
                <thead>
                    <tr>
                        <th width="80">排名</th>
                        <th>概念名称</th>
                        <th width="100">涨停家数</th>
                        <th width="100">占比</th>
                        <th width="120">平均市值(亿)</th>
                        <th>相关个股</th>
                    </tr>
                </thead>
                <tbody>
"""

    for i, item in enumerate(analysis["heat_ranking"][:30], 1):
        rank_class = f"rank-{i}" if i <= 3 else "rank-other"
        stock_tags = "".join([f'<span class="stock-tag">{s[1]}</span>' for s in item["stocks"][:6]])

        html += f"""
                    <tr>
                        <td><span class="rank-badge {rank_class}">{i}</span></td>
                        <td><strong>{item['concept']}</strong></td>
                        <td class="highlight">{item['limit_up_count']}</td>
                        <td>{item['ratio']:.2f}%</td>
                        <td>{item['avg_market_cap']:.2f}</td>
                        <td><div class="stock-tags">{stock_tags}</div></td>
                    </tr>"""

    html += f"""
                </tbody>
            </table>
        </div>

        <div class="footer">
            报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""

    return html


def save_reports(analysis: Dict):
    """保存分析报告"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y%m%d")

    # 文本报告
    text_report = generate_text_report(analysis)
    text_file = f"limit_up_report_{date_str}.txt"
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(text_report)
    print(f"文本报告已保存: {text_file}")

    # HTML报告
    html_report = generate_html_report(analysis)
    html_file = f"limit_up_report_{date_str}.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"HTML报告已保存: {html_file}")

    # 保存到数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    top_concepts = json.dumps([
        {"concept": c["concept"], "count": c["limit_up_count"]}
        for c in analysis["heat_ranking"][:10]
    ], ensure_ascii=False)

    cursor.execute("""
    INSERT OR REPLACE INTO analysis_reports (
        capture_date, total_limit_up, top_concepts, report_content
    ) VALUES (?, ?, ?, ?)
    """, (now.strftime("%Y-%m-%d"), analysis["total_limit_up"], top_concepts, text_report))

    conn.commit()
    conn.close()

    return text_file, html_file


def main():
    """主函数"""
    print("=" * 60)
    print("A股涨停股票概念分析系统")
    print("=" * 60)

    # 初始化数据库
    init_database()

    # 1. 获取涨停股票
    print("\n[1/4] 获取当日涨停股票...")
    stocks = get_daily_limit_up()
    if not stocks:
        print("没有获取到涨停股票，退出")
        return 1

    # 2. 批量获取概念
    print("\n[2/4] 批量获取股票概念标签...")
    stocks = batch_get_concepts(stocks, delay=0.3)

    # 3. 概念热度分析
    print("\n[3/4] 分析概念热度...")
    analysis = analyze_concept_heat(stocks)

    # 4. 保存数据和报告
    print("\n[4/4] 保存数据和生成报告...")
    save_to_database(stocks, analysis)
    text_file, html_file = save_reports(analysis)

    print("\n" + "=" * 60)
    print("✅ 分析完成!")
    print(f"   涨停股票: {analysis['total_limit_up']} 只")
    print(f"   涉及概念: {analysis['concepts_with_limit_up']} 个")
    print(f"   报告文件: {text_file}, {html_file}")
    print("=" * 60)

    # 打印报告摘要
    print("\n" + generate_text_report(analysis))

    return 0


if __name__ == "__main__":
    exit(main())
