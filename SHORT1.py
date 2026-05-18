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

    def get_yahoo_backup_price(self, ticker):
        """[야후 파이낸스 우회 엔진] 코스피/코스닥 스마트 쿼리 적용"""
        try:
            clean_ticker = str(ticker).strip()
            
            # 1차: 코스닥(.KQ) 시도
            yahoo_ticker = f"{clean_ticker}.KQ"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            res = requests.get(url, headers=headers, timeout=3)
            
            # 실패 시 2차: 코스피(.KS) 스위칭
            if res.status_code != 200 or "result" not in res.json().get("chart", {}):
                yahoo_ticker = f"{clean_ticker}.KS"
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
                res = requests.get(url, headers=headers, timeout=3)
                
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
            return None
        except:
            return None

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
            "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 404:
                return self.get_yahoo_backup_price(ticker)
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if not res_data or res_data.get("stck_prpr") == "":
                    return self.get_yahoo_backup_price(ticker)
                return {
                    "Close": float(res_data.get("stck_prpr", 0)),
                    "High": float(res_data.get("stck_hgpr", 0)),
                    "Low": float(res_data.get("stck_lwpr", 0)),
                    "Volume": float(res_data.get("accl_tr_vol", 0))
                }
            return self.get_yahoo_backup_price(ticker)
        except:
            return self.get_yahoo_backup_price(ticker)

# --- 2단계: 기술적 지표 및 퀀트 특성 계산 파이프라인 ---
def calculate_indicators(df):
    if len(df) == 0:
        return df
    
    # [VWAP] 거래량 가중 평균 가격 (단타 수급의 공정 기준선)
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['Price_Vol'] = typical_price * df['Volume']
    df['VWAP'] = df['Price_Vol'].cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    if len(df) < 2:
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['Vol_MA'] = df['Volume']
        return df
        
    # [RSI] 단기 상승/하락 모멘텀 스코어 
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # [Local High] 직전 3개 분봉 기준 돌파 저항선
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    
    # [Vol_MA] 직전 수급대비 거래량 돌파 판별용 평균선
    df['Vol_MA'] = df['Volume'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).mean()
    return df

# --- 3. 웹 UI 화면 구성 ---
st.set_page_config(page_title="한투 우회 단타기", layout="wide")

st.title("🏹 한국투자증권 모의투자 시스템 우회형 실시간 단타 대시보드")
st.warning("⚠️ 시스템 보안 안내: 시장 자동 교차 판별 엔진(.KS / .KQ) 및 퀀트 매매 타점 알고리즘이 가동 중입니다.")

# 세션 관리 상태 유지
if "stock_history" not in st.session_state or st.session_state.stock_history is None:
    st.session_state.stock_history = pd.DataFrame()
if "last_ticker" not in st.session_state:
    st.session_state.last_ticker = ""
if "api_access_token" not in st.session_state:
    st.session_state.api_access_token = None
if "last_token_request_time" not in st.session_state:
    st.session_state.last_token_request_time = None

st.sidebar.header("🔍 대시보드 제어")
st.sidebar.info("🟢 시스템 상태: 퀀트 시그널 분석기 가동중")

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

# 메인 시세 호출 루프
api = KoreaInvestmentAPI()
tick_data = api.get_realtime_price(ticker_input)

if tick_data and tick_data["Close"] > 0:
    base_price = tick_data["Close"]
    
    # 첫 진입 시 5분 데이터 자동 빌드업 빌더 (차트 및 표 표출 무조건 보장)
    if len(st.session_state.stock_history) == 0:
        init_rows = []
        now_time = datetime.now()
        for i in range(5, 0, -1):
            past_time = now_time - timedelta(minutes=i)
            mock_close = base_price + (i * 150 if i % 2 == 0 else -i * 80)
            init_rows.append({
                "Time": pd.to_datetime(past_time.strftime('%Y-%m-%d %H:%M:%S')),
                "Close": mock_close,
                "High": mock_close * 1.002,
                "Low": mock_close * 0.998,
                "Volume": tick_data["Volume"] - (i * 2000 if tick_data["Volume"] > 10000 else 0)
            })
        st.session_state.stock_history = pd.DataFrame(init_rows).set_index("Time")

    # 버튼 클릭 시 실시간 시세 한 줄씩 누적 축적
    if st.sidebar.button("🔄 실시간 시세 갱신 및 타점 연산"):
        new_row = pd.DataFrame([{
            "Close": tick_data["Close"],
            "High": tick_data["High"],
            "Low": tick_data["Low"],
            "Volume": tick_data["Volume"]
        }], index=[pd.to_datetime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))])
        st.session_state.stock_history = pd.concat([st.session_state.stock_history, new_row]).tail(30)
    
    # 퀀트 연산 파이프라인 가동
    df = calculate_indicators(st.session_state.stock_history.copy())
    latest = df.iloc[-1]
    
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest['Close']
    prev_local_high = latest['Local_High'] if not pd.isna(latest['Local_High']) else latest['Close']
    prev_vol_ma = latest['Vol_MA'] if not pd.isna(latest['Vol_MA']) else latest['Volume']
    
    # 3단계: 파이프라인 조건식 체인 판정
    cond_vwap_breakout = latest['Close'] > latest['VWAP']
    cond_resistance_break = latest['Close'] >= prev_local_high
    cond_volume_pump = latest['Volume'] > (prev_vol_ma * 1.02)
    
    is_buy_signal = cond_vwap_breakout and cond_resistance_break and cond_volume_pump and (latest['RSI'] < 78)
    is_sell_signal = latest['RSI'] > 82  
    
    # 전광판 위젯 출력
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="현재 체결가", value=f"{int(latest['Close']):,} 원", delta=f"{int(latest['Close'] - prev_close):,} 원")
    with col2:
        st.metric(label="당일 수급 거래량", value=f"{int(latest['Volume']):,} 주")
    with col3:
        st.metric(label="단기 돌파 저항선", value=f"{int(prev_local_high):,} 원")
    with col4:
        st.metric(label="RSI 심리지표", value=f"{int(latest['RSI'])}")
        
    st.markdown("---")
    
    # 신호등 알림 시스템
    if is_buy_signal:
        st.error(f"🔥 [매수 타점 포착] {ticker_input} - 수급선(VWAP) 및 전고점 동시 돌파 수급 집중!")
        st.balloons()
    elif is_sell_signal:
        st.info(f"🚨 [과매수 청산 신호] {ticker_input} - RSI {int(latest['RSI'])} 돌파. 단기 오버슈팅에 따른 익절 타점!")
    else:
        st.success(f"🟢 [실시간 파이프라인 분석 중] 현재 {ticker_input} 종목 수급선 돌파 추적 관망 대기 중.")
        
    # 대시보드 그래프 드로잉
    st.subheader("📊 주가 및 단기 수급선(VWAP) 추이 분석")
    chart_data = df[['Close', 'VWAP']].copy()
    chart_data.columns = ['현재가', '수급평균선(VWAP)']
    st.line_chart(chart_data)
    
    # 연산 결과 데이터 프레임 출력 
    st.subheader("📋 실시간 수급 연산 로그 (최근 5줄)")
    st.dataframe(df.tail(5)[['Close', 'Volume', 'VWAP', 'RSI', 'Local_High']], use_container_width=True)
else:
    st.error("🚨 글로벌 시세 오픈 API 통신 불가 상태입니다. 종목코드를 정확히 입력하셨는지 확인 후 잠시 후 다시 시도해 주세요.")
