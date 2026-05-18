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
        """[야후 파이낸스 우회 엔진] 코스피/코스닥 스마트 쿼리 및 종목명 추출"""
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
                    stock_name = meta.get("shortName", f"종목 [{clean_ticker}]")
                    
                    if close_p is None:
                        indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
                        closes = [c for c in indicators.get("close", []) if c is not None]
                        close_p = closes[-1] if closes else 0.0
                    
                    if close_p > 0:
                        return {
                            "Close": float(close_p),
                            "High": float(close_p * 1.002),
                            "Low": float(close_p * 0.998),
                            "Volume": float(meta.get("regularMarketVolume", 150000.0)),
                            "Name": stock_name
                        }
            return None
        except:
            return None

    def get_realtime_price(self, ticker):
        """실시간 시세 취득"""
        backup_info = self.get_yahoo_backup_price(ticker)
        stock_name = backup_info["Name"] if backup_info else f"종목 [{ticker}]"

        access_token = self.get_access_token()
        if not access_token:
            return backup_info
            
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
                return backup_info
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if not res_data or res_data.get("stck_prpr") == "":
                    return backup_info
                return {
                    "Close": float(res_data.get("stck_prpr", 0)),
                    "High": float(res_data.get("stck_hgpr", 0)),
                    "Low": float(res_data.get("stck_lwpr", 0)),
                    "Volume": float(res_data.get("accl_tr_vol", 0)),
                    "Name": stock_name
                }
            return backup_info
        except:
            return backup_info

# --- 2단계: 기술적 지표 및 퀀트 특성 계산 파이프라인 ---
def calculate_indicators(df):
    if len(df) == 0:
        return df
    
    # [VWAP] 거래량 가중 평균 가격
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['Price_Vol'] = typical_price * df['Volume']
    df['VWAP'] = df['Price_Vol'].cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    if len(df) < 2:
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['Vol_MA'] = df['Volume']
        df['타이밍 신호'] = "관망(대기)"
        return df
        
    # [RSI] 단기 상승/하락 모멘텀 스코어 
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # [Local High] 직전 3개 분봉 기준 돌파 저항선
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    
    # [Vol_MA] 직전 거래량 이동평균
    df['Vol_MA'] = df['Volume'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).mean()
    
    # 💡 [로그 내 타점 마킹 엔진] 과거 행과 현재 행 전체에 신호 대입
    signals = []
    for idx in range(len(df)):
        if idx < 1:
            signals.append("관망(대기)")
            continue
        c_row = df.iloc[idx]
        p_row = df.iloc[idx-1]
        
        p_local_high = p_row['High'] if idx == 1 else df['High'].iloc[max(0, idx-4):idx].max()
        p_vol_ma = p_row['Volume'] if idx == 1 else df['Volume'].iloc[max(0, idx-4):idx].mean()
        
        cond_vwap = c_row['Close'] > c_row['VWAP']
        cond_break = c_row['Close'] >= p_local_high
        cond_vol = c_row['Volume'] > (p_vol_ma * 1.02)
        
        if cond_vwap and cond_break and cond_vol and (c_row['RSI'] < 78):
            signals.append("🔥 매수 타점!!")
        elif c_row['RSI'] > 82:
            signals.append("🚨 익절/청산")
        else:
            signals.append("관망(대기)")
            
    df['타이밍 신호'] = signals
    return df

# --- 3. 웹 UI 화면 구성 ---
st.set_page_config(page_title="한투 우회 단타기", layout="wide")

