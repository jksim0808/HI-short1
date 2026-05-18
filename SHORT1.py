import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# =================================================================
# 🏦 [버그 수정] 네이버 멀티 API 시장 기호(A) 자동 매핑 엔진
# =================================================================
class NaverPureAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_bulk_realtime_prices(self, tickers):
        """ 종목코드 앞에 'A'를 강제 결합하여 네이버 멀티 쿼리 버그를 원천 해결 """
        if not tickers:
            return {}
        try:
            # 💡 핵심 수정: 네이버 내부 규격에 맞게 'A005930' 형태로 변환
            formatted_tickers = [f"A{t}" if not t.startswith('A') else t for t in tickers]
            query_str = ",".join([f"SERVICE_ITEM:{t}" for t in formatted_tickers])
            
            url = f"https://polling.finance.naver.com/api/realtime?query={query_str}"
            res = requests.get(url, headers=self.headers, timeout=1.0)
            
            results = {}
            if res.status_code == 200:
                datas = res.json().get("result", {}).get("areas", [{}])[0].get("datas", [])
                
                for idx, item in enumerate(datas):
                    if not item: continue
                    # 순수 숫자 6자리 키값으로 복원하여 매핑
                    raw_ticker = tickers[idx]
                    
                    close_p = float(item.get("nv", 0))
                    open_p = float(item.get("ov", 0)) if item.get("ov") else close_p
                    high_p = float(item.get("hv", 0)) if item.get("hv") else close_p
                    low_p = float(item.get("lv", 0)) if item.get("lv") else close_p
                    
                    results[raw_ticker] = {
                        "Name": item.get("nm", f"종목({raw_ticker})"),
                        "Close": close_p,
                        "Open": open_p,
                        "High": high_p,
                        "Low": low_p,
                        "Volume": float(item.get("cv", 0)),          
                        "Total_Value": float(item.get("aa", 0)) * 1000000  
                    }
                return results
        except Exception as e:
            pass
        return {}

# =================================================================
# 📊 [실시간 스팟 연산] 과거 데이터 없이 현재 스펙으로 신호 판정
# =================================================================
def calculate_spot_signal(tick):
    close_p = tick["Close"]
    high_p = tick["High"]
    low_p = tick["Low"]
    open_p = tick["Open"]
    total_value = tick["Total_Value"]
    
    center_price = (high_p + low_p + close_p) / 3
    price_range = high_p - low_p
    target_trigger = open_p + (price_range * 0.5) if price_range > 0 else open_p
    
    is_breakout = (close_p > center_price) and (close_p >= target_trigger)
    is_market_leader = total_value >= 30000000000  # 당일 거래대금 300억 이상 주도주 필터
    is_strong_trend = close_p >= (high_p * 0.97) and (close_p > open_p)

    rsi_score = int(((close_p - low_p) / (price_range + 1e-9)) * 100) if price_range > 0 else 50

    if is_breakout and is_market_leader and is_strong_trend and (rsi_score < 80):
        return "🔥 매수", center_price, rsi_score
    elif rsi_score > 88 or (close_p < center_price and rsi_score > 75):
        return "🚨 청산", center_price, rsi_score
    else:
        return "🟢 대기", center_price, rsi_score

# =================================================================
# 🖥️ 마스터 사전 및 대시보드 인터페이스 (모바일 극대화)
# =================================================================
STOCK_NAME_MAP = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "373220": "LG에너지솔루션", "005490": "POSCO홀딩스", "247540": "에코프로비엠", "068270": "셀트리온",
    "047190": "한화에어로스페이스", "443250": "두산로보틱스", "105560": "KB금융", "000100": "유한양행",
    "035420": "NAVER", "012330": "현대모비스", "006400": "삼성SDI", "051910": "LG화학",
    "207940": "삼성바이오로직스", "010140": "삼성중공업", "352820": "하이브", "004170": "신세계"
}

st.set_page_config(page_title="PURE SCANNER", layout="centered")

if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = list(STOCK_NAME_MAP.keys())

api = NaverPureAPI()

# 🛠️ [사이드바] 종목 입력 관리
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

# 삭제 처리
delete_target = None
for tk in list(st.session_state.custom_stock_pool):
    col1, col2 = st.sidebar.columns([4, 1])
    col1.caption(f"▪️ {STOCK_NAME_MAP.get(tk, f'종목({tk})')} ({tk})")
    if col2.button("❌", key=f"del_{tk}"):
        delete_target = tk

if delete_target:
    st.session_state.custom_stock_pool.remove(delete_target)
    st.rerun()

# 🏹 메인 터미널 보다
st.markdown("### 🏹 실시간 모바일 스캐너 (전종목 출력 엔진)")

if st.button("🔄 실시간 시세 수동 새로고침", use_container_width=True):
    st.rerun()

summary_rows = []

# ⚡ 수정된 기호 결합 방식으로 멀티 패킷 수신 진행
bulk_data = api.get_bulk_realtime_prices(st.session_state.custom_stock_pool)

for ticker in st.session_state.custom_stock_pool:
    if ticker not in bulk_data: continue
    tick_info = bulk_data[ticker]
    
    signal, vwap_like, rsi_like = calculate_spot_signal(tick_info)
    
    signal_weight = 2
    if signal == "🔥 매수":
        signal_weight = 0
    elif signal == "🚨 청산":
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker,
        "종목명": tick_info["Name"],
        "현재 타이밍 신호": signal,
        "현재가": int(tick_info["Close"]),
        "수급선": int(vwap_like),
        "RSI": rsi_like,
        "저항선": int(tick_info["High"]),
        "당일거래대금": tick_info["Total_Value"],
        "신호가중치": signal_weight
    })

st.markdown("---")

# 출력 보드 (오류 구문 완벽 제거 버전)
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    # 신호 가중치 오름차순(매수 최상단) -> 당일 거래대금 내림차순 정렬
    summary_df = summary_df.sort_values(by=['신호가중치', '당일거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank = index + 1
        card_title = f"**[{rank}위] {row['종목명']} ({row['종목코드']})**"
        card_metrics = f"💰 **{row['현재가']:,}원** | 강도: `{row['RSI']}` | 📊 당일대금: **{int(row['당일거래대금']/100000000):,}억**"
        card_sub_metrics = f"🍏 수급(중심): {row['수급선']:,}원 / 🛑 저항(고가): {row['저항선']:,}원"
        
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
