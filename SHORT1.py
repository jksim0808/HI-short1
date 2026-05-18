import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# =================================================================
# 🏦 [속도 혁신] 네이버 멀티 JSON 일괄 인터셉트 엔진
# =================================================================
class NaverFastMultiAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_bulk_realtime_prices(self, tickers):
        """ 20개 이상의 종목 데이터를 단 하나의 네트워크 패킷으로 일괄 수신 (병목 현상 원천 차단) """
        if not tickers:
            return {}
        try:
            query_str = ",".join([f"SERVICE_ITEM:{t}" for t in tickers])
            url = f"https://polling.finance.naver.com/api/realtime?query={query_str}"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            results = {}
            if res.status_code == 200:
                datas = res.json().get("result", {}).get("areas", [{}])[0].get("datas", [])
                for idx, item in enumerate(datas):
                    if not item: continue
                    ticker = tickers[idx] if idx < len(tickers) else item.get("cd", "")
                    
                    results[ticker] = {
                        "Name": item.get("nm", f"종목({ticker})"),
                        "Close": float(item.get("nv", 0)),
                        "High": float(item.get("hv", 0)),
                        "Low": float(item.get("lv", 0)),
                        "Volume": float(item.get("cv", 0)),          
                        "Total_Value": float(item.get("aa", 0)) * 1000000  
                    }
                return results
        except:
            pass
        return {}

    def fetch_base_history(self):
        """ 타임라인 버퍼 초기 안정을 위한 기초 뼈대 생성 """
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(10, 0, -1)]
        rows = [{"Close": 50000.0, "High": 50100.0, "Low": 49900.0, "Volume": 5000.0} for _ in base_times]
        return pd.DataFrame(rows, index=base_times)

# =================================================================
# 📊 [신뢰성 업그레이드] 실전 주도주 변동성 돌파 알고리즘
# =================================================================
def process_advanced_quant(df, total_value):
    if len(df) < 3:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['타이밍 신호'] = "🟢 대기"
        return df

    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (typical_price * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    
    signals = []
    for idx in range(len(df)):
        if idx < 2:
            signals.append("🟢 대기")
            continue
            
        row = df.iloc[idx]
        p_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol_ma = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        # 🚨 [신뢰성 보정 필터 가동] 
        is_breakout = (row['Close'] > row['VWAP']) and (row['Close'] >= p_high) and (row['Volume'] > p_vol_ma * 1.02)
        is_market_leader = total_value >= 30000000000  # 당일 누적 거래대금 300억 이상 주도주 필터
        is_strong_trend = row['Close'] >= (df['High'].max() * 0.97)

        if is_breakout and is_market_leader and is_strong_trend and (row['RSI'] < 78):
            signals.append("🔥 매수")
        elif row['RSI'] > 83:
            signals.append("🚨 청산")
        else:
            signals.append("🟢 대기")
            
    df['타이밍 신호'] = signals
    return df

# =================================================================
# 🖥️ 마스터 딕셔너리 및 대시보드 인터페이스 (모바일 뷰 최적화)
# =================================================================
STOCK_NAME_MAP = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "373220": "LG에너지솔루션", "005490": "POSCO홀딩스", "247540": "에코프로비엠", "068270": "셀트리온",
    "047190": "한화에어로스페이스", "443250": "두산로보틱스", "105560": "KB금융", "000100": "유한양행",
    "035420": "NAVER", "012330": "현대모비스", "006400": "삼성SDI", "051910": "LG화학",
    "207940": "삼성바이오로직스", "010140": "삼성중공업", "352820": "하이브", "004170": "신세계"
}

st.set_page_config(page_title="FAST SCANNER", layout="centered")

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = list(STOCK_NAME_MAP.keys())
if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}
if "cached_stock_names" not in st.session_state:
    st.session_state.cached_stock_names = STOCK_NAME_MAP.copy()

api = NaverFastMultiAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 🛠️ [사이드바] 모바일 컨트롤 영역
st.sidebar.markdown("### 📋 종목 코드 등록")
raw_input_tickers = st.sidebar.text_area("번호만 입력 가능 (공백/쉼표 구분)", placeholder="예: 005930 000660", height=70)

