import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time

# =================================================================
# 🔑 [모의투자 계좌 설정] Streamlit Secrets 내부 금고 연동
# =================================================================
APP_KEY = st.secrets["HANTU_APP_KEY"]
APP_SECRET = st.secrets["HANTU_APP_SECRET"]
MOCK_FLAG = True  
# =================================================================

class KoreaInvestmentAPI:
    def __init__(self):
        if MOCK_FLAG:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_access_token(self):
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            return st.session_state.api_access_token
        now = datetime.now()
        if "last_token_request_time" in st.session_state and st.session_state.last_token_request_time:
            if now - st.session_state.last_token_request_time < timedelta(minutes=1):
                return None
        st.session_state.last_token_request_time = now
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json"}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                token = response.json().get("access_token")
                st.session_state.api_access_token = token
                return token
            return None
        except:
            return None

    def get_yahoo_backup_price(self, ticker):
        try:
            clean_ticker = str(ticker).strip()
            yahoo_ticker = f"{clean_ticker}.KQ"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            res = requests.get(url, headers=headers, timeout=1.5)
            
            if res.status_code != 200 or "result" not in res.json().get("chart", {}):
                yahoo_ticker = f"{clean_ticker}.KS"
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
                res = requests.get(url, headers=headers, timeout=1.5)
                
            if res.status_code == 200:
                json_data = res.json()
                result = json_data.get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    close_p = meta.get("regularMarketPrice")
                    if close_p is None:
                        indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
                        closes = [c for c in indicators.get("close", []) if c is not None]
                        close_p = closes[-1] if closes else 0.0
                    
                    if close_p > 0:
                        return {
                            "Close": float(close_p),
                            "High": float(close_p * 1.002),
                            "Low": float(close_p * 0.998),
                            "Volume": float(meta.get("regularMarketVolume", 150000.0))
                        }
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}
        except:
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}

    def get_realtime_price(self, ticker):
        access_token = self.get_access_token()
        if not access_token:
            return self.get_yahoo_backup_price(ticker)
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200" 
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if not res_data or res_data.get("stck_prpr") == "" or res_data.get("stck_prpr") is None:
                    return self.get_yahoo_backup_price(ticker)
                
                current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                volume = float(str(res_data.get("accl_tr_vol", 0)).strip())
                
                return {
                    "Close": current_price,
                    "High": high_price if high_price > 0 else current_price,
                    "Low": low_price if low_price > 0 else current_price,
                    "Volume": volume if volume > 0 else 1000.0
                }
            return self.get_yahoo_backup_price(ticker)
        except:
            return self.get_yahoo_backup_price(ticker)

# --- 기술적 지표 퀀트 연산 엔진 ---
def process_quant_signals(df):
    if len(df) < 2:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['타이밍 신호'] = "🟢 관망(대기)"
        return df

    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['Price_Vol'] = typical_price * df['Volume']
    df['VWAP'] = df['Price_Vol'].cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    df['Vol_MA'] = df['Volume'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).mean()
    
    signals = []
    for idx in range(len(df)):
        if idx < 1:
            signals.append("🟢 관망(대기)")
            continue
        c_row = df.iloc[idx]
        p_local_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol_ma = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        if (c_row['Close'] > c_row['VWAP']) and (c_row['Close'] >= p_local_high) and (c_row['Volume'] > p_vol_ma * 1.02) and (c_row['RSI'] < 78):
            signals.append("🔥 매수 타점!!")
        elif c_row['RSI'] > 82:
            signals.append("🚨 익절/청산")
        else:
            signals.append("🟢 관망(대기)")
    df['타이밍 신호'] = signals
    return df

# --- 웹 대시보드 인터페이스 설정 ---
st.set_page_config(page_title="초고속 커스텀 스캐너", layout="centered")

# 기본 마스터 풀 정의 (유저 세션 비어있을 때 초기 설정용)
DEFAULT_POOL = {
    "005930": "삼성전자", "000660": "SK하이닉스", "009150": "삼성전기",
    "207940": "삼성바이오로직스", "068270": "셀트리온", "373220": "LG에너지솔루션", 
    "051910": "LG화학", "247540": "에코프로비엠", "005380": "현대차", 
    "000270": "기아", "009540": "HD현대중공업", "035420": "NAVER", 
    "035720": "카카오", "352820": "하이브"
}

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = DEFAULT_POOL.copy()

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

