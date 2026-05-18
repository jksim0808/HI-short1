import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time

# =================================================================
# 🔑 [실전투자 계좌 설정] Streamlit Secrets 내부 금고 연동
# =================================================================
# ⚠️ 반드시 한국투자증권 '실전투자용' App Key와 Secret Key를 Secrets에 넣으셔야 합니다.
APP_KEY = st.secrets.get("HANTU_APP_KEY", "YOUR_APP_KEY")
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "YOUR_APP_SECRET")
MOCK_FLAG = False  # 👈 실전투자용 강제 스위칭 (False 고정)

# =================================================================
# 🏦 한국투자증권 실전 API & 야후 파이낸스 실시간 정밀 연동 엔진
# =================================================================
class KoreaInvestmentAPI:
    def __init__(self):
        # 실전투자 전용 도메인 고정
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_access_token(self):
        """ 실전 토큰 세션 캐싱 및 실시간 갱신 모듈 """
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            return st.session_state.api_access_token
        
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

    def get_realtime_price(self, ticker):
        """ 실전투자 실시간 호가/체결 데이터 수신 및 백업 체인 구문 """
        access_token = self.get_access_token()
        if not access_token:
            return self.get_yahoo_backup_price(ticker)
            
        # 실전투자용 국내주식 현재가 조회 표준 엔드포인트
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        target_tr_id = "FHKST01010200"  # 👈 실전투자 전용 TR_ID 고정
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": target_tr_id,
            "custtype": "P"  # 개인고객 고정
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", 
            "FID_INPUT_ISCD": str(ticker).strip()
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=3.0)
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if res_data and res_data.get("stck_prpr"):
                    # 데이터 전처리 (+/- 부호 및 특수문자 정제)
                    current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                    high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                    low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                    volume = float(str(res_data.get("accl_tr_vol", 0)).strip())
                    
                    if current_price > 0:
                        return {
                            "Close": current_price,
                            "High": high_price if high_price > 0 else current_price,
                            "Low": low_price if low_price > 0 else current_price,
                            "Volume": volume if volume > 0 else 1000.0
                        }
            # 한투 과부하 대기 발생 시 야후 실시간 피드로 즉시 유연하게 스위칭
            return self.get_yahoo_backup_price(ticker)
        except:
            return self.get_yahoo_backup_price(ticker)

    def get_yahoo_backup_price(self, ticker):
        """ 비상용 야후 파이낸스 실시간 시세 트래킹 피드 """
        try:
            clean_ticker = str(ticker).strip()
            yahoo_ticker = f"{clean_ticker}.KQ"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            res = requests.get(url, headers=headers, timeout=2.0)
            
            if res.status_code != 200 or "result" not in res.json().get("chart", {}):
                yahoo_ticker = f"{clean_ticker}.KS"
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1m&range=1d"
                res = requests.get(url, headers=headers, timeout=2.0)
                
            if res.status_code == 200:
                json_data = res.json()
                result = json_data.get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    live_price = meta.get("regularMarketPrice")
                    
                    if live_price is None or float(live_price) <= 0:
                        indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
                        closes = [c for c in indicators.get("close", []) if c is not None and c > 0]
                        if closes: live_price = closes[-1]
                    
                    if live_price and float(live_price) > 0:
                        final_p = float(live_price)
                        return {
                            "Close": final_p,
                            "High": float(meta.get("fiftyTwoWeekHigh", final_p * 1.002)),
                            "Low": float(meta.get("fiftyTwoWeekLow", final_p * 0.998)),
                            "Volume": float(meta.get("regularMarketVolume", 250000.0))
                        }
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}
        except:
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}

# =================================================================
# 🏷️ 국내 주요 대형주 및 핵심 종목 마스터 딕셔너리
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

# =================================================================
# 📊 퀀트 시계열 연산 코어 엔진 (VWAP, RSI, 고가 저항 스캔)
# =================================================================
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
        
        # 🏹 거래량 분출 + 직전 3분봉 최고가 돌파 + VWAP 수급선 상회 조건 충족시 매수 신호
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

# 🛠️ [사이드바] 실시간 감시 종목 추가/삭제 
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

# 🎯 메인 대시보드 스캔 현황판
st.markdown("### 🏹 실전 수급 돌파 스캐너")
st.caption(f"⏱️ 실시간 거래소 동기화 중... ({datetime.now().strftime('%H:%M:%S')})")

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if st.button("🔑 버퍼 및 캐시 비우기 (오류 초기화)", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.session_state.api_access_token = None
    st.rerun()

summary_rows = []

# 멀티 종목 실시간 연산 체인 가동
for ticker in st.session_state.custom_stock_pool:
    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        raw_price = api.get_realtime_price(ticker)
        init_rows = []
        init_times = []
        base_p = raw_price["Close"] if raw_price["Close"] > 0 else 50000.0
        
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            mock_p = base_p + (i * 10 if i % 2 == 0 else -i * 5)
            init_rows.append({"Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": raw_price["Volume"]})
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    live_tick = api.get_realtime_price(ticker)
    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    # 💡 실제 당일 누적 거래대금 산출
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!": signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산": signal_weight = 1

    summary_rows.append({
        "종목코드": ticker, "종목명": get_stock_name(ticker), "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']), "수급선": int(latest_info['VWAP']), "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']), "실시간거래대금": realtime_trading_value, "신호가중치": signal_weight
    })

st.markdown("---")

# 수급 신호 포착 및 정렬 렌더링
if summary_rows:
    summary_df = pd.DataFrame(summary_rows).sort_values(by=['신호가중치', '실시간거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    # 매수 신호 발생 시 시스템 알림음 재생
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank_idx = index + 1
        card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']})"
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

# 🔄 1.2초 대기 후 페이지 무한 리프레시 메커니즘
time.sleep(1.2)
st.rerun()
