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

# 📂 업종 구분 없이 전체 시장에서 추적할 주도주 마스터 데이터 Pool
# (추적 대상을 전체적으로 통합 비교하기 위해 단일 딕셔너리로 병합)
STOCK_MASTER_POOL = {
    "005930": ("삼성전자", "반도체/테크"), "000660": ("SK하이닉스", "반도체/테크"), 
    "009150": ("삼성전기", "반도체/테크"), "066570": ("LG전자", "반도체/테크"), 
    "018260": ("삼성에스디에스", "반도체/테크"), "036570": ("엔씨소프트", "반도체/테크"),
    "207940": ("삼성바이오로직스", "바이오/헬스"), "068270": ("셀트리온", "바이오/헬스"), 
    "091990": ("셀트리온제약", "바이오/헬스"), "028260": ("삼성물산", "바이오/헬스"), 
    "112610": ("씨젠", "바이오/헬스"), "319660": ("피엔에이치테크", "바이오/헬스"),
    "373220": ("LG에너지솔루션", "2차전지/신소재"), "051910": ("LG화학", "2차전지/신소재"), 
    "006400": ("삼성SDI", "2차전지/신소재"), "247540": ("에코프로비엠", "2차전지/신소재"), 
    "086520": ("에코프로", "2차전지/신소재"), "005490": ("POSCO홀딩스", "2차전지/신소재"),
    "005380": ("현대차", "자동차/중공업"), "000270": ("기아", "자동차/중공업"), 
    "012330": ("현대모비스", "자동차/중공업"), "009540": ("HD현대중공업", "자동차/중공업"), 
    "010950": ("S-Oil", "자동차/중공업"), "011780": ("금호석유", "자동차/중공업"),
    "035420": ("NAVER", "플랫폼/엔터"), "035720": ("카카오", "플랫폼/엔터"), 
    "253450": ("스튜디오드래곤", "플랫폼/엔터"), "403870": ("포바이포", "플랫폼/엔터"), 
    "352820": ("하이브", "플랫폼/엔터"), "035900": ("JYP Ent.", "플랫폼/엔터")
}

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
            res = requests.get(url, headers=headers, timeout=2)
            
            if res.status_code != 200 or "result" not in res.json().get("chart", {}):
                yahoo_ticker = f"{clean_ticker}.KS"
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
                res = requests.get(url, headers=headers, timeout=2)
                
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

# --- 웹 대시보드 인터페이스 초기화 및 설정 ---
st.set_page_config(page_title="시장 통합 단타 스캐너", layout="centered")

st.markdown("### 🏹 전시장 통합 수급 돌파 스캐너 (TOP 30)")
st.caption(f"⏱️ 전체 실시간 스트리밍 및 실시간 랭킹 실현 중... ({datetime.now().strftime('%H:%M:%S')})")

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if st.button("🔑 데이터 버퍼 초기화", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.rerun()

# --- 🌟 [변경] 업종별 제한을 풀고 시장 전체 종목 일괄 연산 처리 ---
summary_rows = []
total_accumulated_ticks = [] 

for ticker, (name, ref_sector) in STOCK_MASTER_POOL.items():
    # 기저 데이터 빌드
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

    # 초단위 실시간 체결 데이터 버퍼 업데이트
    live_tick = api.get_realtime_price(ticker)
    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    total_accumulated_ticks.append(len(st.session_state.multi_market_data[ticker]))

    # 퀀트 연산 및 핵심 정렬 데이터 산출
    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    # 실시간 거래대금 산출 (현재가 * 당일 누적 거래량)
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    # 신호별 우선순위 가중치 부여 (매수 타점발생이 무조건 0순위로 상단에 표출)
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산":
        signal_weight = 1

    summary_rows.append({
        "참조 업종": ref_sector,
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

# --- 🌟 [정밀 통합 정렬 및 TOP 30 컷오프 처리] ---
# 1순위: 매수타점 여부순(신호가중치 오름차순), 2순위: 거래대금 크기순(내림차순)으로 전체 일괄 정렬
summary_df = pd.DataFrame(summary_rows)
summary_df = summary_df.sort_values(
    by=['신호가중치', '실시간거래대금'], 
    ascending=[True, False]
).head(30).reset_index(drop=True) # 💥 정확히 상위 30개만 선별 절단

# --- 현재 버퍼 데이터 상태 진단 표시 ---
avg_ticks = np.mean(total_accumulated_ticks) if total_accumulated_ticks else 5
data_maturity = min(100, int((avg_ticks / 15.0) * 100))
st.progress(data_maturity / 100.0, text=f"📈 전시장 수급 추적 데이터 축적도: {data_maturity}%")

# --- 30대 주도주 스캐너 전광판 리스트 출력 ---
st.markdown("---")

has_buy_signal = not summary_df[summary_df["신호가중치"] == 0].empty
if has_buy_signal:
    st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

# 선별된 통합 30대 종목을 순위별 카드 출력
for index, row in summary_df.iterrows():
    sig = row["현재 타이밍 신호"]
    rank_idx = index + 1
    card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']}) ｜ `{row['참조 업종']}`"
    card_body = f"💰 **현재가**: {row['현재가']:,}원 ｜ 📈 **RSI**: {row['RSI']} ｜ 📊 **당일 거래대금**: {int(row['실시간거래대금']/100000000):,}억\n\n🍏 **수급선(VWAP)**: {row['수급선']:,}원 ｜ 🛑 **저항선**: {row['저항선']:,}원"
    
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

# =================================================================
# 🔄 초단위 자동 인코딩 무한루프 엔진 (1.5초 간격 랭킹 및 타점 리프레시)
# =================================================================
time.sleep(1.5)
st.rerun()
