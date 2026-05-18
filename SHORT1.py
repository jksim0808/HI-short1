import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# =================================================================
# 🏦 초고속 실시간 JSON 마스터 엔진
# =================================================================
class HyperFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_top_30_tickers(self):
        """ 시장에서 실시간 거래대금이 가장 높은 상위 30개 종목 자동 추출 """
        try:
            url = "https://finance.naver.com/api/sise/rankingList.naver?rankingType=mks&pageSize=30"
            res = requests.get(url, headers=self.headers, timeout=1.2)
            if res.status_code == 200:
                items = res.json().get("result", {}).get("list", [])
                return [item["cd"] for item in items if "cd" in item]
        except:
            pass
        return ["005930", "000660", "005380", "000270", "373220", "005490", "247540", "068270", "047190", "105560"]

    def fetch_24h_history(self, ticker):
        """ 분봉 데이터 초기화 (과거 족적 생성) """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://polling.finance.naver.com/api/realtime/has/candle?symbol={clean_ticker}&candleType=MIN1&count=60"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            if res.status_code == 200:
                data = res.json().get("result", {}).get("candleList", [])
                init_rows = []
                init_times = []
                for c in reversed(data):
                    dt_str = str(c["candleDateTime"])
                    parsed_time = pd.to_datetime(f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:00")
                    
                    if parsed_time not in init_times:
                        init_times.append(parsed_time)
                        init_rows.append({
                            "Close": float(c["closePrice"]),
                            "High": float(c["highPrice"]),
                            "Low": float(c["lowPrice"]),
                            "Volume": float(c["candleAccTradeVolume"])
                        })
                if init_rows:
                    return pd.DataFrame(init_rows, index=init_times)
        except:
            pass
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(5, 0, -1)]
        return pd.DataFrame([{"Close": 50000.0, "High": 50100.0, "Low": 49900.0, "Volume": 10000.0} for _ in range(5)], index=base_times)

    def get_bulk_realtime_json(self, tickers):
        """ 30개 종목 일괄 패킷 수신 """
        try:
            query_str = ",".join([f"SERVICE_ITEM:{t}" for t in tickers])
            url = f"https://polling.finance.naver.com/api/realtime?query={query_str}"
            res = requests.get(url, headers=self.headers, timeout=1.5)
            
            parsed_results = []
            if res.status_code == 200:
                datas = res.json().get("result", {}).get("areas", [{}])[0].get("datas", [])
                for idx, item in enumerate(datas):
                    if not item: continue
                    ticker = tickers[idx] if idx < len(tickers) else item.get("cd", "")
                    parsed_results.append({
                        "Ticker": ticker,
                        "Name": item.get("nm", f"종목({ticker})"),
                        "Close": float(item.get("nv", 0)),
                        "High": float(item.get("hv", 0)),
                        "Low": float(item.get("lv", 0)),
                        "Volume": float(item.get("cv", 0)),
                        "Total_Value": float(item.get("aa", 0))  # 네이버 제공 당일 누적 거래대금
                    })
                return parsed_results
        except:
            pass
        return []

