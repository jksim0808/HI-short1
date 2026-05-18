import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

# =================================================================
# 🏦 네이버 금융 실시간 웹 스크래핑 엔진
# =================================================================
class NaverFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_realtime_price(self, ticker):
        """ 네이버 금융 실시간 주가창에서 현재가, 고가, 저가, 거래량을 정밀 추출 """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
            res = requests.get(url, headers=self.headers, timeout=2.0)
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 1. 현재가 추출
                today_div = soup.find("div", {"class": "today"})
                if not today_div:
                    return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}
                
                blind_now = today_div.find("span", {"class": "blind"})
                current_price = float(re.sub(r'[^\d]', '', blind_now.text))
                
                # 2. 고가, 저가, 거래량 추출
                no_info_table = soup.find("table", {"class": "no_info"})
                high_price = current_price
                low_price = current_price
                volume = 150000.0
                
                if no_info_table:
                    tds = no_info_table.find_all("td")
                    for td in tds:
                        blind_span = td.find("span", {"class": "blind"})
                        if not blind_span:
                            continue
                        
                        text_val = blind_span.text.strip()
                        parent_text = td.text
                        
                        if "고가" in parent_text and "52주" not in parent_text:
                            high_price = float(re.sub(r'[^\d]', '', text_val))
                        elif "저가" in parent_text and "52주" not in parent_text:
                            low_price = float(re.sub(r'[^\d]', '', text_val))
                        elif "거래량" in parent_text:
                            volume = float(re.sub(r'[^\d]', '', text_val))

                if current_price > 0:
                    return {
                        "Close": current_price,
                        "High": high_price if high_price > 0 else current_price,
                        "Low": low_price if low_price > 0 else current_price,
                        "Volume": volume if volume > 0 else 1000.0
                    }
                    
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}
        except:
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}

# =================================================================
# 🏷️ 국내 주요 종목 코드 마스터 매핑 딕셔너리 (감시 풀 기본 확장)
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
# 📊 기술적 지표 퀀트 연산 엔진
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
        
        if (c_row['Close'] > c_row['VWAP']) and (c_row['Close'] >= p_local_high) and (c_row['Volume'] > p_vol_ma * 1.02) and (c_row['RSI'] < 78):
            signals.append("🔥 매수 타점!!")
        elif c_row['RSI'] > 82:
            signals.append("🚨 익절/청산")
        else:
            signals.append("🟢 관망(대기)")
    df['타이밍 신호'] = signals
    return df

# =================================================================
# 🖥️ 웹 대시보드 인터페이스 영역 (모바일 반응형 최적화)
# =================================================================
st.set_page_config(page_title="실시간 스캐너", layout="centered")

# 📌 초기 감시 풀 목록을 주요 대형주 24개 전체로 대폭 확장
if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = list(STOCK_NAME_MAP.keys())

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

# 🛠️ [사이드바] 종목 입력기
st.sidebar.markdown("### 📋 종목 번호 입력")
st.sidebar.caption("공백이나 쉼표로 구분하여 추가 가능")

raw_input_tickers = st.sidebar.text_area(
    "종목코드 멀티 입력", 
    placeholder="예: 005930 000660",
    height=90
)

if st.sidebar.button("⚡ 종목 등록 및 동기화", use_container_width=True):
    if raw_input_tickers.strip():
        parsed_tickers = raw_input_tickers.replace(",", " ").replace("\n", " ").split()
        clean_tickers = [t.strip() for t in parsed_tickers if len(t.strip()) == 6 and t.strip().isdigit()]
        
        if clean_tickers:
            updated_pool = list(set(st.session_state.custom_stock_pool + clean_tickers))
            st.session_state.custom_stock_pool = updated_pool
            st.sidebar.success(f"추가 완료!")
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.write(f"🔍 감시 목록 ({len(st.session_state.custom_stock_pool)}개)")

# 모바일 사이드바 세로 폭 폭망 방지를 위해 컴팩트 UI로 변경
delete_target = None
for tk in list(st.session_state.custom_stock_pool):
    col1, col2 = st.sidebar.columns([4, 1])
    col1.caption(f"▪️ {get_stock_name(tk)}")
    if col2.button("❌", key=f"del_{tk}", help="삭제"):
        delete_target = tk

if delete_target:
    st.session_state.custom_stock_pool.remove(delete_target)
    if delete_target in st.session_state.multi_market_data:
        del st.session_state.multi_market_data[delete_target]
    st.rerun()

# 🏹 메인 모니터링 전광판
st.markdown("### 🏹 실시간 네이버 수급 스캐너")
st.caption(f"⏱️ 자동 갱신 중... ({datetime.now().strftime('%H:%M:%S')})")

api = NaverFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if st.button("🔑 버퍼 및 캐시 비우기 (시세 동기화 세트)", use_container_width=True):
    st.session_state.multi_market_data = {}
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
            init_rows.append({
                "Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": raw_price["Volume"]
            })
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    live_tick = api.get_realtime_price(ticker)
    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(15)

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수 타점!!":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 익절/청산":
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker,
        "종목명": get_stock_name(ticker),  
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']),
        "수급선": int(latest_info['VWAP']),
        "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']),
        "실시간거래대금": realtime_trading_value,
        "신호가중치": signal_weight
    })

st.markdown("---")

# 실시간 시세 보드 정렬 및 렌더링 (최대 20위까지 노출)
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(
        by=['신호가중치', '실시간거래대금'], 
        ascending=[True, False]
    ).head(20).reset_index(drop=True)  # 📊 최대 20개 종목 순위 정렬 고정
    
    has_buy_signal = not summary_df[summary_df["신호가중치"] == 0].empty
    if has_buy_signal:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank_idx = index + 1
        
        card_header = f"**[{rank_idx}위] {row['종목명']}** ({row['종목코드']})"
        
        card_body = (
            f"💵 **현재가**: {row['현재가']:,}원\n\n"
            f"🔥 **RSI**: {row['RSI']} | 📊 **대금**: {int(row['실시간거래대금']/100000000):,}억\n\n"
            f"🍏 **수급**: {row['수급선']:,}원 | 🛑 **저항**: {row['저항선']:,}원"
        )
        
        if sig == "🔥 매수 타점!!":
            with st.container():
                st.error(f"🎯 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
        elif sig == "🚨 익절/청산":
            with st.container():
                st.warning(f"🚨 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
        else:
            with st.container():
                st.success(f"🍏 **{sig}**\n\n{card_header}")
                st.markdown(card_body)
                st.markdown("---")
else:
    st.info("💡 종목 번호들을 등록하시면 분석이 시작됩니다.")

# =================================================================
# 🔄 초단위 자동 리프레시 루프 (1.2초 인터벌)
# =================================================================
time.sleep(1.2)
st.rerun()
