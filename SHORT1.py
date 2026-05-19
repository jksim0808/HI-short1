import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =================================================================
# 🔑 [한투 실전 규격] Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (보안 통과 헤더 보강)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        # 오직 실전투자 공식 표준 주소만 타깃팅합니다.
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        # 한투 방화벽 통과를 위한 크롬 표준 브라우저 헤더 위장
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.session = requests.Session()

    def get_access_token(self):
        """실전투자 서버 인증 토큰 발급 및 캐싱"""
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            if "token_expire_time" in st.session_state and datetime.now() < st.session_state.token_expire_time:
                return st.session_state.api_access_token
        
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            # 한투 실전 서버가 요구하는 필수 표준 콘텐츠 타입 지정
            headers = {
                "content-type": "application/json; charset=UTF-8",
                "User-Agent": self.user_agent
            }
            data = {
                "grant_type": "client_credentials", 
                "appkey": self.app_key, 
                "appsecret": self.app_secret
            }
            
            response = self.session.post(url, headers=headers, json=data, timeout=5.0)
            
            if response.status_code != 200:
                st.session_state.last_api_error = (
                    f"🚨 [실전 인증 실패] 한투 서버가 연결을 거부했습니다. (HTTP {response.status_code})\n\n"
                    f"💡 **해결책**: Streamlit Web 관리자 화면의 `Settings` -> `Secrets`에 오타나 앞뒤 공백(스페이스바)이 들어갔는지 꼭 확인해 주십시오."
                )
                return None
                
            res_json = response.json()
            token = res_json.get("access_token")
            if token:
                st.session_state.api_access_token = token
                # 한투 토큰은 24시간 유효하지만 안전하게 11시간으로 캐싱 설정
                st.session_state.token_expire_time = datetime.now() + timedelta(hours=11)
                return token
            
            st.session_state.last_api_error = f"🚨 [인증 거절] 서버 메시지: {res_json.get('msg1')}"
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [인증 시스템 시스템 오류] {str(e)}"
            return None

    def get_realtime_price(self, ticker):
        """실전 국내주식 현재가 시세 호출 (TR_ID: FHKST01010200)"""
        access_token = self.get_access_token()
        if not access_token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200", # 실전 주식 시세조회 고유 TR ID
            "custtype": "P",           # 개인 고객 설정 필수
            "User-Agent": self.user_agent
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # J: 주식/ETF 시장구분
            "FID_INPUT_ISCD": str(ticker).strip()
        }
        
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=5.0)
            
            if response.status_code != 200:
                st.session_state.last_api_error = f"🚨 [시세 호출 실패] 실전 주소 통신 이상 (HTTP {response.status_code})"
                return None
                
            res_json = response.json()
            if res_json.get("rt_cd", "0") != "0":
                st.session_state.last_api_error = f"🚨 [실전 조회 거절] {get_stock_name(ticker)}: {res_json.get('msg1')}"
                return None
                
            res_data = res_json.get("output", {})
            if res_data and res_data.get("stck_prpr"):
                current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                
                raw_vol = str(res_data.get("accl_tr_vol", "1.0")).strip()
                volume = float(raw_vol) if raw_vol and raw_vol != "0" else 1.0
                
                return {
                    "Close": current_price, "High": high_price, "Low": low_price,
                    "Volume": volume, "Source": "🔥 한투 실전망 직결 성공"
                }
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [시세 예외 오류] {str(e)}"
            return None

# =================================================================
# 🏷️ 종목 마스터 데이터 관리
# =================================================================
STOCK_NAME_MAP = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아"
}

def get_stock_name(ticker):
    return STOCK_NAME_MAP.get(ticker, f"종목({ticker})")

def process_quant_signals(df):
    """실전 퀀트 수급 돌파 알고리즘"""
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
    
    signals = []
    for idx in range(len(df)):
        if idx < 1: signals.append("🟢 관망"); continue
        c_row = df.iloc[idx]
        p_local_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol_ma = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        if (c_row['Close'] > c_row['VWAP']) and (c_row['Close'] >= p_local_high) and (c_row['Volume'] > p_vol_ma * 1.02) and (c_row['RSI'] < 78):
            signals.append("🔥 매수 타점!!")
        elif c_row['RSI'] > 82: signals.append("🚨 익절/청산")
        else: signals.append("🟢 관망")
    df['타이밍 신호'] = signals
    return df