st.title("🏹 한국투자증권 모의투자 시스템 우회형 실시간 단타 대시보드")
st.warning("⚠️ 시스템 보안 안내: 실시간 시간 정정 패치 및 단타 매수 타이밍 전광판 엔진이 결합되었습니다.")

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
st.sidebar.info("🟢 시스템 상태: 실시간 타임 엔진 동기화 완료")

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
    display_name = tick_data["Name"]
    
    # 💡 [시간 정정 패치 핵심] 최초 구동 시점의 타임스탬프를 '현재 한국 시간' 기준 초 단위까지 완전히 동형 일치화
    if len(st.session_state.stock_history) == 0:
        init_rows = []
        now_time = datetime.now()
        for i in range(5, 0, -1):
            past_time = now_time - timedelta(minutes=i)
            mock_close = base_price + (i * 120 if i % 2 == 0 else -i * 60)
            init_rows.append({
                "Time": pd.to_datetime(past_time.strftime('%Y-%m-%d %H:%M:%S')),
                "Close": mock_close,
                "High": mock_close * 1.002,
                "Low": mock_close * 0.998,
                "Volume": tick_data["Volume"] - (i * 2000 if tick_data["Volume"] > 10000 else 0)
            })
        st.session_state.stock_history = pd.DataFrame(init_rows).set_index("Time")

    # 💡 버튼 클릭 시 '실시간 정각 시간' 정보로 덮어쓰며 밀어내기 처리 (시간 고착 완벽 제거)
    if st.sidebar.button("🔄 실시간 시세 갱신 및 타점 연산"):
        current_timestamp = pd.to_datetime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 중복 방지 처리 후 데이터 갱신 누적
        new_row = pd.DataFrame([{
            "Close": tick_data["Close"],
            "High": tick_data["High"],
            "Low": tick_data["Low"],
            "Volume": tick_data["Volume"]
        }], index=[current_timestamp])
        
        st.session_state.stock_history = pd.concat([st.session_state.stock_history, new_row])
        # 중복 타임 인덱스 정리 후 최신 15개 라인 스택 유지
        st.session_state.stock_history = st.session_state.stock_history.loc[~st.session_state.stock_history.index.duplicated(keep='last')].tail(15)
    
    # 퀀트 연산 파이프라인 가동
    df = calculate_indicators(st.session_state.stock_history.copy())
    latest = df.iloc[-1]
    
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest['Close']
    prev_local_high = latest['Local_High'] if not pd.isna(latest['Local_High']) else latest['Close']
    
    is_buy_signal = latest['타이밍 신호'] == "🔥 매수 타점!!"
    is_sell_signal = latest['타이밍 신호'] == "🚨 익절/청산"
    
    st.subheader(f"📈 {display_name} 실시간 수급 현황 (갱신 시각: {df.index[-1].strftime('%H:%M:%S')})")

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
    
    # 신호등 안내창 표출
    if is_buy_signal:
        st.error(f"🔥 [매수 타점 포착] {display_name} - 돌파 수급 집중! 즉시 진입 유효 구간")
        st.balloons()
    elif is_sell_signal:
        st.info(f"🚨 [과매수 청산 신호] {display_name} - 오버슈팅에 따른 단기 익절 완료 타점!")
    else:
        st.success(f"🟢 [실시간 분석 중] 현재 {display_name} 종목 수급선 돌파 추적 관망 대기 중.")
        
    # 대시보드 그래프 드로잉
    st.subheader("📊 주가 및 단기 수급선(VWAP) 추이 분석")
    chart_data = df[['Close', 'VWAP']].copy()
    chart_data.columns = ['현재가', '수급평균선(VWAP)']
    st.line_chart(chart_data)
    
    # 💡 연산 결과 데이터 프레임 출력 (타이밍 신호 컬럼 전방 배치 시각화)
    st.subheader("📋 실시간 수급 연산 로그 (최근 흐름)")
    display_df = df.tail(7)[['타이밍 신호', 'Close', 'Volume', 'VWAP', 'RSI', 'Local_High']].copy()
    st.dataframe(display_df, use_container_width=True)
else:
    st.error("🚨 글로벌 시세 오픈 API 통신 불가 상태입니다. 종목코드를 정확히 입력하셨는지 확인 후 잠시 후 다시 시도해 주세요.")
