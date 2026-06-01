# 东方财富网人气榜 TOP50 每日爬虫

每天下午 8:00 自动获取东方财富网人气榜排名前 50 的股票，存入 SQLite 数据库。

## 功能

- 每天自动抓取热门股票排名
- 存储所有历史数据到 SQLite 数据库
- 支持查询历史记录
- Windows 定时任务自动运行

## 文件说明

- `crawler.py` - 主爬虫程序
- `run_crawler.bat` - 手动运行批处理
- `install_schedule.bat` - 安装每天 8PM 定时任务
- `uninstall_schedule.bat` - 删除定时任务
- `requirements.txt` - Python 依赖
- `eastmoney_stock_hot.db` - SQLite 数据库（运行后生成）

## 安装

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 安装定时任务（需要管理员权限）：
```
双击 install_schedule.bat
```

## 手动运行

双击 `run_crawler.bat` 即可立即运行一次抓取。

## 数据库结构

表名：`stock_hot_rank`

| 字段 | 说明 |
|------|------|
| id | 自增ID |
| capture_date | 抓取日期 YYYY-MM-DD |
| capture_time | 抓取时间 HH:MM:SS |
| rank | 排名 1-50 |
| code | 股票代码 |
| market | 市场 0=沪A 1=深A |
| name | 股票名称 |
| price | 当前价格 |
| change_pct | 涨跌幅 % |
| change | 涨跌额 |
| volume | 成交量 |
| turnover | 成交额 |
| market_cap | 总市值 |
| neg_market_cap | 流通市值 |
| hot_rank | 人气排名值 |
| created_at | 创建时间 |

## 查询数据

可以用任何 SQLite 客户端打开 `eastmoney_stock_hot.db` 查看数据。