# =================================================================
# 🖥️ UI 및 제어 대시보드
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너", layout="centered")

st.sidebar.markdown("### 📋 종목 관리")
raw_input_tickers = st.sidebar.text_area("종목코드 입력", placeholder="예: 005930", height=70)

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = ["005930", "000660", "005380", "000270"]
if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}
if "last_api_error" not in st.session_state:
    st.session_state.last_api_error = None

if st.sidebar.button("⚡ 종목 등록", use_container_width=True):
    if raw_input_tickers.strip():
        clean_tickers = [t.strip() for t in raw_input_tickers.split() if len(t.strip()) == 6]
        if clean_tickers:
            st.session_state.custom_stock_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.rerun()

st.markdown("### 🏹 실전 수급 돌파 스캐너 (공식 표준 수동 모드)")
st.caption(f"💡 현재 화면 데이터 시점: {datetime.now().strftime('%H:%M:%S')} | 📡 가동모드: 실전매매 전용")

if st.session_state.last_api_error:
    st.error(st.session_state.last_api_error)
else:
    st.info("🟢 통신 상태: 실전망 가동 준비 완료 (조회 버튼을 누르면 실시간 시세를 호출합니다)")

col_btn1, col_btn2 = st.columns(2)
click_refresh = col_btn1.button("🔥 [클릭] 한투 실시간 시세 조회/갱신", type="primary", use_container_width=True)

if col_btn2.button("🧹 캐시 메모리 청소", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.session_state.last_api_error = None
    if "api_access_token" in st.session_state: 
        del st.session_state["api_access_token"]
    st.rerun()

if not APP_KEY or not APP_SECRET:
    st.warning("⚠️ Streamlit Secrets 보관함에 실전투자 전용 앱키 세팅이 완침되지 않았습니다.")

# =================================================================
# ⚙️ 실시간 데이터 프로세싱 파이프라인
# =================================================================
api = KoreaInvestmentOfficialAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if click_refresh:
    st.session_state.last_api_error = None
    for ticker in st.session_state.custom_stock_pool:
        live_tick = api.get_realtime_price(ticker)
        
        if live_tick and live_tick["Close"] > 0:
            if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
                init_rows = []
                init_times = []
                base_p = live_tick["Close"]
                for i in range(5, 0, -1):
                    time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
                    init_times.append(pd.to_datetime(time_str))
                    init_rows.append({"Close": base_p, "High": base_p, "Low": base_p, "Volume": live_tick["Volume"]})
                st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)
            
            new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
            st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
            st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

summary_rows = []
for ticker in st.session_state.custom_stock_pool:
    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        init_rows = []
        init_times = []
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            init_rows.append({"Close": 50000.0, "High": 50000.0, "Low": 50000.0, "Volume": 0.0})
        df_frame = pd.DataFrame(init_rows, index=init_times)
        data_source_text = "🛑 대기중"
    else:
        df_frame = st.session_state.multi_market_data[ticker].copy()
        data_source_text = live_tick["Source"] if 'live_tick' in locals() and live_tick else "실전 연결 완료"

    calculated_df = process_quant_signals(df_frame)
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!": signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산": signal_weight = 1

    summary_rows.append({
        "종목코드": ticker, "종목명": get_stock_name(ticker), "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']), "수급선": int(latest_info['VWAP']), "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']), "실시간거래대금": realtime_trading_value, "신호가중치": signal_weight,
        "데이터출처": data_source_text
    })

st.markdown("---")

# =================================================================
# 🖥️ 결과 출력 대시보드
# =================================================================
if summary_rows:
    summary_df = pd.DataFrame(summary_rows).sort_values(by=['신호가중치', '실시간거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if click_refresh and not summary_df[summary_df["신호가중치"] == 0].empty:
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
                st.error(f"🎯 **{sig}**\n\n{card_header}\n\n{card_body}")
                st.markdown("---")
        elif sig == "🚨 익절/청산":
            with st.container(): 
                st.warning(f"🚨 **{sig}**\n\n{card_header}\n\n{card_body}")
                st.markdown("---")
        else:
            with st.container(): 
                st.success(f"🍏 **{sig}**\n\n{card_header}\n\n{card_body}")
                st.markdown("---")