# =================================================================
# 📊 퀀트 알고리즘 엔진
# =================================================================
def compute_signals(df):
    if len(df) < 3:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['알고리즘신호'] = "🟢 대기"
        return df

    typical_p = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (typical_p * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
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
# 🖥️ 제로 딜레이 트레이딩 시스템 인터페이스
# =================================================================
st.set_page_config(page_title="30 STOCKS QUANT", layout="centered")

api = HyperFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 상위 30개 세션 풀 자동 생성 및 유지
if "stock_pool" not in st.session_state or st.sidebar.button("🔄 상위 30개 종목 갱신"):
    with st.spinner("시장의 실시간 거래대금 상위 30개 주도주 탐색 중..."):
        st.session_state.stock_pool = api.get_top_30_tickers()
if "market_data_buffer" not in st.session_state:
    st.session_state.market_data_buffer = {}
if "account_portfolio" not in st.session_state:
    st.session_state.account_portfolio = {}

st.markdown(f"### 🏹 실시간 거래대금 TOP 30 전수 분석기")
st.caption(f"⚡ 필터 해제 모드 (30개 전 종목 무조건 출력) • 갱신시간: {datetime.now().strftime('%H:%M:%S')}")

# 잔고 상태창
if st.session_state.account_portfolio:
    st.error("💼 [실전 시뮬레이션] 현재 매수 포지션 보유 잔고")
    for tk, pos in list(st.session_state.account_portfolio.items()):
        df_temp = api.fetch_24h_history(tk)
        cur_p = df_temp.iloc[-1]["Close"] if not df_temp.empty else pos["진입가"]
        pnl = ((cur_p - pos["진입가"]) / pos["진입가"]) * 100
        st.write(f"▪ 진입가: {pos['진입가']:,}원 | 현재가: {cur_p:,}원 | 수익률: **{pnl:+.2f}%**")
    st.markdown("---")

# 벌크 시세 다운로드
live_results = api.get_bulk_realtime_json(st.session_state.stock_pool)
summary_board = []

for live in live_results:
    ticker = live["Ticker"]
    if live["Close"] == 0: continue
        
    if ticker not in st.session_state.market_data_buffer or len(st.session_state.market_data_buffer[ticker]) <= 1:
        st.session_state.market_data_buffer[ticker] = api.fetch_24h_history(ticker)
        
    tick_df = pd.DataFrame([{"Close": live["Close"], "High": live["High"], "Low": live["Low"], "Volume": live["Volume"]}], index=[pd.to_datetime(current_time_str)])
    st.session_state.market_data_buffer[ticker] = pd.concat([st.session_state.market_data_buffer[ticker], tick_df])
    st.session_state.market_data_buffer[ticker] = st.session_state.market_data_buffer[ticker].loc[~st.session_state.market_data_buffer[ticker].index.duplicated(keep='last')].tail(60)

    df_buffer = st.session_state.market_data_buffer[ticker].copy()
    
    # 퀀트 매매 신호 계산
    calc_df = compute_signals(df_buffer)
    latest = calc_df.iloc[-1]
    final_signal = latest["알고리즘신호"]
    
    # 리스크 관리 가동
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

    # 정렬용 우선순위 가중치 (매수/매도가 가장 위로 오도록 설정)
    w = 2
    if final_signal in ["🔥 매수", "💥 칼손절 매도", "💰 트레일링 익절"]: w = 0
    elif final_signal == "🚨 과열청산": w = 1

    # 누적대금 정보가 유실되었을 경우 안전 보정
    display_value = live["Total_Value"] if live["Total_Value"] > 0 else (live["Close"] * live["Volume"] * 60)

    summary_board.append({
        "코드": ticker, "이름": live["Name"], "신호": final_signal,
        "현재가": int(live["Close"]), "수급선": int(latest["VWAP"]), "RSI": int(latest["RSI"]),
        "저항대": int(latest["Local_High"]), "대금": display_value, "가중치": w
    })

# 🖥️ 화면 렌더링 (30개 무조건 출력)
if summary_board:
    # 1순위: 신호 발생 종목, 2순위: 거래대금 상위 순 정렬
    res_df = pd.DataFrame(summary_board).sort_values(by=['가중치', '대금'], ascending=[True, False]).reset_index(drop=True)
    
    # 매수 신호 포착 시 경보음
    if not res_df[res_df["가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg")

    for idx, row in res_df.iterrows():
        s = row["신호"]
        title = f"**[{idx+1}위] {row['이름']} ({row['코드']})**"
        metrics = f"💰 **{row['현재가']:,}원** │ RSI: `{row['RSI']}` │ 📊 거래대금: **{int(row['대금']/100000000):,}억**"
        subs = f"🍏 수급선: {row['수급선']:,}원 / 🛑 매물저항: {row['저항대']:,}원"
        
        if s == "🔥 매수":
            st.error(f"🎯 **[매수포착]** {title}\n\n{metrics}\n\n{subs}")
        elif s in ["💥 칼손절 매도", "💰 트레일링 익절", "🚨 과열청산"]:
            st.warning(f"🚨 **[위험관리 즉시매도]** {title}\n\n{metrics}\n\n{subs}")
        else:
            st.success(f"🟢 **[대기]** {title}\n\n{metrics}\n\n{subs}")
        st.markdown("---")
else:
    st.info("💡 종목 데이터를 불러오는 중입니다.")

# 딜레이 없이 무제한 초고속 루프 가동
st.rerun()
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# =================================================================
# 🏦 초고속 실시간 JSON 마스터 엔진 (30개 종목 일괄 자동 제어)
# =================================================================
class HyperFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_top_30_tickers(self):
        """ [신규] 시장에서 실시간 거래대금이 가장 높은 상위 30개 종목의 코드를 자동 추출 """
        try:
            # 네이버 금융 거래대금 상위 검색 API 활용
            url = "https://finance.naver.com/api/sise/rankingList.naver?rankingType=mks&pageSize=30"
            res = requests.get(url, headers=self.headers, timeout=1.2)
            if res.status_code == 200:
                items = res.json().get("result", {}).get("list", [])
                # 거래대금 상위 30개 종목 코드 배열 리턴
                return [item["cd"] for item in items if "cd" in item]
        except:
            pass
        # API 통신 실패 시 백업용 대표 우량주 10종 리스트 방어선
        return ["005930", "000660", "005380", "000270", "373220", "005490", "247540", "068270", "047190", "105560"]

    def fetch_24h_history(self, ticker):
        """ 초기 구동 시 해당 종목의 24시간 분봉 뼈대 데이터 빌드 """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://polling.finance.naver.com/api/realtime/has/candle?symbol={clean_ticker}&candleType=MIN1&count=60"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            if res.status_code == 200:
                data = res.json().get("result", {}).get("candleList", [])
                init_rows = []
                init_times = []
                for c in reversed(data):
                    dt_str = str(c["candleDateTime"])
                    parsed_time = pd.to_datetime(f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:00")
                    
                    if parsed_time not in init_times:
                        init_times.append(parsed_time)
                        init_rows.append({
                            "Close": float(c["closePrice"]),
                            "High": float(c["highPrice"]),
                            "Low": float(c["lowPrice"]),
                            "Volume": float(c["candleAccTradeVolume"])
                        })
                if init_rows:
                    return pd.DataFrame(init_rows, index=init_times)
        except:
            pass
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(5, 0, -1)]
        return pd.DataFrame([{"Close": 50000.0, "High": 50100.0, "Low": 49900.0, "Volume": 10000.0} for _ in range(5)], index=base_times)

    def get_bulk_realtime_json(self, tickers):
        """ [속도 혁명] 30개 종목을 단 한 번의 패킷 요청으로 통째로 긁어오는 벌크 커넥터 """
        try:
            query_str = ",".join([f"SERVICE_ITEM:{t}" for t in tickers])
            url = f"https://polling.finance.naver.com/api/realtime?query={query_str}"
            res = requests.get(url, headers=self.headers, timeout=1.5)
            
            parsed_results = []
            if res.status_code == 200:
                datas = res.json().get("result", {}).get("areas", [{}])[0].get("datas", [])
                for idx, item in enumerate(datas):
                    if not item: continue
                    ticker = tickers[idx] if idx < len(tickers) else item.get("cd", "")
                    parsed_results.append({
                        "Ticker": ticker,
                        "Name": item.get("nm", f"종목({ticker})"),
                        "Close": float(item.get("nv", 0)),
                        "High": float(item.get("hv", 0)),
                        "Low": float(item.get("lv", 0)),
                        "Volume": float(item.get("cv", 0)),
                        "Total_Value": float(item.get("aa", 0)) # 당일 누적 거래대금 마스터
                    })
                return parsed_results
        except:
            pass
        return []

# =================================================================
# 📊 수급 돌파 및 변동성 연산 엔진
# =================================================================
def compute_signals(df):
    if len(df) < 3:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['알고리즘신호'] = "🟢 대기"
        return df

    typical_p = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (typical_p * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
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
# 🖥️ 제로 딜레이 트레이딩 단말기 인터페이스
# =================================================================
st.set_page_config(page_title="ZERO DELAY QUANT", layout="centered")

api = HyperFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# [자동화] 시스템이 기동되면 실시간 상위 30개 종목을 자동으로 스캔하여 풀에 등록
if "stock_pool" not in st.session_state or st.sidebar.button("🔄 상위 30개 종목 재생성"):
    with st.spinner("시장의 실시간 거래대금 상위 30개 주도주 탐색 중..."):
        st.session_state.stock_pool = api.get_top_30_tickers()
if "market_data_buffer" not in st.session_state:
    st.session_state.market_data_buffer = {}
if "account_portfolio" not in st.session_state:
    st.session_state.account_portfolio = {}

# 사이드바 리스크 필터 컨트롤러
st.sidebar.markdown("### 🛠️ 실전 리스크 제어")
target_value_filter = st.sidebar.slider("🔥 최근 24h 누적대금 하한선 (억원)", min_value=100, max_value=1500, value=500, step=50)
filter_value_bytes = target_value_filter * 100_000_000

st.markdown(f"### 🏹 실시간 거래대금 TOP 30 자동 분석기")
st.caption(f"⚡ 딜레이 제로 커스텀 구동 중 • 현재 감시 종목: {len(st.session_state.stock_pool)}개")

# 가상 체결 잔고 현황
if st.session_state.account_portfolio:
    st.error("💼 [실전 시뮬레이션] 현재 매수 포지션 보유 잔고")
    for tk, pos in list(st.session_state.account_portfolio.items()):
        df_temp = api.fetch_24h_history(tk)
        cur_p = df_temp.iloc[-1]["Close"] if not df_temp.empty else pos["진입가"]
        pnl = ((cur_p - pos["진입가"]) / pos["진입가"]) * 100
        st.write(f"▪ 현재 포지션 진입가: {pos['진입가']:,}원 | 현재가: {cur_p:,}원 | 수익률: **{pnl:+.2f}%**")
    st.markdown("---")

# ⚡ 단 한 번의 요청으로 30개 종목의 시세를 통째로 인터셉트 (딜레이 제거의 핵심)
live_results = api.get_bulk_realtime_json(st.session_state.stock_pool)

summary_board = []

for live in live_results:
    ticker = live["Ticker"]
    if live["Close"] == 0: continue
        
    # 버퍼에 과거 이력이 없으면 로딩
    if ticker not in st.session_state.market_data_buffer or len(st.session_state.market_data_buffer[ticker]) <= 1:
        st.session_state.market_data_buffer[ticker] = api.fetch_24h_history(ticker)
        
    # 실시간 초경량 데이터 스트리밍 결합
    tick_df = pd.DataFrame([{"Close": live["Close"], "High": live["High"], "Low": live["Low"], "Volume": live["Volume"]}], index=[pd.to_datetime(current_time_str)])
    st.session_state.market_data_buffer[ticker] = pd.concat([st.session_state.market_data_buffer[ticker], tick_df])
    st.session_state.market_data_buffer[ticker] = st.session_state.market_data_buffer[ticker].loc[~st.session_state.market_data_buffer[ticker].index.duplicated(keep='last')].tail(60)

    # 24시간 거래대금 필터 연산
    df_buffer = st.session_state.market_data_buffer[ticker].copy()
    rolling_24h_value = (df_buffer['Close'] * df_buffer['Volume']).sum()
    
    if rolling_24h_value < filter_value_bytes:
        continue

    # 시그널 추출
    calc_df = compute_signals(df_buffer)
    latest = calc_df.iloc[-1]
    final_signal = latest["알고리즘신호"]
    
    # 익절 / 손절 트레일링 스톱 알고리즘 가동
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

# 🖥️ 모바일 화면 출력 시스템
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
    st.info("💡 실시간 조건에 부합하는 활성 주도주가 없습니다.")

# [개선] 의도적인 time.sleep() 완전 제거하여 속도 무제한 구동
st.rerun()
