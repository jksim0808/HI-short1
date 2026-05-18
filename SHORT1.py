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

# --- 웹 대시보드 인터페이스 초기화 및 설정 (괄호 정상화 완료) ---
st.set_page_config(page_title="업종별 자동 선별 단타 스캐너", layout="wide")
st.title("🏹 실시간 주도 업종(섹터) 자동 판별 및 수급 단타 스캐너")
st.warning("⚠️ 시스템 가동 중: 수급 거래대금이 가장 강력하게 터지는 유망 업종을 자동 선별하여 감시 리스트에 주입합니다.")

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

api = KoreaInvestmentAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 사이드바 제어 패널
st.sidebar.header("⚙️ 스마트 섹터 제어실")
scan_trigger = st.sidebar.button("🔄 [실시간] 유망업종 선별 및 전 종목 동시 스캔")
reset_trigger = st.sidebar.button("🔑 메모리 버퍼 전체 초기화")

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

# 사이드바에 실시간 업종 순위 노출
st.sidebar.markdown("### 📊 실시간 업종 수급 순위")
for rank, (sec_name, vol) in enumerate(sorted_sectors, 1):
    st.sidebar.write(f"**{rank}위: {sec_name}** ({int(vol/100000000):,}억 원 쏠림)")

# 전광판 데이터 연산 루프
summary_rows = []

for ticker in flat_ticker_list:
    name = ticker_to_name_map[ticker]
    
    belonging_sector = "기타"
    for sec_name, stocks in SECTOR_MASTER.items():
        if ticker in stocks:
            belonging_sector = sec_name
            break

    # 🛠️ [버그 수정 완료] 가상 기저 분봉 빌드업 구조 정의 (가독성 분리 구조)
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

    # 실시간 데이터 결합
    if scan_trigger:
        live_tick = api.get_realtime_price(ticker)
        if live_tick["Close"] > 0:
            new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
            st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
            st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    # 퀀트 연산
    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    sector_rank = [i for i, (s_name, _) in enumerate(sorted_sectors) if s_name == belonging_sector][0]
    
    summary_rows.append({
        "소속 업종": belonging_sector,
        "종목코드": ticker,
        "종목명": name,
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가 (원)": f"{int(latest_info['Close']):,}",
        "수급선 (VWAP)": f"{int(latest_info['VWAP']):,}",
        "RSI 지표": int(latest_info["RSI"]),
        "단기 저항선": f"{int(latest_info['Local_High']):,}",
        "업종순위가중치": sector_rank,
        "신호가중치": {"🔥 매수 타점!!": 0, "🚨 익절/청산": 1, "🟢 관망(대기)": 2}[latest_info["타이밍 신호"]]
    })

# 정렬 알고리즘 적용 (신호 우선 -> 우량 업종 순)
summary_df = pd.DataFrame(summary_rows)
summary_df = summary_df.sort_values(by=['신호가중치', '업종순위가중치']).drop(columns=['업종순위가중치', '신호가중치']).reset_index(drop=True)

# --- 대시보드 상단 메인 요약 모니터 모듈 ---
st.subheader(f"📊 실시간 주도 유망업종 종합 전광판 (최종 분석: {datetime.now().strftime('%H:%M:%S')})")
st.info("💡 실시간 팁: 거래대금이 급증하는 1~2위 최유망 업종의 종목 중 '🔥 매수 타점!!'이 뜬 종목을 공략하는 것이 가장 승률이 높습니다.")
st.dataframe(summary_df, use_container_width=True, height=450)

st.markdown("---")

# --- 하단부 개별 종목 돋보기 집중 분석 섹션 ---
st.subheader("🔍 선택 종목 수급 및 차트 정밀 정찰")
selected_stock_name = st.selectbox("정밀 추적 차트를 보고 타이밍을 복기할 종목을 선택하세요.", options=list(ticker_to_name_map.values()))

selected_ticker = [k for k, v in ticker_to_name_map.items() if v == selected_stock_name][0]
target_df = process_quant_signals(st.session_state.multi_market_data[selected_ticker].copy())
latest_target = target_df.iloc[-1]

col_l, col_r = st.columns([2, 1])

with col_l:
    st.markdown(f"#### 📊 {selected_stock_name} ({selected_ticker}) 분봉 수급선(VWAP) 추이")
    chart_view = target_df[['Close', 'VWAP']].copy()
    chart_view.columns = ['현재가', '수급평균선(VWAP)']
    st.line_chart(chart_view)

with col_r:
    st.markdown("#### 🏹 최종 퀀트 타점 판정")
    sig = latest_target['타이밍 신호']
    if sig == "🔥 매수 타점!!":
        st.error(f"🎯 [매수 추천] {selected_stock_name}이 유망 섹터 수급을 바탕으로 전고점 저항선 돌파 성공!")
    elif sig == "🚨 익절/청산":
        st.info(f"🛑 [분할 청산] {selected_stock_name} 단기 오버슈팅으로 과열 구간 도달.")
    else:
        st.success(f"🍏 [관망 유지] {selected_stock_name}은 현재 안정적인 진입 대기 상태입니다.")
        
    st.metric(label="현재 체결가", value=f"{int(latest_target['Close']):,} 원")
    st.metric(label="RSI 수치", value=f"{int(latest_target['RSI'])}")

st.markdown("##### 📋 해당 종목 수급 연산 상세 로그")
st.dataframe(target_df.tail(6)[['타이밍 신호', 'Close', 'Volume', 'VWAP', 'RSI', 'Local_High']], use_container_width=True)
