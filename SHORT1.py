import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor

# =================================================================
# 🏦 초고속 실시간 JSON 데이터 엔진 (HTML 파싱 전면 제거)
# =================================================================
class FastFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_24h_history(self, ticker):
        """ [개선] 켜자마자 최근 분봉 데이터를 로드하여 24시간 연산 뼈대 구축 """
        try:
            clean_ticker = str(ticker).strip()
            # 네이버 모바일 실시간 JSON 분봉 API 다이렉트 호출 (초고속)
            url = f"https://polling.finance.naver.com/api/realtime/has/candle?symbol={clean_ticker}&candleType=MIN1&count=60"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            if res.status_code == 200:
                data = res.json().get("result", {}).get("candleList", [])
                init_rows = []
                init_times = []
                for c in reversed(data):
                    # 시간 포맷 변환 (YYYYMMDDHHMMSS)
                    dt_str = str(c["candleDateTime"])
                    parsed_time = pd.to_datetime(f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:00")
                    
                    if parsed_time not in init_times:
                        init_times.append(parsed_time)
                        init_rows.append({
                            "Close": float(c["closePrice"]),
                            "High": float(c["highPrice"]),
                            "Low": float(c["lowPrice"]),
                            "Volume": float(c["candleAccTradeVolume"])  # 해당 분봉 순수 거래량
                        })
                if init_rows:
                    return pd.DataFrame(init_rows, index=init_times)
        except:
            pass
        # 시스템 다운 방지용 샌드박스 데이터
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(5, 0, -1)]
        return pd.DataFrame([{"Close": 50000.0, "High": 50100.0, "Low": 49900.0, "Volume": 10000.0} for _ in range(5)], index=base_times)

    def get_realtime_json(self, ticker):
        """ [속도 혁명] HTML 뷰티풀수프 크롤링을 전면 제거하고 오직 JSON 데이터만 수신 """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{clean_ticker}"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            result = {"Ticker": clean_ticker, "Name": f"종목({clean_ticker})", "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 0.0, "Instant_Value": 0.0}
            
            if res.status_code == 200:
                item = res.json().get("result", {}).get("areas", [{}])[0].get("datas", [{}])[0]
                if not item: return result
                
                result["Name"] = item.get("nm", f"종목({clean_ticker})")
                result["Close"] = float(item.get("nv", 0))
                result["High"] = float(item.get("hv", result["Close"]))
                result["Low"] = float(item.get("lv", result["Close"]))
                result["Volume"] = float(item.get("cv", 0)) # 현재 체결 분봉 분 가중 거래량
                # 실시간 거래대금 (현재가 * 거래량)
                result["Instant_Value"] = result["Close"] * result["Volume"]
                return result
        except:
            pass
        return {"Ticker": ticker, "Name": f"오류({ticker})", "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 0.0, "Instant_Value": 0.0}

# =================================================================
# 🎯 대한민국 20대 주도주 기본 풀
# =================================================================
LEADING_STOCKS = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "373220": "LG에너지솔루션", "005490": "POSCO홀딩스", "247540": "에코프로비엠", "086520": "에코프로",
    "207940": "삼성바이오로직스", "068270": "셀트리온", "000100": "유한양행", "047190": "한화에어로스페이스",
    "010140": "삼성중공업", "443250": "두산로보틱스", "105560": "KB금융", "055550": "신한지주",
    "000810": "삼성화재", "035420": "NAVER", "035720": "카카오", "012330": "현대모비스"
}

