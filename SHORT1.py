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

# 📂 시장 전체 섹터 및 소속 주도 종목 풀(Pool) 마스터 데이터 정의
SECTOR_MASTER = {
    "⚡ 반도체 & AI/테크": {
        "005930": "삼성전자", "000660": "SK하이닉스", "009150": "삼성전기", 
        "066570": "LG전자", "018260": "삼성에스디에스", "036570": "엔씨소프트"
    },
    "🧬 바이오 & 헬스케어": {
        "207940": "삼성바이오로직스", "068270": "셀트리온", "091990": "셀트리온제약", 
        "028260": "삼성물산", "112610": "씨젠", "319660": "피엔에이치테크"
    },
    "🔋 2차전지 & 신소재": {
        "373220": "LG에너지솔루션", "051910": "LG화학", "006400": "삼성SDI", 
        "247540": "에코프로비엠", "086520": "에코프로", "005490": "POSCO홀딩스"
    },
    "🚗 자동차 & 중공업/기계": {
        "005380": "현대차", "000270": "기아", "012330": "현대모비스", 
        "009540": "HD현대중공업", "010950": "S-Oil", "011780": "금호석유"
    },
    "📱 플랫폼 & 엔터테인먼트": {
        "035420": "NAVER", "035720": "카카오", "253450": "스튜디오드래곤", 
        "403870": "포바이포", "352820": "하이브", "035900": "JYP Ent."
    }
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
            
        # 🌟 [수정] 호가(FHKST01010100) 대신 실시간 체결가 중심인 '주식현재가 시세(FHKST01010200)'로 변경
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
                
                # 문자열 부호나 공백 제거 후 정확히 Float 형변환
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
st.set_page_config(page_title="모바일 단타 스캐너", layout="centered")

st.markdown("### 🏹 실시간 주도 섹터 수급 스캐너")

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    scan_trigger = st.button("🔄 실시간 스캔", use_container_width=True)
with col_btn2:
    reset_trigger = st.button("🔑 버퍼 초기화", use_container_width=True)

if reset_trigger:
    st.session_state.multi_market_data = {}
    st.rerun()

# --- 실시간 섹터별 거래대금 스캔 및 유망순위 연산 ---
sector_volumes = {}
ticker_to_name_map = {}
flat_ticker_list = []

for sector_name, stocks in SECTOR_MASTER.items():
    total_sector_money = 0.0
    for tk, nm in stocks.items():
        ticker_to_name_map[tk] = nm
        flat_ticker_list.append(tk)
        p_info = api.get_realtime_price(tk)
        total_sector_money += (p_info["Close"] * p_info["Volume"])
    sector_volumes[sector_name] = total_sector_money

sorted_sectors = sorted(sector_volumes.items(), key=lambda x: x[1], reverse=True)

with st.expander("📊 현재 업종 수급 순위 보기"):
    for rank, (sec_name, vol) in enumerate(sorted_sectors, 1):
        st.write(f"**{rank}위** : {sec_name} ({int(vol/100000000):,}억)")

# 전광판 데이터 연산 루프
summary_rows = []
total_accumulated_ticks = [] 

for ticker in flat_ticker_list:
    name = ticker_to_name_map[ticker]
    
    belonging_sector = "기타"
    for sec_name, stocks in SECTOR_MASTER.items():
        if ticker in stocks:
            belonging_sector = sec_name
            break

    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        raw_price = api.get_realtime_price(ticker)
        init_rows = []
        init_times = []
        base_p = raw_price["Close"] if raw_price["Close"] > 0 else 50000.0
        
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            t = pd.to_datetime(time_str)
            init_times.append(t)
            
            mock_p = base_p + (i * 100 if i % 2 == 0 else -i * 50)
            init_rows.append({
                "Close": mock_p, 
                "High": mock_p * 1.001, 
                "Low": mock_p * 0.999, 
                "Volume": raw_price["Volume"]
            })
            
        tmp_df = pd.DataFrame(init_rows, index=init_times)
        st.session_state.multi_market_data[ticker] = tmp_df

    if scan_trigger:
        live_tick = api.get_realtime_price(ticker)
        if live_tick["Close"] > 0:
            new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
            st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
            st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    total_accumulated_ticks.append(len(st.session_state.multi_market_data[ticker]))

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    sector_rank = [i for i, (s_name, _) in enumerate(sorted_sectors) if s_name == belonging_sector][0]
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산":
        signal_weight = 1

    summary_rows.append({
        "소속 업종": belonging_sector,
        "종목코드": ticker,
        "종목명": name,
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']),
        "수급선": int(latest_info['VWAP']),
        "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']),
        "업종순위가중치": sector_rank,
        "신호가중치": signal_weight
    })

summary_df = pd.DataFrame(summary_rows)
summary_df = summary_df.sort_values(by=['신호가중치', '업종순위가중치']).reset_index(drop=True)

# --- 현재 시전 평가 전광판 모듈 ---
avg_ticks = np.mean(total_accumulated_ticks) if total_accumulated_ticks else 5
data_maturity = min(100, int((avg_ticks / 15.0) * 100))

if data_maturity <= 40:
    st.info(f"⏳ **현재 시전 점검**: 데이터 축적도 **{data_maturity}%** (기저 데이터 빌드 완료. '실시간 스캔'을 눌러 실시간 시세를 채워 갈수록 타점 평가가 정밀해집니다.)")
elif data_maturity < 80:
    st.success(f"⚡ **현재 시전 점검**: 데이터 축적도 **{data_maturity}%** (실시간 시세 정상 추적 중. 데이터 신뢰도 보통)")
else:
    st.error(f"🔥 **현재 시전 점검**: 데이터 축적도 **{data_maturity}%** (최대치 버퍼 확보 완료! 돌파 타점 실시간 평가 신뢰도 최상)")

# --- 카드형 리스트 순차 출력 ---
st.markdown("---")

has_buy_signal = not summary_df[summary_df["신호가중치"] == 0].empty
if has_buy_signal:
    st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

for index, row in summary_df.iterrows():
    sig = row["현재 타이밍 신호"]
    card_header = f"**{row['종목명']}** ({row['종목코드']}) ｜ {row['소속 업종']}"
    card_body = f"💰 **현재가**: {row['현재가']:,}원 ｜ 📈 **RSI**: {row['RSI']}\n\n🍏 **수급선(VWAP)**: {row['수급선']:,}원 ｜ 🛑 **저항선**: {row['저항선']:,}원"
    
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
