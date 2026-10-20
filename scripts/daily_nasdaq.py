import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

# 定义需要抓取的核心标的列表
SYMBOLS = {
    "IXIC": "^IXIC",     # 纳斯达克综合指数
    "VIX": "^VIX",       # 恐慌指数
    "NVDA": "NVDA",      # 英伟达
    "AAPL": "AAPL",      # 苹果
    "MSFT": "MSFT",      # 微软
    "GOOGL": "GOOGL",    # 谷歌
    "AMZN": "AMZN",      # 亚马逊
    "META": "META",      # Meta
    "TSLA": "TSLA"       # 特斯拉
}

def fetch_symbol_data(symbol):
    """
    抓取 1 年日 K 线行情数据，附带防屏蔽请求头与自动重试机制
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json,text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                result = data['chart']['result'][0]
                timestamps = result.get('timestamp', [])
                quotes = result['indicators']['quote'][0]
                
                # 清理空数据节点
                valid_data = [(t, c) for t, c in zip(timestamps, quotes.get('close', [])) if c is not None]
                if len(valid_data) < 2:
                    return None
                
                closes = [c for _, c in valid_data]
                
                # 【核心修正】：强制使用数组最后两根真实 K 线进行增量与百分比计算
                price = closes[-1]
                prev = closes[-2]
                change = price - prev
                pct = (change / prev) * 100 if prev else 0

                # 200 日移动平均线 (MA200)
                ma200 = sum(closes[-200:]) / min(len(closes), 200)
                dist_ma200 = ((price - ma200) / ma200) * 100

                # 52 周最高点与回撤幅度
                high_52w = max(closes)
                drawdown_52w = ((price - high_52w) / high_52w) * 100

                # 获取最近 5 个交易日的收盘明细
                recent_5_days = []
                for ts, c in valid_data[-5:]:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%m/%d')
                    recent_5_days.append({"date": dt, "close": round(c, 2)})

                return {
                    "price": round(price, 2),
                    "prev": round(prev, 2),
                    "change": round(change, 2),
                    "pct": round(pct, 2),
                    "ma200": round(ma200, 2),
                    "dist_ma200": round(dist_ma200, 2),
                    "high_52w": round(high_52w, 2),
                    "drawdown_52w": round(drawdown_52w, 2),
                    "recent_5_days": recent_5_days
                }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"❌ 抓取标的 {symbol} 失败 (已重试 {max_retries} 次): {e}")
                return None
    return None

def fetch_all_market_data():
    """遍历抓取所有核心标的数据"""
    market_data = {}
    for name, ticker in SYMBOLS.items():
        print(f"正在抓取 {name} ({ticker})...")
        data = fetch_symbol_data(ticker)
        if data:
            market_data[name] = data
        time.sleep(1) # 避免频繁请求触发频次限制
    return market_data

def generate_report_with_ai(market_data):
    """调用 Google Gemini API 生成高质量 Markdown 研报"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 错误：环境变量 GEMINI_API_KEY 未设置！")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    
    # 获取北京时间日期
    beijing_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(beijing_tz).strftime('%Y-%m-%d')
    date_display = datetime.now(beijing_tz).strftime('%Y年%m月%d日')

    prompt = f"""
你是一位顶尖的美股量化策略分析师。请根据以下我抓取到的真实盘面数据，撰写一份符合 Hugo 博客格式的《纳斯达克市场日报》。

【今日真实盘面数据】：
{json.dumps(market_data, ensure_ascii=False, indent=2)}

【严格排版与格式要求】：
1. 文件顶部必须包含 Hugo YAML Front Matter 格式标头：
---
title: "📊 纳斯达克市场日报 — {date_display}"
date: {today_str}T07:00:00+08:00
draft: false
tags: ["美股", "纳斯达克", "量化研报", "科技股"]
categories: ["美股日报"]
description: "纳斯达克综合指数每日量化解析与科技股洞察。"
---

2. 正文必须包含以下五个完整章节，使用三级 Markdown 标题 (###)：
   - ### 一、市场概览：包含当天的纳指收盘数据表格（收盘价、涨跌幅、涨跌点数）以及最近 5 个交易日的收盘明细表格。
   - ### 二、重要新闻：结合当前美股宏观背景（美联储利率政策、AI 科技动态、财报季、美债收益率等），整理 5-8 条硬核要闻点评。
   - ### 三、技术分析：包含大盘 RSI、MACD、MA5、MA200 移动平均线指标分析表格，并列出明确的支撑位（26,000、25,500、25,200）与阻力位（26,700、27,000、27,600）。
   - ### 四、热门科技股表现：使用 Markdown 表格梳理科技七巨头（NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA）的收盘表现与驱动逻辑。
   - ### 五、后市操作建议：给出明确的短线、中线策略与风控提示。

3. 绝对原则：所有价格、涨跌幅数据必须以我提供的 JSON 数据为准，不得自行捏造数值！表格格式必须工整规范。
"""

    print("🤖 正在调用 Gemini 2.5 API 生成研报...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    return response.text, today_str

def save_markdown_post(content, today_str):
    """保存 Markdown 文件到 content/posts/ 目录"""
    output_dir = os.path.join(os.getcwd(), "content", "posts")
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"{today_str}-nasdaq-daily.md"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"✅ 研报生成成功并已保存至: {filepath}")

if __name__ == "__main__":
    print("🚀 开始运行美股量化自动化抓取脚本...")
    data = fetch_all_market_data()
    if not data or "IXIC" not in data:
        print("❌ 错误：核心标的 IXIC 抓取失败，终止自动流程。")
        sys.exit(1)
        
    report_md, today_date = generate_report_with_ai(data)
    save_markdown_post(report_md, today_date)
