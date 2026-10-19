import os
import json
import urllib.request
from datetime import datetime

url = "https://query1.finance.yahoo.com/v8/finance/chart/^IXIC"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
    
    meta = data['chart']['result'][0]['meta']
    price = meta['regularMarketPrice']
    prev_close = meta['chartPreviousClose']
    change = price - prev_close
    pct_change = (change / prev_close) * 100

    today = datetime.now().strftime('%Y-%m-%d')
    content = f"""---
title: "纳斯达克每日市场简报 ({today})"
date: {today}
draft: false
tags: ["美股", "纳斯达克", "每日行情"]
---

### 纳斯达克综合指数 (^IXIC) 盘后概览

| 指标 | 数值 |
| :--- | :--- |
| **最新收盘价** | **{price:.2f}** |
| **涨跌额** | {'' if change < 0 else '+'}{change:.2f} |
| **涨跌幅** | {'' if pct_change < 0 else '+'}{pct_change:.2f}% |

---
*本简报由 GitHub Actions 云端工作流于 {today} 全自动实时抓取生成。*
"""

    os.makedirs("content/posts", exist_ok=True)
    file_path = f"content/posts/nasdaq-{today}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"成功生成每日简报: {file_path}")

except Exception as e:
    print(f"数据拉取失败: {e}")