# =================================================================
# 🛠️ [사이드바] 실시간 종목 풀(Pool) 커스텀 편집 시스템
# =================================================================
st.sidebar.markdown("### 🛠️ 내 커스텀 종목 편집기")

with st.sidebar.form("add_stock_form", clear_on_submit=True):
    new_ticker = st.text_input("종목코드 입력 (6자리)", max_chars=6).strip()
    new_name = st.text_input("종목명 입력").strip()
    submit_add = st.form_submit_button("➕ 종목 추가하기")
    
    if submit_add and new_ticker and new_name:
        st.session_state.custom_stock_pool[new_ticker] = new_name
        st.sidebar.success(f"✅ {new_name}({new_ticker}) 추가 완료!")

st.sidebar.markdown("---")
st.sidebar.write("📋 현재 등록된 감시 종목 리스트")

# 개별 삭제 기능 구현
delete_target = None
for tk, nm in list(st.session_state.custom_stock_pool.items()):
    col1, col2 = st.sidebar.columns([3, 1])
    col1.caption(f"▪️ {nm} ({tk})")
    if col2.button("❌", key=f"del_{tk}"):
        delete_target = tk

if delete_target:
    del st.session_state.custom_stock_pool[delete_target]
    if delete_target in st.session_state.multi_market_data:
        del st.session_state.multi_market_data[delete_target]
    st.rerun()

# =================================================================

st.markdown("### 🏹 전시장 통합 수급 돌파 스캐너 (TOP 20)")
st.caption(f"⏱️ 대역폭 최적화 모드 가동 중... ({datetime.now().strftime('%H:%M:%S')})")

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if st.button("🔑 데이터 버퍼 초기화", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.rerun()

summary_rows = []
total_accumulated_ticks = [] 

# 편집기 풀 기반 실시간 시세 연산 루프
for ticker, name in st.session_state.custom_stock_pool.items():
    # 기저 데이터 생성
    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        raw_price = api.get_realtime_price(ticker)
        init_rows = []
        init_times = []
        base_p = raw_price["Close"] if raw_price["Close"] > 0 else 50000.0
        
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            mock_p = base_p + (i * 100 if i % 2 == 0 else -i * 50)
            init_rows.append({
                "Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": raw_price["Volume"]
            })
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    # 초단위 실시간 체결 처리
    live_tick = api.get_realtime_price(ticker)
    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    total_accumulated_ticks.append(len(st.session_state.multi_market_data[ticker]))

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산":
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker,
        "종목명": name,
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']),
        "수급선": int(latest_info['VWAP']),
        "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']),
        "실시간거래대금": realtime_trading_value,
        "신호가중치": signal_weight
    })

# --- 🌟 [20종목 최적화 정렬 컷오프 처리] ---
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(
        by=['신호가중치', '실시간거래대금'], 
        ascending=[True, False]
    ).head(20).reset_index(drop=True) # ⚡ 상위 20개 종목으로 타이트하게 압축해 로딩 속도 상향
else:
    summary_df = pd.DataFrame()

# 전광판 리스트 출력
st.markdown("---")

if not summary_df.empty:
    has_buy_signal = not summary_df[summary_df["신호가중치"] == 0].empty
    if has_buy_signal:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank_idx = index + 1
        card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']})"
        card_body = f"💰 **현재가**: {row['현재가']:,}원 ｜ 📈 **RSI**: {row['RSI']} ｜ 📊 **거래대금**: {int(row['실시간거래대금']/100000000):,}억\n\n🍏 **수급선**: {row['수급선']:,}원 ｜ 🛑 **저항선**: {row['저항선']:,}원"
        
        if sig == "🔥 매수 타점!!":
            with st.container():
                st.error(f"🎯 **{sig}** ｜ {card_header}")
                st.markdown(card_body)
                st.markdown("---")
        elif sig == "🚨 익절/청산":
            with st.container():
                st.warning(f"🚨 **{sig}** ｜ {card_header}")
                st.markdown(card_body)
                st.markdown("---")
        else:
            with st.container():
                st.success(f"🍏 **{sig}** ｜ {card_header}")
                st.markdown(card_body)
                st.markdown("---")
else:
    st.info("💡 사이드바를 통해 분석을 진행할 종목을 추가해 주세요.")

# =================================================================
# 🔄 초단위 자동 인코딩 무한루프 엔진 (1.2초 간격 리프레시)
# =================================================================
time.sleep(1.2)
st.rerun()