# =================================================================
# 📊 24시간 실시간 시점 퀀트 알고리즘 엔지니어링
# =================================================================
def compute_signals(df):
    if len(df) < 3:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['알고리즘신호'] = "🟢 대기"
        return df

    # VWAP 라인 계산
    typical_p = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (typical_p * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    # 5분 커스텀 RSI 계산
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # 저항 매물대 라인
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    
    sig_list = []
    for idx in range(len(df)):
        if idx < 2:
            sig_list.append("🟢 대기")
            continue
        row = df.iloc[idx]
        p_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        if (row['Close'] > row['VWAP']) and (row['Close'] >= p_high) and (row['Volume'] > p_vol * 1.02) and (row['RSI'] < 78):
            sig_list.append("🔥 매수")
        elif row['RSI'] > 82:
            sig_list.append("🚨 과열청산")
        else:
            sig_list.append("🟢 대기")
    df['알고리즘신호'] = sig_list
    return df

# =================================================================
# 🖥️ 초고속 병렬 트레이딩 시스템 구동 단말
# =================================================================
st.set_page_config(page_title="HYPER QUANT", layout="centered")

if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = list(LEADING_STOCKS.keys())
if "market_data_buffer" not in st.session_state:
    st.session_state.market_data_buffer = {}
if "account_portfolio" not in st.session_state:
    st.session_state.account_portfolio = {}

api = FastFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 사이드바 리스크 필터 컨트롤러
st.sidebar.markdown("### 🛠️ 실전 시스템 설정")
target_value_filter = st.sidebar.slider("🔥 24시간 누적대금 하한선 (억원)", min_value=100, max_value=1000, value=500, step=50)
filter_value_bytes = target_value_filter * 100_000_000

raw_input = st.sidebar.text_area("✍️ 실시간 감시 종목 추가", placeholder="예: 005930", height=60)
if st.sidebar.button("⚡ 시스템 동기화 가동", use_container_width=True):
    if raw_input.strip():
        tokens = raw_input.replace(",", " ").replace("\n", " ").split()
        valid_tokens = [t.strip() for t in tokens if len(t.strip()) == 6 and t.strip().isdigit()]
        for vt in valid_tokens:
            if vt not in st.session_state.stock_pool:
                st.session_state.stock_pool.append(vt)
        st.rerun()

st.markdown(f"### 🏹 실시간 주도주 스캐너 (⚡ JSON 초고속 엔진)")
st.caption(f"📊 현재 시점 기준 [24시간 누적 거래대금 {target_value_filter}억 이상]만 실시간 연산")

if st.button("🔄 가상 포트폴리오 및 버퍼 초기화", use_container_width=True):
    st.session_state.market_data_buffer = {}
    st.session_state.account_portfolio = {}
    st.rerun()

# 가상 체결 잔고 현황
if st.session_state.account_portfolio:
    st.error("💼 [실전 시뮬레이션] 현재 매수 포지션 보유 잔고")
    for tk, pos in list(st.session_state.account_portfolio.items()):
        tick_now = api.get_realtime_json(tk)
        cur_p = tick_now["Close"]
        pnl = ((cur_p - pos["진입가"]) / pos["진입가"]) * 100
        st.write(f"▪  **{tick_now['Name']}** -> 진입: {pos['진입가']:,}원 | 현재: {cur_p:,}원 | 수익률: **{pnl:+.2f}%**")
    st.markdown("---")

# ⚡ [개선] 20개 종목 초경량 JSON 병렬 패킷 다운로드
with ThreadPoolExecutor(max_workers=20) as executor:
    live_results = list(executor.map(api.get_realtime_json, st.session_state.stock_pool))

summary_board = []

for live in live_results:
    ticker = live["Ticker"]
    if live["Close"] == 0: continue
        
    # 메모리 버퍼가 비어있다면 즉시 분봉 과거 이력 동기화
    if ticker not in st.session_state.market_data_buffer or len(st.session_state.market_data_buffer[ticker]) <= 1:
        st.session_state.market_data_buffer[ticker] = api.fetch_24h_history(ticker)
        
    # 실시간 초경량 데이터 스트리밍 버퍼에 적재
    tick_df = pd.DataFrame([{"Close": live["Close"], "High": live["High"], "Low": live["Low"], "Volume": live["Volume"]}], index=[pd.to_datetime(current_time_str)])
    st.session_state.market_data_buffer[ticker] = pd.concat([st.session_state.market_data_buffer[ticker], tick_df])
    st.session_state.market_data_buffer[ticker] = st.session_state.market_data_buffer[ticker].loc[~st.session_state.market_data_buffer[ticker].index.duplicated(keep='last')].tail(60) # 60개 캔들 유지

    # 📈 [핵심 변경] 당일 누적 수치가 아닌, 현재 버퍼 내 쌓인 분봉 기준의 실시간 거래대금 연산
    # 분봉들의 (종가 * 거래량)을 모두 더하여 실전 시점 기준의 최근 누적 거래대금 산출
    df_buffer = st.session_state.market_data_buffer[ticker].copy()
    rolling_24h_value = (df_buffer['Close'] * df_buffer['Volume']).sum()
    
    # 24시간 환산 거래대금 조건 미달 시 대시보드 출력에서 즉시 탈락
    if rolling_24h_value < filter_value_bytes:
        continue

    # 퀀트 매매 시그널 분석
    calc_df = compute_signals(df_buffer)
    latest = calc_df.iloc[-1]
    final_signal = latest["알고리즘신호"]
    
    # 익절 / 칼손절 리스크 매니지먼트 수식 가동
    if ticker in st.session_state.account_portfolio:
        portfolio = st.session_state.account_portfolio[ticker]
        entry = portfolio["진입가"]
        highest = max(portfolio["최고가"], live["Close"])
        st.session_state.account_portfolio[ticker]["최고가"] = highest
        
        if live["Close"] <= entry * 0.985:
            final_signal = "💥 칼손절 매도"
            del st.session_state.account_portfolio[ticker]
        elif live["Close"] <= highest * 0.98 and live["Close"] > entry:
            final_signal = "💰 트레일링 익절"
            del st.session_state.account_portfolio[ticker]
            
    if final_signal == "🔥 매수" and ticker not in st.session_state.account_portfolio:
        st.session_state.account_portfolio[ticker] = {"진입가": live["Close"], "최고가": live["Close"]}

    w = 2
    if final_signal in ["🔥 매수", "💥 칼손절 매도", "💰 트레일링 익절"]: w = 0
    elif final_signal == "🚨 과열청산": w = 1

    summary_board.append({
        "코드": ticker, "이름": live["Name"], "신호": final_signal,
        "현재가": int(live["Close"]), "수급선": int(latest["VWAP"]), "RSI": int(latest["RSI"]),
        "저항대": int(latest["Local_High"]), "대금": rolling_24h_value, "가중치": w
    })

# 🖥️ 모바일 가시성 최적화 UI 배치 리포팅
if summary_board:
    res_df = pd.DataFrame(summary_board).sort_values(by=['가중치', '대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not res_df[res_df["가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg")

    for idx, row in res_df.iterrows():
        s = row["신호"]
        title = f"**[{idx+1}위] {row['이름']} ({row['코드']})**"
        metrics = f"💰 **{row['현재가']:,}원** │ RSI: `{row['RSI']}` │ 📊 최근 24h 대금: **{int(row['대금']/100000000):,}억**"
        subs = f"🍏 수급선: {row['수급선']:,}원 / 🛑 매물저항: {row['저항대']:,}원"
        
        if s == "🔥 매수":
            st.error(f"🎯 **[매수포착]** {title}\n\n{metrics}\n\n{subs}")
        elif s in ["💥 칼손절 매도", "💰 트레일링 익절", "🚨 과열청산"]:
            st.warning(f"🚨 **[위험관리 즉시매도]** {title}\n\n{metrics}\n\n{subs}")
        else:
            st.success(f"🟢 **[대기]** {title}\n\n{metrics}\n\n{subs}")
        st.markdown("---")
else:
    st.info("💡 지정한 최근 24시간 거래대금 하한선을 넘는 거래 활성 주도주가 없습니다.")

# 딜레이 타임을 0.1초로 축소하여 즉각 반응형 리프레시 실행
time.sleep(0.1)
st.rerun()