if st.sidebar.button("⚡ 종목 등록/동기화", use_container_width=True):
    if raw_input_tickers.strip():
        parsed_tickers = raw_input_tickers.replace(",", " ").replace("\n", " ").split()
        clean_tickers = [t.strip() for t in parsed_tickers if len(t.strip()) == 6 and t.strip().isdigit()]
        if clean_tickers:
            st.session_state.custom_stock_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.write(f"🔍 감시 중: {len(st.session_state.custom_stock_pool)}개 종목")

# 사이드바 개별 삭제 기능
delete_target = None
for tk in list(st.session_state.custom_stock_pool):
    col1, col2 = st.sidebar.columns([4, 1])
    display_name = st.session_state.cached_stock_names.get(tk, f"종목({tk})")
    col1.caption(f"▪️ {display_name} ({tk})")
    if col2.button("❌", key=f"del_{tk}"):
        delete_target = tk

if delete_target:
    st.session_state.custom_stock_pool.remove(delete_target)
    if delete_target in st.session_state.multi_market_data:
        del st.session_state.multi_market_data[delete_target]
    st.rerun()

# 🏹 메인 터미널 보드
st.markdown("### 🏹 실시간 모바일 스캐너 (초고속 엔진)")
st.caption(f"ℹ️ 수동 업데이트 모드 (화면 조작 시 실시간 갱신) • 현재시각: {datetime.now().strftime('%H:%M:%S')}")

# 사용자가 즉시 시세를 새로고침하고 싶을 때 누르는 마스터 버튼
if st.button("🔄 실시간 시세 수동 새로고침", use_container_width=True):
    st.rerun()

if st.button("🔑 버퍼 및 캐시 비우기", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.session_state.cached_stock_names = STOCK_NAME_MAP.copy()
    st.rerun()

summary_rows = []

# ⚡ 20개 종목을 단 한 번의 요청으로 일괄 수신
bulk_data = api.get_bulk_realtime_prices(st.session_state.custom_stock_pool)

for ticker in st.session_state.custom_stock_pool:
    if ticker not in bulk_data: continue
    live_tick = bulk_data[ticker]
    
    st.session_state.cached_stock_names[ticker] = live_tick["Name"]
    actual_name = live_tick["Name"]

    if ticker not in st.session_state.multi_market_data:
        st.session_state.multi_market_data[ticker] = api.fetch_base_history()

    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    calculated_df = process_advanced_quant(st.session_state.multi_market_data[ticker].copy(), live_tick["Total_Value"])
    latest_info = calculated_df.iloc[-1]
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 청산":
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker, "종목명": actual_name, "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']), "수급선": int(latest_info['VWAP']), "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']), "당일거래대금": live_tick["Total_Value"], "신호가중치": signal_weight
    })

st.markdown("---")

# 스마트폰 화면 레이아웃 최적화 렌더링
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(by=['text_value' if 'text_value' in summary_df else '신호가중치', '당일거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank = index + 1
        card_title = f"**[{rank}위] {row['종목명']} ({row['종목코드']})**"
        card_metrics = f"💰 **{row['현재가']:,}원** | RSI: `{row['RSI']}` | 📊 당일대금: **{int(row['당일거래대금']/100000000):,}억**"
        card_sub_metrics = f"🍏 수급: {row['수급선']:,}원 / 🛑 저항: {row['저항선']:,}원"
        
        if sig == "🔥 매수":
            with st.container():
                st.error(f"🎯 **{sig} 타점 포착!** │ {card_title}")
                st.markdown(card_metrics)
                st.caption(card_sub_metrics)
                st.markdown("---")
        elif sig == "🚨 청산":
            with st.container():
                st.warning(f"🚨 **{sig} 유도!** │ {card_title}")
                st.markdown(card_metrics)
                st.caption(card_sub_metrics)
                st.markdown("---")
        else:
            with st.container():
                st.success(f"🟢 **{sig} 대기** │ {card_title}")
                st.markdown(card_metrics)
                st.caption(card_sub_metrics)
                st.markdown("---")
else:
    st.info("💡 오른쪽 상단 사이드바 버튼을 열어 종목을 추가해 주세요.")
