import streamlit as st
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from datetime import datetime, timedelta
import time

# =================================================================
# 🔑 [실전투자 계좌 설정] Streamlit Secrets 내부 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "YOUR_APP_KEY")
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "YOUR_APP_SECRET")

# =================================================================
# 🏦 한국투자증권 실전 API 전용 강력 통신 엔진 (토큰 세션 고정형)
# =================================================================
class KoreaInvestmentAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_access_token(self):
        """ [완벽 튜닝] 발급받은 토큰을 지우지 않고 만료 전까지 철저히 뼈를 발라 재사용 """
        # 1. 이미 발급받은 토큰과 만료 시간이 메모리에 남아있다면 즉시 그것을 반환 (한투 요청 차단)
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            if "token_expire_time" in st.session_state and datetime.now() < st.session_state.token_expire_time:
                return st.session_state.api_access_token
        
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {
                "content-type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            
            response = self.session.post(url, headers=headers, json=data, timeout=5.0)
            if response.status_code == 200:
                res_json = response.json()
                token = res_json.get("access_token")
                
                # 💡 한투 토큰은 유효기간이 24시간입니다. 넉넉하게 12시간 동안은 절대로 한투에 재요청 안 하도록 잠금.
                st.session_state.api_access_token = token
                st.session_state.token_expire_time = datetime.now() + timedelta(hours=12)
                return token
            else:
                # 1분 제한 걸렸을 때 화면에 빨간 에러 다발로 도배되는 것을 방지하기 위해 묵묵히 기존 캐시 토큰 사용 시도
                if "api_access_token" in st.session_state:
                    return st.session_state.api_access_token
                return None
        except Exception as e:
            if "api_access_token" in st.session_state:
                return st.session_state.api_access_token
            return None

    def get_realtime_price(self, ticker):
        access_token = self.get_access_token()
        if not access_token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200", 
            "custtype": "P",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", 
            "FID_INPUT_ISCD": str(ticker).strip()
        }
        
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=5.0)

            if response.status_code == 200:
                res_json = response.json()
                rt_cd = res_json.get("rt_cd", "0")
                
                # 토큰 만료 에러나 재인증이 필요하다는 메시지가 수신되면 그때만 토큰 비우기
                if rt_cd != "0":
                    msg_cd = res_json.get("msg_cd", "")
                    if msg_cd in ["EGW00001", "EGW00002", "ISC00002"]: # 토큰 무효 관련 코드들
                        st.session_state.api_access_token = None
                    return None

                res_data = res_json.get("output", {})
                if res_data and res_data.get("stck_prpr"):
                    current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                    high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                    low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                    volume = float(str(res_data.get("accl_tr_vol", 0)).strip())
                    
                    return {
                        "Close": current_price,
                        "High": high_price,
                        "Low": low_price,
                        "Volume": volume if volume > 0 else 1000.0,
                        "Source": "한투 실전 호가 고정"
                    }
            return None
        except Exception as e:
            return None

# =================================================================
# 🏷️ 국내 주요 대형주 마스터 딕셔너리
# =================================================================
STOCK_NAME_MAP = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "035420": "NAVER", "035720": "카카오", "068270": "셀트리온", "373220": "LG에너지솔루션",
    "207940": "삼성바이오로직스", "051910": "LG화학", "006400": "삼성SDI", "003550": "LG",
    "005490": "POSCO홀딩스", "010140": "삼성중공업", "009540": "HD현대중공업", "105560": "KB금융",
    "055550": "신한지주", "000810": "삼성화재", "015760": "한국전력", "028260": "삼성물산",
    "247540": "에코프로비엠", "086520": "에코프로", "091500": "삼성전기", "352820": "하이브"
}

def get_stock_name(ticker):
    return STOCK_NAME_MAP.get(ticker, f"종목({ticker})")

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

# =================================================================
# 🖥️ 모바일 웹 대시보드 인터페이스 영역
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너", layout="centered")

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = ["005930", "000660", "005380", "000270", "035420", "068270"]

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

