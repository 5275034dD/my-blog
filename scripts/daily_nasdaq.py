import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
from google import genai

# 1. 监控标的清单
SYMBOLS = {
    "IXIC": "^IXIC",     # 纳斯达克综合指数 (基准大盘)
    "QQQ": "QQQ",        # 纳斯达克100 ETF
    "VIX": "^VIX",       # 恐慌指数
    "TNX": "^TNX",       # 10年期美债收益率
    "NVDA": "NVDA",      # 英伟达
    "AAPL": "AAPL",      # 苹果
    "MSFT": "MSFT",      # 微软
    "GOOGL": "GOOGL",    # 谷歌
    "AMZN": "AMZN",      # 亚马逊
    "META": "META",      # Meta
    "TSLA": "TSLA"       # 特斯拉
}

# 2026 年美联储 FOMC 议息会议决议公布日
FOMC_MEETINGS_2026 = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"
]

def get_next_fomc():
    """计算距离今天最近的下一个美联储 FOMC 决议日"""
    today_dt = datetime.now()
    today_str = today_dt.strftime('%Y-%m-%d')
    for m_date in FOMC_MEETINGS_2026:
        if m_date >= today_str:
            days_left = (datetime.strptime(m_date, '%Y-%m-%d') - today_dt).days + 1
            return m_date, days_left
    return "尚未公布", None

def fetch_earnings_date(symbol):
    """从 Yahoo Finance 获取个股预计财报公布窗口"""
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=calendarEvents"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            calendar = data['quoteSummary']['result'][0]['calendarEvents']
            earnings_date_list = calendar['earnings']['earningsDate']
            if earnings_date_list:
                return earnings_date_list[0].get('fmt', '待定')
    except Exception:
        pass
    return "待定/暂无数据"

def calculate_returns(prices):
    """计算每日收益率序列"""
    return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

def calculate_beta(stock_returns, market_returns):
    """基于协方差与方差计算近 30 交易日 Beta 系数"""
    n = min(len(stock_returns), len(market_returns), 30)
    if n < 5:
        return 1.0
    s_ret, m_ret = stock_returns[-n:], market_returns[-n:]
    mean_s, mean_m = sum(s_ret) / n, sum(m_ret) / n
    cov = sum((s_ret[i] - mean_s) * (m_ret[i] - mean_m) for i in range(n)) / (n - 1)
    var_m = sum((m_ret[i] - mean_m) ** 2 for i in range(n)) / (n - 1)
    return cov / var_m if var_m != 0 else 1.0

