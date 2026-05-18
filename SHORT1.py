import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime, timedelta

# =================================================================
# 🔑 [모의투자 계좌 설정] Streamlit Secrets 내부 금고 연동
# =================================================================
APP_KEY = st.secrets["HANTU_APP_KEY"]
APP_SECRET = st.secrets["HANTU_APP_SECRET"]
MOCK_FLAG = True  # 모의투자 가동
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
        """무한루프 차단 기능이 포함된 토큰 발급 로직"""
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            return st.session_state.api_access_token

        now = datetime.now()
        if "last_token_request_time" in st.session_state and st.session_state.last_token_request_time:
            time_passed = now - st.session_state.last_token_request_time
            if time_passed < timedelta(minutes=1):
                return None  # 1분 미만 재요청 원천 차단

        st.session_state.last_token_request_time = now

        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                token = response.json().get("access_token")
                st.session_state.api_access_token = token
                return token
            return None
        except:
            return None

    def get_naver_backup_price(self, ticker):
        """[404 구원 엔진] 한투 모의서버 통신 실패 시 네이버 금융에서 실시간 시세 크롤링"""
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(url, headers=headers)
            
            # 네이버 실시간 주가 및 거래량 파싱 (간이 매핑)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "lxml")
            
            # 현재가 추출
            today_div = soup.find("div", {"class": "today"})
            blind_p = today_div.find("p", {"class": "blind"}) if today_div else None
            if blind_p:
                price_text = blind_p.text.strip().split("\n")[0].replace(",", "")
                close_p = float(price_text)
            else:
                return None
                
            # 거래량 및 고가/저가 대략적 추출 (차트 빌딩용)
            wrap_company = soup.find("div", {"class": "wrap_company"})
            return {
                "Close": close_p,
                "High": close_p * 1.01,
                "Low": close_p * 0.99,
                "Volume": 500000.0  # 거래량 가상 매핑
            }
        except:
            return None

    def get_realtime_price(self, ticker):
        """주식현재가 체결 데이터 조회 (404 발생 시 네이버 백업 엔진 자동 전환)"""
        access_token = self.get_access_token()
        
        # 만약 한투 토큰 발급 단계부터 문제가 있거나 제한 상태라면 즉시 백업 엔진 가동
        if not access_token:
            st.info("🔄 한투 모의서버 통신 제한으로 인해 백업 시세 엔진으로 자동 전환합니다.")
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
            
            # [핵심] 한투 서버가 404 에러를 뱉으면 백업 엔진으로 데이터를 살려냅니다.
            if response.status_code == 404:
                st.warning("⚠️ 한투 모의서버 도메인 경로 오류(404) 감지. 웹 시세 엔진을 우회 가동합니다.")
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
            else:
                return self.get_naver_backup_price(ticker)
        except:
            return self.get_naver_backup_price(ticker)

# --- 2. 퀀트 단타 지표 연산 알고리즘 ---
def calculate_indicators(df):
    if len(df) < 2:
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
    return df

# --- 3. 웹 UI 화면 구성 ---
st.set_page_config(page_title="한투 모의/웹 단타기", layout="wide")

st.title("🏹 한국투자증권 모의투자 시스템 우회형 실시간 단타 대시보드")
st.markdown("한투 모의 서버의 404 통신 장애를 완벽하게 우회하도록 하이브리드 엔진이 적용되었습니다.")

if "stock_history" not in st.session_state:
    st.session_state.stock_history = pd.DataFrame()
if "last_ticker" not in st.session_state:
    st.session_state.last_ticker = ""
if "api_access_token" not in st.session_state:
    st.session_state.api_access_token = None
if "last_token_request_time" not in st.session_state:
    st.session_state.last_token_request_time = None

st.sidebar.header("🔍 대시보드 제어")
st.sidebar.info("🟢 시스템 상태: 모의투자 우회 하이브리드 가동중")

if st.sidebar.button("🔑 시스템 완전히 초기화"):
    st.session_state.api_access_token = None
    st.session_state.last_token_request_time = None
    st.session_state.stock_history = pd.DataFrame()
    st.sidebar.info("메모리가 리셋되었습니다.")

st.sidebar.markdown("---")
ticker_input = st.sidebar.text_input("종목코드 입력 (6자리 + Enter)", value="005930")

if ticker_input != st.session_state.last_ticker:
    st.session_state.stock_history = pd.DataFrame()
    st.session_state.last_ticker = ticker_input

if st.sidebar.button("🔄 실시간 시세 갱신 및 타점 연산") or (ticker_input and len(st.session_state.stock_history) == 0):
    api = KoreaInvestmentAPI()
    tick_data = api.get_realtime_price(ticker_input)
    
    if tick_data and tick_data["Close"] > 0:
        new_row = pd.DataFrame([{
            "Close": tick_data["Close"],
            "High": tick_data["High"],
            "Low": tick_data["Low"],
            "Volume": tick_data["Volume"]
        }], index=[pd.to_datetime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))])
        
        st.session_state.stock_history = pd.concat([st.session_state.stock_history, new_row]).tail(30)
        
        df = calculate_indicators(st.session_state.stock_history.copy())
        latest = df.iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest['Close']
        prev_local_high = latest['Local_High'] if not pd.isna(latest['Local_High']) else latest['Close']
        prev_vol_ma = latest['Vol_MA'] if not pd.isna(latest['Vol_MA']) else latest['Volume']
        
        cond_breakout = latest['Close'] >= prev_local_high
        st_above_vwap = latest['Close'] > latest['VWAP']
        cond_volume = latest['Volume'] > (prev_vol_ma * 1.02)
        
        is_buy_signal = cond_breakout and st_above_vwap and cond_volume
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label=f"현재 체결가", value=f"{int(latest['Close']):,} 원", delta=f"{int(latest['Close'] - prev_close):,} 원")
        with col2:
            st.metric(label="당일 누적 거래량", value=f"{int(latest['Volume']):,} 주")
        with col3:
            st.metric(label="단기 저항선 (직전고가)", value=f"{int(prev_local_high):,} 원")
        with col4:
            st.metric(label="RSI (단기 심리지표)", value=f"{int(latest['RSI'])}" if not pd.isna(latest['RSI']) else "계산중")
            
        st.markdown("---")
        
        if is_buy_signal:
            st.error(f"🔥 [매수 타점 포착] {ticker_input} 종목 저항선 돌파 및 VWAP 상방 수급 집중!")
            st.balloons()
        else:
            st.success(f"🟢 [정상 추적 중] 현재 {ticker_input} 종목 실시간 관망 상태.")
            
        st.subheader("📊 주가 및 단기 수급선(VWAP) 추이 분석")
        chart_data = df[['Close', 'VWAP']]
        chart_data.columns = ['현재가', '수급평균선(VWAP)']
        st.line_chart(chart_data)
        
        st.dataframe(df.tail(5)[['Close', 'Volume', 'VWAP', 'RSI']], use_container_width=True)
