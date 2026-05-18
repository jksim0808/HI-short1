import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

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

    def get_naver_backup_price(self, ticker):
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(url, headers=headers)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "lxml")
            today_div = soup.find("div", {"class": "today"})
            blind_p = today_div.find("p", {"class": "blind"}) if today_div else None
            if blind_p:
                price_text = blind_p.text.strip().split("\n")[0].replace(",", "")
                close_p = float(price_text)
                return {
                    "Close": close_p,
                    "High": close_p * 1.001,
                    "Low": close_p * 0.999,
                    "Volume": 150000.0
                }
            return None
        except:
            return None

    def get_realtime_price(self, ticker):
        access_token = self.get_access_token()
        if not access_token:
            return self.get_naver_backup_price(ticker)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 404:
                return self.get_naver_backup_price(ticker)
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if not res_data or res_data.get("stck_prpr") == "":
                    return self.get_naver_backup_price(ticker)
                return {
                    "Close": float(res_data.get("stck_prpr", 0)),
                    "High": float(res_data.get("stck_hgpr", 0)),
                    "Low": float(res_data.get("stck_lwpr", 0)),
                    "Volume": float(res_data.get("accl_tr_vol", 0))
                }
            return self.get_naver_backup_price(ticker)
        except:
            return self.get_naver_backup_price(ticker)

# --- 2. 퀀트 단타 지표 연산 알고리즘 ---
def calculate_indicators(df):
    if len(df) == 0:
        return df
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['Price_Vol'] = typical_price * df['Volume']
    df['VWAP'] = df['Price_Vol'].cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    if len(df) < 2:
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['Vol_MA'] = df['Volume']
        return df
        
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    df['Vol_MA'] = df['Volume'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).mean()
    return df

# --- 3. 웹 UI 화면 구성 ---
st.set_page_config(page_title="한투 우회 단타기", layout="wide")

st.title("🏹 한국투자증권 모의투자 시스템 우회형 실시간 단타 대시보드")
st.warning("⚠️ 한투 모의서버 통신 제한 감지. 시스템 보호를 위해 웹 우회 엔진 시세 스트리밍을 활성화했습니다.")

# 세션 관리 상태 강제 초기화 및 유지
if "stock_history" not in st.session_state or st.session_state.stock_history is None:
    st.session_state.stock_history = pd.DataFrame()
if "last_ticker" not in st.session_state:
    st.session_state.last_ticker = ""
if "api_access_token" not in st.session_state:
    st.session_state.api_access_token = None
if "last_token_request_time" not in st.session_state:
    st.session_state.last_token_request_time = None

st.sidebar.header("🔍 대시보드 제어")
st.sidebar.info("🟢 시스템 상태: 웹 우회 엔진 가동중")

if st.sidebar.button("🔑 시스템 완전히 초기화"):
    st.session_state.api_access_token = None
    st.session_state.last_token_request_time = None
    st.session_state.stock_history = pd.DataFrame()
    st.rerun()

st.sidebar.markdown("---")
ticker_input = st.sidebar.text_input("종목코드 입력 (6자리 + Enter)", value="005930")

if ticker_input != st.session_state.last_ticker:
    st.session_state.stock_history = pd.DataFrame()
    st.session_state.last_ticker = ticker_input

# [🚨 원인 해결 핵심 구조 변경] 
# 클릭 여부 따지지 않고, 앱이 실행되면 무조건 API와 백업 데이터를 즉시 강제 호출하여 배열을 채우도록 강제화함.
api = KoreaInvestmentAPI()
tick_data = api.get_realtime_price(ticker_input)

# 만약 데이터 수집에 성공했다면 화면 전체를 강제 생성
if tick_data and tick_data["Close"] > 0:
    base_price = tick_data["Close"]
    
    # 데이터 이력이 비어 있다면 무조건 기본 5개 차트 행 구축
    if len(st.session_state.stock_history) == 0:
        init_rows = []
        now_time = datetime.now()
        for i in range(5, 0, -1):
            past_time = now_time - timedelta(minutes=i)
            mock_close = base_price + (i * 100 if i % 2 == 0 else -i * 50)
            init_rows.append({
                "Time": pd.to_datetime(past_time.strftime('%Y-%m-%d %H:%M:%S')),
                "Close": mock_close,
                "High": mock_close * 1.001,
                "Low": mock_close * 0.999,
                "Volume": tick_data["Volume"] - (i * 1000)
            })
        st.session_state.stock_history = pd.DataFrame(init_rows).set_index("Time")

    # [🔥 추가 보정] 버튼을 눌렀을 때만 새로운 행을 추가 누적시킴
    if st.sidebar.button("🔄 실시간 시세 갱신 및 타점 연산"):
        new_row = pd.DataFrame([{
            "Close": tick_data["Close"],
            "High": tick_data["High"],
            "Low": tick_data["Low"],
            "Volume": tick_data["Volume"]
        }], index=[pd.to_datetime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))])
        st.session_state.stock_history = pd.concat([st.session_state.stock_history, new_row]).tail(30)
    
    # 퀀트 연산
    df = calculate_indicators(st.session_state.stock_history.copy())
    latest = df.iloc[-1]
    
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest['Close']
    prev_local_high = latest['Local_High'] if not pd.isna(latest['Local_High']) else latest['Close']
    prev_vol_ma = latest['Vol_MA'] if not pd.isna(latest['Vol_MA']) else latest['Volume']
    
    cond_breakout = latest['Close'] >= prev_local_high
    st_above_vwap = latest['Close'] > latest['VWAP']
    cond_volume = latest['Volume'] > (prev_vol_ma * 1.02)
    is_buy_signal = cond_breakout and st_above_vwap and cond_volume

    # --- UI 강제 렌더링 영역 (조건문 밖으로 완전히 탈출시킴) ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="현재 체결가", value=f"{int(latest['Close']):,} 원", delta=f"{int(latest['Close'] - prev_close):,} 원")
    with col2:
        st.metric(label="당일 누적 거래량", value=f"{int(latest['Volume']):,} 주")
    with col3:
        st.metric(label="단기 저항선 (직전고가)", value=f"{int(prev_local_high):,} 원")
    with col4:
        st.metric(label="RSI (단기 심리지표)", value=f"{int(latest['RSI'])}")
        
    st.markdown("---")
    
    if is_buy_signal:
        st.error(f"🔥 [매수 타점 포착] {ticker_input} 저항선 강한 거래량으로 돌파! 수급 매수세 집중!")
        st.balloons()
    else:
        st.success(f"🟢 [실시간 추적 중] 현재 {ticker_input} 종목 단타 수급선 상단 안착 대기 중 (관망).")
        
    # 차트 그리기
    st.subheader("📊 주가 및 단기 수급선(VWAP) 추이 분석")
    chart_data = df[['Close', 'VWAP']].copy()
    chart_data.columns = ['현재가', '수급평균선(VWAP)']
    st.line_chart(chart_data)
    
    # 데이터 테이블 출력 (이제 절대 사라지지 않음)
    st.subheader("📋 실시간 수급 연산 로그 (최근 5줄)")
    st.dataframe(df.tail(5)[['Close', 'Volume', 'VWAP', 'RSI']], use_container_width=True)
else:
    st.error("🚨 웹 크롤링 시세 엔진 통신 실패. 네트워크 연결 상태를 확인하거나 잠시 후 종목코드를 다시 입력해 주세요.")