st.sidebar.markdown("### 📋 종목 번호 입력")
raw_input_tickers = st.sidebar.text_area("종목코드 멀티 입력", placeholder="예: 005930 000660", height=90)

if st.sidebar.button("⚡ 종목 등록 및 동기화", use_container_width=True):
    if raw_input_tickers.strip():
        parsed_tickers = raw_input_tickers.replace(",", " ").replace("\n", " ").split()
        clean_tickers = [t.strip() for t in parsed_tickers if len(t.strip()) == 6 and t.strip().isdigit()]
        if clean_tickers:
            st.session_state.custom_stock_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.sidebar.success("추가 완료!")
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.write(f"🔍 실시간 감시 목록 ({len(st.session_state.custom_stock_pool)}개)")

delete_target = None
for tk in list(st.session_state.custom_stock_pool):
    col1, col2 = st.sidebar.columns([4, 1])
    col1.caption(f"▪️ {get_stock_name(tk)}")
    if col2.button("❌", key=f"del_{tk}"): delete_target = tk

if delete_target:
    st.session_state.custom_stock_pool.remove(delete_target)
    if delete_target in st.session_state.multi_market_data: del st.session_state.multi_market_data[delete_target]
    st.rerun()

st.markdown("### 🏹 실전 수급 돌파 스캐너")
st.caption(f"⏱️ 한투 실전 서버 데이터 연동 중... ({datetime.now().strftime('%H:%M:%S')})")

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 💡 이제 이 버튼은 토큰을 강제로 지우지 않고 순수 데이터 버퍼만 초기화합니다. (1분 제한 차단용)
if st.button("🔑 버퍼 및 캐시 비우기 (오류 초기화)", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.rerun()

summary_rows = []

for ticker in st.session_state.custom_stock_pool:
    live_tick = api.get_realtime_price(ticker)
    
    if not live_tick:
        live_tick = {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0, "Source": "⚠️ 한투 제한 대기중"}

    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        init_rows = []
        init_times = []
        base_p = live_tick["Close"] if live_tick["Close"] > 0 else 50000.0
        
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            mock_p = base_p + (i * 10 if i % 2 == 0 else -i * 5)
            init_rows.append({"Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": live_tick["Volume"]})
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!": signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산": signal_weight = 1

    summary_rows.append({
        "종목코드": ticker, "종목명": get_stock_name(ticker), "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']), "수급선": int(latest_info['VWAP']), "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']), "실시간거래대금": realtime_trading_value, "신호가중치": signal_weight,
        "데이터출처": live_tick.get("Source", "통신 대기")
    })

st.markdown("---")

if summary_rows:
    summary_df = pd.DataFrame(summary_rows).sort_values(by=['신호가중치', '실시간거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank_idx = index + 1
        card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']}) | 📌 `출처: {row['데이터출처']}`"
        display_money = int(row['실시간거래대금']/100000000) if row['실시간거래대금'] > 0 else 0
        
        card_body = (
            f"💵 **현재가**: {row['현재가']:,}원\n\n"
            f"🔥 **RSI**: {row['RSI']} | 📊 **당일대금**: {display_money:,}억\n\n"
            f"🍏 **수급**: {row['수급선']:,}원 | 🛑 **저항**: {row['저항선']:,}원"
        )
        
        if sig == "🔥 매수 타점!!":
            with st.container():
                st.error(f"🎯 **{sig}**\n\n{card_header}"); st.markdown(card_body); st.markdown("---")
        elif sig == "🚨 익절/청산":
            with st.container():
                st.warning(f"🚨 **{sig}**\n\n{card_header}"); st.markdown(card_body); st.markdown("---")
        else:
            with st.container():
                st.success(f"🍏 **{sig}**\n\n{card_header}"); st.markdown(card_body); st.markdown("---")

# 한투 초당 호출 제한(TPS) 안전 구역 확보를 위해 리프레시를 3초로 상향
time.sleep(3.0)
st.rerun()