def fetch_history_data(symbol):
    """抓取 1 年 K 线行情数据，计算 MA200 与 52 周高点回撤"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            result = data['chart']['result'][0]
            meta = result['meta']
            quotes = result['indicators']['quote'][0]
            closes = [c for c in quotes.get('close', []) if c is not None]
            if not closes:
                return None
            price = meta.get('regularMarketPrice', closes[-1])
            prev = meta.get('chartPreviousClose', closes[-2] if len(closes) > 1 else price)
            change = price - prev
            pct = (change / prev) * 100 if prev else 0

            # 200 日均线 (MA200)
            ma200 = sum(closes[-200:]) / min(len(closes), 200)
            dist_ma200 = ((price - ma200) / ma200) * 100

            # 52 周高点及回撤幅度
            high_52w = max(closes)
            drawdown_52w = ((price - high_52w) / high_52w) * 100

            return {
                "price": price, "change": change, "pct": pct,
                "closes": closes, "returns": calculate_returns(closes),
                "ma200": ma200, "dist_ma200": dist_ma200,
                "high_52w": high_52w, "drawdown_52w": drawdown_52w
            }
    except Exception as e:
        print(f"抓取 {symbol} 失败: {e}")
        return None

# 2. 全量行情抓取与计算
market_data = {key: fetch_history_data(sym) for key, sym in SYMBOLS.items() if fetch_history_data(sym)}
ixic_returns = market_data.get("IXIC", {}).get("returns", [])
mag7_keys = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]
betas = {k: calculate_beta(market_data[k]["returns"], ixic_returns) if k in market_data and ixic_returns else 1.0 for k in mag7_keys}

# 3. 宏观与财报日程数据获取
fomc_date, fomc_days = get_next_fomc()
earnings_calendar = {k: fetch_earnings_date(k) for k in mag7_keys}

today = datetime.now().strftime('%Y-%m-%d')

# 4. 构建包含多时间跨度指标的 Prompt
ixic_data = market_data.get("IXIC", {})
data_prompt_text = f"交易日期: {today}\n"
data_prompt_text += f"纳指大盘(IXIC): 最新={ixic_data.get('price', 0):.2f}, 涨跌幅={ixic_data.get('pct', 0):+.2f}%, 200日均线(MA200)={ixic_data.get('ma200', 0):.2f} (偏离度: {ixic_data.get('dist_ma200', 0):+.2f}%), 52周高点回撤: {ixic_data.get('drawdown_52w', 0):.2f}%\n"
data_prompt_text += f"恐慌指数(VIX): {market_data.get('VIX', {}).get('price', 0):.2f}\n"
data_prompt_text += f"美债10年收益率(TNX): {market_data.get('TNX', {}).get('price', 0):.2f}%\n"
data_prompt_text += f"下一次 FOMC 议息决议日: {fomc_date} (倒计时: {fomc_days} 天)\n\n"
data_prompt_text += "科技七巨头表现、Beta、200日线偏离度与财报日：\n"

for k in mag7_keys:
    if k in market_data:
        d = market_data[k]
        data_prompt_text += f"{k}: 涨跌={d['pct']:+.2f}%, 30天Beta={betas[k]:.2f}, MA200偏离={d['dist_ma200']:+.2f}%, 52周高点回撤={d['drawdown_52w']:.2f}%, 下次财报日={earnings_calendar[k]}\n"

# 5. 调用 Gemini 3.8 Flash 生成研报 (带 503 UNAVAILABLE 自动重试机制)
api_key = os.environ.get("GEMINI_API_KEY")
ai_report = "（未配置 GEMINI_API_KEY，无法生成研报）"

if api_key:
    client = genai.Client(api_key=api_key)
    prompt = f"""
你是一位资深美股量化与宏观策略分析师。请基于提供的今日行情、200日均线(MA200)、52周高点回撤、Beta系数及宏观利率数据，生成一份结构清晰、多时间维度的深度投资研报《纳斯达克全景研报与多时间跨度展望》。

数据输入:
{data_prompt_text}

请严格按照以下 4 个模块编写（使用专业金融术语，结构化 Markdown 呈现）：

### 1. 核心大盘与短线博弈（1-30 天）
- 结合 IXIC 今日涨跌幅、VIX 恐慌指数与短期 Beta 敏感度，评估短线避险与交易择时建议。

### 2. 中期趋势与周期研判（1-12 个月）
- 结合纳指及七巨头距离 200 日均线 (MA200) 的偏离度、52周高点回撤幅度，以及美联储 FOMC 利率路径与财报窗口，评估中期牛熊趋势格局与回调加仓/减仓区间。

### 3. 长期产业与估值展望（1-5 年）
- 结合科技七巨头（Mag 7）在 AI 基础设施与 Capex 资本支出方面的长期逻辑，推演长期资产配置逻辑与潜在风险点（给出乐观/基准/悲观三大情景摘要）。

