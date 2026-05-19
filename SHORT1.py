import streamlit as st
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from datetime import datetime, timedelta

# =================================================================
# 🔑 [실전투자 계좌 설정] Streamlit Secrets 내부 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한국투자증권 실전 API 전용 정밀 통신 엔진 (진단기 탑재)
# =================================================================
class KoreaInvestmentAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_access_token(self):
        """ [진단 기능] 토큰 발급 단계에서 한투가 거절하면 에러를 즉시 화면에 박아버립니다. """
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            if "token_expire_time" in st.session_state and datetime.now() < st.session_state.token_expire_time:
                return st.session_state.api_access_token
        
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json", "User-Agent": "Mozilla/5.0"}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            
            response = self.session.post(url, headers=headers, json=data, timeout=4.0)
            res_json = response.json()
            
            if response.status_code == 200:
                token = res_json.get("access_token")
                if token:
                    st.session_state.api_access_token = token
                    st.session_state.token_expire_time = datetime.now() + timedelta(hours=12)
                    return token
            
            # 토큰 발급 실패 시 한투 날것의 에러 메시지 노출
            st.session_state.last_api_error = f"🚨 [토큰 발급 실패] 한투 응답: {res_json}"
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [토큰 네트워크 오류] {str(e)}"
            return None

    def get_realtime_price(self, ticker):
        """ [진단 기능] 시세 조회 단계에서 한투가 거절하면 거절 사유를 실시간 파싱합니다. """
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
            "User-Agent": "Mozilla/5.0"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=3.0)
            res_json = response.json()
            
            if response.status_code == 200:
                # 한투 응답 성공 가부 확인 (rt_cd 가 0이 아니면 에러)
                if res_json.get("rt_cd", "0") != "0":
                    st.session_state.last_api_error = f"🚨 [시세 조회 실패] 코드({ticker}) 한투 응답: {res_json.get('msg1') or res_json}"
                    return None
                    
                res_data = res_json.get("output", {})
                if res_data and res_data.get("stck_prpr"):
                    current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                    high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                    low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                    volume = float(str(res_data.get("accl_tr_vol", 0)).strip())
                    
                    if current_price <= 0: 
                        return None
                        
                    return {
                        "Close": current_price, "High": high_price, "Low": low_price,
                        "Volume": volume if volume > 0 else 10.0, "Source": "한투 실시간 시세"
                    }
            
            st.session_state.last_api_error = f"🚨 [시세 HTTP 오류] 상태코드: {response.status_code} 내용: {res_json}"
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [시세 통신 예외 오류] {str(e)}"
            return None

# =================================================================
# 🏷️ 국내 주요 대형주 마스터 딕셔너리
# =================================================================
STOCK_NAME_MAP = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "035420": "NAVER", "035720": "카카오", "068270": "셀트리온", "373220": "LG에너지솔루션"
}

def get_stock_name(ticker):
    return STOCK_NAME_MAP.get(ticker, f"종목({ticker})")

def process_quant_signals(df):
    if len(df) < 2:
        df['VWAP'] = df['Close']; df['RSI'] = 50.0; df['Local_High'] = df['High']; df['타이밍 신호'] = "🟢 관망"
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
            signals.append("🟢 관망")
            continue
        c_row = df.iloc[idx]
        p_local_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol_ma = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        if (c_row['Close'] > c_row['VWAP']) and (c_row['Close'] >= p_local_high) and (c_row['Volume'] > p_vol_ma * 1.02) and (c_row['RSI'] < 78):
            signals.append("🔥 매수 타점!!")
        elif c_row['RSI'] > 82: 
            signals.append("🚨 익절/청산")
        else: 
            signals.append("🟢 관망")
    df['타이밍 신호'] = signals
    return df

# =================================================================
# 🖥️ 모바일 웹 대시보드 인터페이스 영역
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너", layout="centered")

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = ["005930", "000660", "005380", "000270"]

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

# 진단용 오류 저장소 초기화
if "last_api_error" not in st.session_state:
    st.session_state.last_api_error = None

st.sidebar.markdown("### 📋 종목 관리")
raw_input_tickers = st.sidebar.text_area("종목코드 입력", placeholder="예: 005930", height=70)
if st.sidebar.button("⚡ 종목 등록", use_container_width=True):
    if raw_input_tickers.strip():
        clean_tickers = [t.strip() for t in raw_input_tickers.split() if len(t.strip()) == 6]
        if clean_tickers:
            st.session_state.custom_stock_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.rerun()

st.markdown("### 🏹 실전 수급 돌파 스캐너 (X-Ray 진단 모드)")
st.caption(f"💡 현재 화면 데이터 시점: {datetime.now().strftime('%H:%M:%S')}")

# =================================================================
# 🕵️‍♂️ [실시간 블랙박스 시스템 판넬] 
# =================================================================
if st.session_state.last_api_error:
    st.error(st.session_state.last_api_error)
else:
    st.info("🟢 통신 장비 상태: 특이사항 없음 (정상 대기)")

col_btn1, col_btn2 = st.columns(2)
if col_btn1.button("🔥 [클릭] 한투 실시간 시세 조회/갱신", type="primary", use_container_width=True):
    st.session_state.last_api_error = None  # 누를 때마다 이전 에러 기록 청소 후 재시도
    st.rerun()
if col_btn2.button("🧹 데이터 초기화 (캐시 청소)", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.session_state.last_api_error = None
    st.rerun()

# 비밀키 누락 점검 안전장치
if not APP_KEY or not APP_SECRET:
    st.warning("⚠️ Streamlit Secrets 보관함에 HANTU_APP_KEY 또는 HANTU_APP_SECRET 설정이 누락되었거나 비어있습니다.")

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
summary_rows = []

for ticker in st.session_state.custom_stock_pool:
    live_tick = api.get_realtime_price(ticker)
    
    if not live_tick:
        live_tick = {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 0.0, "Source": "🛑 대기중 (위 버튼을 누르세요)"}

    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        init_rows = []
        init_times = []
        base_p = live_tick["Close"] if live_tick["Close"] > 0 else 50000.0
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            init_rows.append({"Close": base_p, "High": base_p, "Low": base_p, "Volume": 100.0})
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!": 
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산": 
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker, "종목명": get_stock_name(ticker), "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']), "수급선": int(latest_info['VWAP']), "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']), "실시간거래대금": realtime_trading_value, "신호가중치": signal_weight,
        "데이터출처": live_tick.get("Source", "대기 중")
    })

st.markdown("---")

if summary_rows:
    summary_df = pd.DataFrame(summary_rows).sort_values(by=['신호가중치', '실시간거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank_idx = index + 1
        card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']}) | 📌 `상태: {row['데이터출처']}`"
        display_money = int(row['실시간거래대금']/100000000) if row['실시간거래대금'] > 0 else 0
        
        card_body = (
            f"💵 **현재가**: {row['현재가']:,}원\n\n"
            f"🔥 **RSI**: {row['RSI']} | 📊 **당일대금**: {display_money:,}억\n\n"
            f"🍏 **수급**: {row['수급선']:,}원 | 🛑 **저항**: {row['저항선']:,}원"
        )
        
        if sig == "🔥 매수 타점!!":
            with st.container(): 
                st.error(f"🎯 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
        elif sig == "🚨 익절/청산":
            with st.container(): 
                st.warning(f"🚨 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
        else:
            with st.container(): 
                st.success(f"🍏 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
