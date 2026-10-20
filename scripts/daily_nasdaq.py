import os
import json
import urllib.request
import urllib.parse

def fetch_history_data(symbol):
    """使用 Alpha Vantage 稳定接口获取美股日K线数据"""
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
    
    # 转换雅虎格式代码 (如 ^IXIC) 适配其他源或直接使用对应符号
    # Alpha Vantage 指数通常使用如 QQQ 或直接对应代码，若支持 ^IXIC 可直接传
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={urllib.parse.quote(symbol)}&outputsize=compact&apikey={api_key}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            
            # 兼容处理限制提示
            if "Note" in data or "Information" in data:
                print(f"API 提示: {data.get('Note') or data.get('Information')}")
                
            time_series = data.get("Time Series (Daily)")
            if not time_series:
                print(f"获取 {symbol} 失败，返回数据结构异常: {data}")
                return None
                
            # 按日期正序排列收盘价
            sorted_dates = sorted(time_series.keys())
            closes = [float(time_series[d]["4. close"]) for d in sorted_dates]
            
            if len(closes) < 2:
                return None
                
            price = closes[-1]
            prev = closes[-2]
            change = price - prev
            pct = (change / prev) * 100

            ma200 = sum(closes[-200:]) / min(len(closes), 200)
            dist_ma200 = ((price - ma200) / ma200) * 100

            high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
            drawdown_52w = ((price - high_52w) / high_52w) * 100

            return {
                "price": price, "change": change, "pct": pct,
                "closes": closes, "ma200": ma200, "dist_ma200": dist_ma200,
                "high_52w": high_52w, "drawdown_52w": drawdown_52w
            }
    except Exception as e:
        print(f"请求 Alpha Vantage 异常: {e}")
        return None
