import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# =================================================================
# 🏦 [구조 수정] 네이버 페이 증권 실시간 멀티 패킷 엔진 (정밀 파싱)
# =================================================================
class NaverPayAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://finance.naver.com/"
        }

    def get_bulk_realtime_prices(self, tickers):
        """ 네이버 페이 API 내부 JSON 구조 변경 반영 (areas 배열 제거 수정을 완벽히 반영) """
        if not tickers:
            return {}
        try:
            ticker_ids = ",".join(tickers)
            url = f"https://polling.finance.naver.com/api/realtime/domestic/prices?itemCodes={ticker_ids}"
            
            res = requests.get(url, headers=self.headers, timeout=2.0)
            results = {}
            
            if res.status_code == 200:
                raw_json = res.json()
                # 💡 핵심 수정: 데이터가 areas 없이 result 바로 밑의 배열/딕셔너리로 들어옵니다.
                datas = raw_json.get("result", [])
                
                # 만약 result 안에 형식이 다를 경우를 대비한 방어 코드
                if isinstance(datas, dict):
                    datas = datas.get("areas", [{}])[0].get("datas", [])
                
                for item in datas:
                    if not item: continue
                    cd = item.get("cd") 
                    if not cd: continue
                    
                    # 실시간 값 수신, 만약 없으면 전일종가나 기준가로 방어
                    close_p = float(item.get("nv", 0))    # 현재가
                    open_p = float(item.get("ov", 0)) if item.get("ov") else close_p  # 시가
                    high_p = float(item.get("hv", 0)) if item.get("hv") else close_p  # 고가
                    low_p = float(item.get("lv", 0)) if item.get("lv") else close_p   # 저가
                    
                    # 장마감 후에도 0이 되지 않도록 이전 체결가(sv) 참조 방어
                    if close_p == 0:
                        close_p = float(item.get("sv", 0))
                        open_p = float(item.get("ov", close_p))
                        high_p = float(item.get("hv", close_p))
                        low_p = float(item.get("lv", close_p))
                    
                    results[cd] = {
                        "Name": item.get("nm", f"종목({cd})"),
                        "Close": close_p,
                        "Open": open_p,
                        "High": high_p,
                        "Low": low_p,
                        "Volume": float(item.get("cv", 0)),          
                        "Total_Value": float(item.get("aa", 0)) * 1000000  # 만원/백만 단위 자동 보정
                    }
                return results
        except Exception as e:
            pass
        return {}

# =================================================================
# 📊 [실시간 스팟 연산] 현재 캔들의 에너지 기반 신호 판정
# =================================================================
def calculate_spot_signal(tick):
    close_p = tick["Close"]
    high_p = tick["High"]
    low_p = tick["Low"]
    open_p = tick["Open"]
    total_value = tick["Total_Value"]
    
    if close_p == 0:
        return "🟢 대기", 0, 50

    center_price = (high_p + low_p + close_p) / 3
    price_range = high_p - low_p
    target_trigger = open_p + (price_range * 0.5) if price_range > 0 else open_p
    
    is_breakout = (close_p > center_price) and (close_p >= target_trigger)
    # 거래대금 필터를 장마감 후 검증을 위해 10억으로 일시 하향 안전화
    is_market_leader = total_value >= 1000000000  
    is_strong_trend = close_p >= (high_p * 0.95) and (close_p > open_p)

    rsi_score = int(((close_p - low_p) / (price_range + 1e-9)) * 100) if price_range > 0 else 50

    if is_breakout and is_market_leader and is_strong_trend and (rsi_score < 80):
        return "🔥 매수", center_price, rsi_score
    elif rsi_score > 88 or (close_p < center_price and rsi_score > 75):
        return "🚨 청산", center_price, rsi_score
    else:
        return "🟢 대기", center_price, rsi_score

# =================================================================
# 🖥️ 마스터 사전 및 대시보드 인터페이스 (모바일 뷰 최적화)
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

api = NaverPayAPI()

# 🛠️ [사이드바] 종목 입력 관리
st.sidebar.markdown("### 📋 종목 코드 등록")
raw_input_tickers = st.sidebar.text_area("번호만 입력 가능 (공백/쉼표 구분)", placeholder="예: 005930 000660", height=70)

if st.sidebar.button("⚡ 종목 등록/동기화", use_container_width=True):
    if raw_input_tickers.strip():
        parsed_tickers = raw_input_tickers.replace(",", " ").replace("\n", " ").split()
        clean_tickers = [t.strip() for t in parsed_tickers if len(t.strip()) == 6 and t.strip().isdigit()]
        if clean_tickers:
            updated_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.session_state.custom_stock_pool = updated_pool
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

# 🏹 메인 터미널 보드
st.markdown("### 🏹 실시간 모바일 스캐너 (전종목 출력 엔진)")

if st.button("🔄 실시간 시세 수동 새로고침", use_container_width=True):
    st.rerun()

summary_rows = []

# ⚡ 수정된 수신 통로로 데이터 파싱 실행
bulk_data = api.get_bulk_realtime_prices(st.session_state.custom_stock_pool)

for ticker in st.session_state.custom_stock_pool:
    if ticker in bulk_data:
        tick_info = bulk_data[ticker]
    else:
        tick_info = {"Name": STOCK_NAME_MAP.get(ticker, f"종목({ticker})"), "Close": 0, "High": 0, "Low": 0, "Open": 0, "Total_Value": 0}
    
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

# 🖥️ 메인 렌더링 화면 출력 보드
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(by=['신호가중치', '당일거래대금'], ascending=[True, False]).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank = index + 1
        card_title = f"**[{rank}위] {row['종목명']} ({row['종목코드']})**"
        
        # 거래대금 표시 억 단위 환산 안전화
        display_money = int(row['당일거래대금']/100000000) if row['당일거래대금'] > 0 else 0
        
        card_metrics = f"💰 **{row['현재가']:,}원** | 강도: `{row['RSI']}` | 📊 당일대금: **{display_money:,}억**"
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