### 4. 跨周期资产配置建议总结
- 给出 1-2 条明确的短线、中线、长线仓位配置与风控策略。
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
            )
            ai_report = response.text
            break
        except Exception as ai_err:
            err_str = str(ai_err)
            if attempt < max_retries - 1 and ("503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str):
                sleep_sec = (attempt + 1) * 5
                print(f"触发 503/429 服务忙，等待 {sleep_sec} 秒后进行第 {attempt + 2} 次重试...")
                time.sleep(sleep_sec)
            else:
                ai_report = f"AI 研报生成异常: {ai_err}"

# 6. 生成 QuickChart 动态柱状图 URL
chart_pcts = [round(market_data[k]['pct'], 2) if k in market_data else 0 for k in mag7_keys]
chart_colors = ['#22c55e' if p >= 0 else '#ef4444' for p in chart_pcts]
chart_config = {
    "type": "bar",
    "data": {
        "labels": mag7_keys,
        "datasets": [{"label": "涨跌幅 (%)", "data": chart_pcts, "backgroundColor": chart_colors, "borderRadius": 4}]
    },
    "options": {
        "plugins": {
            "legend": {"display": False},
            "title": {"display": True, "text": f"科技七巨头日内涨跌幅对比 ({today})", "font": {"size": 16}}
        }
    }
}
chart_url = f"https://quickchart.io/chart?c={urllib.parse.quote(json.dumps(chart_config))}&w=700&h=380&bkg=white"

# 7. 组装 Markdown 文章输出 (通过列表拼接，避免三引号解析异常)
ixic = market_data.get("IXIC", {"price": 0, "change": 0, "pct": 0, "ma200": 0, "dist_ma200": 0, "drawdown_52w": 0})
vix = market_data.get("VIX", {"price": 0, "change": 0, "pct": 0})
tnx = market_data.get("TNX", {"price": 0, "change": 0, "pct": 0})

md_lines = []
md_lines.append("---")
md_lines.append(f'title: "纳斯达克全景研报与多时间跨度展望 ({today})"')
md_lines.append(f"date: {today}")
md_lines.append("draft: false")
md_lines.append('tags: ["美股", "纳斯达克", "财报日历", "FOMC", "深度研报", "中期预测", "长期趋势", "Beta系数"]')
md_lines.append("---")
md_lines.append("")
md_lines.append("### 📅 重大宏观事件预警")
md_lines.append("")
md_lines.append(f"* 🏛️ **下一次美联储 (FOMC) 议息会议决议日**：`{fomc_date}` （⌛ 距离现在还有 **{fomc_days}** 天）")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("### 📊 核心指标与宏观环境")
md_lines.append("")
md_lines.append("| 标的 | 最新价格/点位 | 涨跌额 | 涨跌幅 | 200日均线 (MA200) | 偏离 MA200 | 52周高点回撤 |")
md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
md_lines.append(f"| **纳斯达克综合指数 (^IXIC)** | **{ixic['price']:.2f}** | {ixic['change']:+.2f} | **{ixic['pct']:+.2f}%** | {ixic['ma200']:.2f} | **{ixic['dist_ma200']:+.2f}%** | **{ixic['drawdown_52w']:.2f}%** |")
md_lines.append(f"| **恐慌指数 (^VIX)** | {vix['price']:.2f} | {vix['change']:+.2f} | {vix['pct']:+.2f}% | - | - | - |")
md_lines.append(f"| **10年期美债收益率 (^TNX)** | {tnx['price']:.2f}% | {tnx['change']:+.2f} | {tnx['pct']:+.2f}% | - | - | - |")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("### 📈 七巨头涨跌幅可视化")
md_lines.append("")
md_lines.append(f"![七巨头涨跌幅对比图]({chart_url})")
md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("### 💡 科技七巨头 (Mag 7) 量化指标与下期财报")
md_lines.append("")
md_lines.append("| 股票代码 | 收盘价 | 涨跌幅 | 30天 Beta | 偏离 MA200 | 52周高点回撤 | 预计下期财报日 |")
md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

for k in mag7_keys:
    if k in market_data:
        d = market_data[k]
        b = betas[k]
        e_date = earnings_calendar.get(k, "待定")
        md_lines.append(f"| **{k}** | ${d['price']:.2f} | {d['pct']:+.2f}% | {b:.2f} | {d['dist_ma200']:+.2f}% | {d['drawdown_52w']:.2f}% | 🗓️ `{e_date}` |")

md_lines.append("")
md_lines.append("---")
md_lines.append("")
md_lines.append("## 🔍 Gemini AI 深度全景研报（含中长期趋势）")
md_lines.append("")
md_lines.append(ai_report)
md_lines.append("")
md_lines.append("---")
md_lines.append("*本报告由 GitHub Actions 自动化工作流实时拉取行情与财报日历，并通过 Gemini AI 联合解析生成。*")

content = "\n".join(md_lines)

os.makedirs("content/posts", exist_ok=True)
file_path = f"content/posts/nasdaq-{today}.md"
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"成功生成研报: {file_path}")
