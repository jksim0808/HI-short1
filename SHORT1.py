import streamlit as st
import pandas as pd
import numpy as np
import requests
import time  # ⚡ 과부하 방지용 타임 모듈 추가
from datetime import datetime, timedelta

# =================================================================
# 🏦 실시간 주도주 데이터 웹 크롤링 마스터 엔진
# =================================================================
class WebFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    # @st.cache_data를 쓰면 좋지만 실시간성이 떨어지므로, 함수 내부 timeout을 극도로 줄여 병목 차단
    def get_top_30_data(self):
        """ 네이버 모바일 금융에서 상위 30개를 신속하게 인터셉트 """
        try:
            url = "https://m.stock.naver.com/api/json/sise/getSiseListJson.nhn?menu=trade_value&pageSize=30"
            # timeout을 0.8초로 제한해 네트워크가 절대로 화면을 붙잡고 늘어지지 못하게 차단
            res = requests.get(url, headers=self.headers, timeout=0.8)
            
            parsed_results = []
            if res.status_code == 200:
                items = res.json().get("result", {}).get("list", [])
                
                for item in items:
                    parsed_results.append({
                        "Ticker": item.get("cd", ""),
                        "Name": item.get("nm", ""),
                        "Close": float(item.get("nv", 0)),
                        "High": float(item.get("hv", 0)),
                        "Low": float(item.get("lv", 0)),
                        "Volume": float(item.get("cv", 0)), 
                        "Total_Value": float(item.get("aa", 0)) * 1000000 
                    })
                return parsed_results
        except Exception as e:
            pass
        return []

    def fetch_24h_history(self, ticker):
        """ 초기 뼈대 데이터 고속 생성 """
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(10, 0, -1)]
        rows = [{"Close": 50000.0, "High": 50200.0, "Low": 49900.0, "Volume": 1000.0} for _ in base_times]
        return pd.DataFrame(rows, index=base_times)

# =================================================================
# 📊 실전 실시간 퀀트 알고리즘
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
        
        if (row['Close'] > row['VWAP']) and (row['Close'] >= p_high) and (row['Volume'] > p_vol * 1.01) and (row['RSI'] < 80):
            sig_list.append("🔥 매수")
        elif row['RSI'] > 83:
            sig_list.append("🚨 과열청산")
        else:
            sig_list.append("🟢 대기")
            
    df['알고리즘신호'] = sig_list
    return df

# =================================================================
# 🖥️ 초고속 스크리닝 단말기 인터페이스
# =================================================================
st.set_page_config(page_title="FAST QUANT", layout="centered")

api = WebFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if "market_data_buffer" not in st.session_state:
    st.session_state.market_data_buffer = {}
if "account_portfolio" not in st.session_state:
    st.session_state.account_portfolio = {}

st.markdown(f"### 🏹 실시간 거래대금 TOP 30 주도주 스캐너")
st.caption(f"⚡ 병목 최적화 모드 가동 중 • 동기화 시간: {datetime.now().strftime('%H:%M:%S')}")

# 가상 잔고 현황
if st.session_state.account_portfolio:
    st.error("💼 [실전 포지션] 실시간 가상 매수 보유 잔고")
    for tk, pos in list(st.session_state.account_portfolio.items()):
        st.write(f"▪ **{pos['이름']}** ({tk}) ➡️ 진입가: {pos['진입가']:,}원")
    st.markdown("---")

# 네이버 데이터 원격 호출
live_results = api.get_top_30_data()
summary_board = []

if live_results:
    for live in live_results:
        ticker = live["Ticker"]
        
        if ticker not in st.session_state.market_data_buffer:
            st.session_state.market_data_buffer[ticker] = api.fetch_24h_history(ticker)
            
        tick_df = pd.DataFrame([{"Close": live["Close"], "High": live["High"], "Low": live["Low"], "Volume": live["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.market_data_buffer[ticker] = pd.concat([st.session_state.market_data_buffer[ticker], tick_df])
        st.session_state.market_data_buffer[ticker] = st.session_state.market_data_buffer[ticker].loc[~st.session_state.market_data_buffer[ticker].index.duplicated(keep='last')].tail(20)

        df_buffer = st.session_state.market_data_buffer[ticker].copy()
        calc_df = compute_signals(df_buffer)
        latest = calc_df.iloc[-1]
        final_signal = latest["알고리즘신호"]
        
        if final_signal == "🔥 매수" and ticker not in st.session_state.account_portfolio:
            st.session_state.account_portfolio[ticker] = {"이름": live["Name"], "진입가": live["Close"]}
        elif final_signal == "🚨 과열청산" and ticker in st.session_state.account_portfolio:
            del st.session_state.account_portfolio[ticker]

        w = 2
        if final_signal in ["🔥 매수", "💥 매도"]: w = 0
        elif final_signal == "🚨 과열청산": w = 1

        summary_board.append({
            "코드": ticker, "이름": live["Name"], "신호": final_signal,
            "현재가": int(live["Close"]), "수급선": int(latest["VWAP"]), "RSI": int(latest["RSI"]),
            "저항대": int(latest["Local_High"]), "대금": live["Total_Value"], "가중치": w
        })

# 🖥️ 화면 렌더링 부
if summary_board:
    res_df = pd.DataFrame(summary_board).sort_values(by=['가중치', '대금'], ascending=[True, False]).reset_index(drop=True)
    
    # 30개 종목을 UI 컴포넌트로 한 번에 빠르게 밀어 넣기
    for idx, row in res_df.iterrows():
        s = row["신호"]
        title = f"**[{idx+1}위] {row['이름']} ({row['코드']})**"
        metrics = f"💰 **{row['현재가']:,}원** │ RSI: `{row['RSI']}` │ 📊 대금: **{int(row['대금']/100000000):,}억**"
        subs = f"🍏 수급선: {row['수급선']:,}원 / 🛑 저항대: {row['저항대']:,}원"
        
        if s == "🔥 매수":
            st.error(f"🎯 **[매수포착]** {title}\n\n{metrics}\n\n{subs}")
        elif s == "🚨 과열청산":
            st.warning(f"🚨 **[과열청산]** {title}\n\n{metrics}\n\n{subs}")
        else:
            st.success(f"🟢 **[대기]** {title}\n\n{metrics}\n\n{subs}")
        st.markdown("---")
else:
    st.info("🔄 서버와 통신 라인을 재확보하고 있습니다. 잠시만 기다려주세요.")

# =================================================================
# ⏱️ [핵심 변경] 시스템 안정을 위한 0.5초 미세 딜레이 배치
# =================================================================
# CPU와 네트워크에 숨 쉴 구멍을 주어 브라우저가 안 멈추고 부드럽게 넘어가게 만듭니다.
time.sleep(0.5)
st.rerun()
