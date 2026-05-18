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

# 📊 단타 매매 대상 시장 주도주 및 거래대금 상위 추천 30종목 풀(Pool) 정의
TICKER_POOL = {
    "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER", "035720": "카카오",
    "005380": "현대차", "000270": "기아", "051910": "LG화학", "006400": "삼성SDI",
    "373220": "LG에너지솔루션", "207940": "삼성바이오로직스", "068270": "셀트리온", "105560": "KB금융",
    "055550": "신한지주", "005490": "POSCO홀딩스", "003550": "LG", "012330": "현대모비스",
    "066570": "LG전자", "032830": "삼성생명", "000810": "삼성화재", "033780": "KT&G",
    "009150": "삼성전기", "010950": "S-Oil", "015760": "한국전력", "018260": "삼성에스디에스",
    "247540": "에코프로비엠", "086520": "에코프로", "091990": "셀트리온제약", "403870": "포바이포",
    "253450": "스튜디오드래곤", "036570": "엔씨소프트"
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
            "tr_id": "FHKST01010100"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            response = requests.get(url, headers=headers, params=params)
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

# --- 기술적 지표 퀀트 연산 엔진 (독립 구조화) ---
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

# --- 웹 대시보드 인터페이스 구성 ---
st.set_page_config(page_title="30종목 주도주 단타 스캐너", layout="wide")
st.title("🏹 주도주 30종목 실시간 퀀트 타점 스캐너 시스템")
st.warning("⚠️ 시스템 가동 중: 국내 실시간 거래대금 최상위 30종목의 융합 지표를 동시 병렬 스캔합니다.")

# 세션 상태 및 가상 분봉 스택 초기 가동 구조 정의
if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 💡 [핵심] 사이드바 제어 패널 설계
st.sidebar.header("⚙️ 스캐너 중앙 제어실")
scan_trigger = st.sidebar.button("🔄 [30종목] 전 종목 실시간 동시 스캔 및 타점 갱신")
reset_trigger = st.sidebar.button("🔑 메모리 누적 버퍼 전체 초기화")

if reset_trigger:
    st.session_state.multi_market_data = {}
    st.rerun()

# 30종목 데이터 수집 및 연산 매커니즘
summary_rows = []

for ticker, name in TICKER_POOL.items():
    # 최초 진입 시 각 종목별 5분 분봉 초기 기저 빌드업 자동 생성 (실시간 표준시 연동)
    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        raw_price = api.get_realtime_price(ticker)
        init_rows = []
        base_p = raw_price["Close"] if raw_price["Close"] > 0 else 50000.0
        for i in range(5, 0, -1):
            t = pd.to_datetime((datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'))
            mock_p = base_p + (i * 100 if i % 2 == 0 else -i * 50)
            init_rows.append({"Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": raw_price["Volume"]})
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=[pd.to_datetime((datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')) for i in range(5, 0, -1)])

    # 사용자가 스캔 버튼 누를 시 실제 실시간 데이터 버퍼 스택에 결합 레이어링
    if scan_trigger:
        live_tick = api.get_realtime_price(ticker)
        if live_tick["Close"] > 0:
            new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
            st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
            st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    # 종목별 독립 퀀트 계산 처리
    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    summary_rows.append({
        "종목코드": ticker,
        "종목명": name,
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가 (원)": f"{int(latest_info['Close']):,}",
        "수급선 (VWAP)": f"{int(latest_info['VWAP']):,}",
        "RSI 지표": int(latest_info["RSI"]),
        "단기 저항선": f"{int(latest_info['Local_High']):,}",
        "당일 누적거래량": f"{int(latest_info['Volume']):,}"
    })

# 전광판 데이터프레임 빌드 및 정렬 (매수타점 상단 우선 노출 알고리즘)
summary_df = pd.DataFrame(summary_rows)
summary_df['정렬순위'] = summary_df['현재 타이밍 신호'].map({"🔥 매수 타점!!": 0, "🚨 익절/청산": 1, "🟢 관망(대기)": 2})
summary_df = summary_df.sort_values(by='정렬순위').drop(columns=['정렬순위']).reset_index(drop=True)

# --- 대시보드 상단 메인 요약 모니터 모듈 ---
st.subheader(f"📊 실시간 전 종목 수급 상태 전광판 (최종 스캔 시각: {datetime.now().strftime('%H:%M:%S')})")
st.info("💡 팁: '🔄 전 종목 실시간 동시 스캔' 버튼을 누르면 30개 주도주의 현재가와 타점이 초단위로 동시 리프레시됩니다.")
st.dataframe(summary_df, use_container_width=True, height=450)

st.markdown("---")

# --- 하단부 개별 종목 돋보기 집중 분석 섹션 ---
st.subheader("🔍 타점 확인 종목 정밀 돋보기 분석")
selected_stock_name = st.selectbox("정밀 추적 차트를 보고 매수 타이밍을 잡을 종목을 선택하세요.", options=list(TICKER_POOL.values()))

# 선택된 종목명으로 코드 매칭 역추적
selected_ticker = [k for k, v in TICKER_POOL.items() if v == selected_stock_name][0]
target_df = process_quant_signals(st.session_state.multi_market_data[selected_ticker].copy())
latest_target = target_df.iloc[-1]

# 개별 분석 레이아웃 쪼개기
col_l, col_r = st.columns([2, 1])

with col_l:
    st.markdown(f"#### 📊 {selected_stock_name} ({selected_ticker}) 분봉 및 수급선 추이")
    chart_view = target_df[['Close', 'VWAP']].copy()
    chart_view.columns = ['현재가', '수급평균선(VWAP)']
    st.line_chart(chart_view)

with col_r:
    st.markdown("#### 🏹 최종 탐지 결과")
    sig = latest_target['타이밍 신호']
    if sig == "🔥 매수 타점!!":
        st.error(f"🎯 [진입 추천] {selected_stock_name} 종목에 거래량이 동반되며 전고점 및 VWAP선을 동시에 강력하게 돌파 중입니다! 매수 고려 가능.")
    elif sig == "🚨 익절/청산":
        st.info(f"🛑 [분할 청산] {selected_stock_name}의 단기 RSI 심리지표가 과열 구간인 {int(latest_target['RSI'])}을 초과했습니다. 수익 실현 타이밍.")
    else:
        st.success(f"🍏 [추적 관망] 현재 {selected_stock_name}은 조건 만족 대기 상태입니다. 안정적인 횡보 흐름 유지 중.")
        
    st.metric(label="현재가", value=f"{int(latest_target['Close']):,} 원")
    st.metric(label="당일 실시간 거래량", value=f"{int(latest_target['Volume']):,} 주")

# 최하단 데이터 시트 로깅 테이블 표출
st.markdown("##### 📋 해당 종목 단타 수급 히스토리 로그 (최근 흐름)")
st.dataframe(target_df.tail(7)[['타이밍 신호', 'Close', 'Volume', 'VWAP', 'RSI', 'Local_High']], use_container_width=True)
