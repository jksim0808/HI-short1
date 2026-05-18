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
        """ 네이버 금융 실시간 주가창에서 종목명, 현재가, 고가, 저가, 거래량을 정밀 추출 """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
            res = requests.get(url, headers=self.headers, timeout=1.5)
            
            # 기본 방어 스펙 설정
            result = {"Name": f"종목({clean_ticker})", "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 네이버 금융 헤더 영역에서 실제 종목명 추출
                wrap_company = soup.find("div", {"class": "wrap_company"})
                if wrap_company and wrap_company.find("h2"):
                    extracted_name = wrap_company.find("h2").text.strip()
                    if extracted_name:
                        result["Name"] = extracted_name
                
                # 1. 현재가 추출
                today_div = soup.find("div", {"class": "today"})
                if not today_div:
                    return result
                
                blind_now = today_div.find("span", {"class": "blind"})
                current_price = float(re.sub(r'[^\d]', '', blind_now.text))
                result["Close"] = current_price
                
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
                    result["High"] = high_price if high_price > 0 else current_price
                    result["Low"] = low_price if low_price > 0 else current_price
                    result["Volume"] = volume if volume > 0 else 1000.0
                    return result
                    
            return result
        except:
            return {"Name": f"종목({ticker})", "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0}

# =================================================================
# 🎯 [업데이트] 대한민국 시장 주도주 및 트렌드 핵심 20종목 마스터 사전
# =================================================================
STOCK_NAME_MAP = {
    # 1. 반도체 / AI / 핵심 대형주
    "005930": "삼성전자", 
    "000660": "SK하이닉스", 
    "004170": "신세계", 
    "035420": "NAVER",
    # 2. 자동차 / 모빌리티 미래차
    "005380": "현대차", 
    "000270": "기아", 
    "012330": "현대모비스",
    # 3. 2차전지 / 핵심 소재
    "373220": "LG에너지솔루션", 
    "006400": "삼성SDI", 
    "051910": "LG화학", 
    "005490": "POSCO홀딩스", 
    "247540": "에코프로비엠",
    # 4. 바이오 / 제약 대장주
    "207940": "삼성바이오로직스", 
    "068270": "셀트리온", 
    "000100": "유한양행",
    # 5. 방산 / 조선 / 인프라 주도주
    "047190": "한화에어로스페이스", 
    "010140": "삼성중공업",
    # 6. 로봇 / 엔터 / 금융 밸류업
    "443250": "두산로보틱스", 
    "352820": "하이브", 
    "105560": "KB금융"
}

# =================================================================
# 📊 기술적 지표 퀀트 연산 엔진
# =================================================================
def process_quant_signals(df):
    if len(df) < 2:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['타이밍 신호'] = "🟢 대기"
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
            signals.append("🟢 대기")
            continue
        c_row = df.iloc[idx]
        p_local_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol_ma = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        if (c_row['Close'] > c_row['VWAP']) and (c_row['Close'] >= p_local_high) and (c_row['Volume'] > p_vol_ma * 1.02) and (c_row['RSI'] < 78):
            signals.append("🔥 매수")
        elif c_row['RSI'] > 82:
            signals.append("🚨 청산")
        else:
            signals.append("🟢 대기")
    df['타이밍 신호'] = signals
    return df

# =================================================================
# 🖥️ 웹 대시보드 인터페이스 영역 (모바일 최적화)
# =================================================================
st.set_page_config(page_title="스캐너", layout="centered")

# 초기 기동 시 20종목 풀로 바인딩
if "custom_stock_pool" not in st.session_state:
    st.session_state.custom_stock_pool = list(STOCK_NAME_MAP.keys())

if "multi_market_data" not in st.session_state:
    st.session_state.multi_market_data = {}

if "cached_stock_names" not in st.session_state:
    st.session_state.cached_stock_names = STOCK_NAME_MAP.copy()

api = NaverFinanceAPI()

# 🛠️ [사이드바] 모바일 입력창
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

# 사이드바 리스트 렌더링
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

# 🏹 메인 모니터링 영역
st.markdown("### 🏹 실시간 모바일 스캐너 (20대 주도주)")
st.caption(f"🔄 자동 갱신 중... ({datetime.now().strftime('%H:%M:%S')})")

current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

if st.button("🔑 버퍼 및 캐시 비우기", use_container_width=True):
    st.session_state.multi_market_data = {}
    st.session_state.cached_stock_names = STOCK_NAME_MAP.copy()
    st.rerun()

summary_rows = []

# 멀티 종목 실시간 연산 가동
for ticker in st.session_state.custom_stock_pool:
    live_tick = api.get_realtime_price(ticker)
    
    if "Name" in live_tick and not live_tick["Name"].startswith("종목("):
        st.session_state.cached_stock_names[ticker] = live_tick["Name"]
        
    actual_name = st.session_state.cached_stock_names.get(ticker, f"종목({ticker})")

    if ticker not in st.session_state.multi_market_data or len(st.session_state.multi_market_data[ticker]) == 0:
        init_rows = []
        init_times = []
        base_p = live_tick["Close"] if live_tick["Close"] > 0 else 50000.0
        
        for i in range(5, 0, -1):
            time_str = (datetime.now() - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            init_times.append(pd.to_datetime(time_str))
            mock_p = base_p + (i * 10 if i % 2 == 0 else -i * 5)
            init_rows.append({
                "Close": mock_p, "High": mock_p * 1.001, "Low": mock_p * 0.999, "Volume": live_tick["Volume"]
            })
        st.session_state.multi_market_data[ticker] = pd.DataFrame(init_rows, index=init_times)

    if live_tick["Close"] > 0:
        new_df = pd.DataFrame([{"Close": live_tick["Close"], "High": live_tick["High"], "Low": live_tick["Low"], "Volume": live_tick["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.multi_market_data[ticker] = pd.concat([st.session_state.multi_market_data[ticker], new_df])
        st.session_state.multi_market_data[ticker] = st.session_state.multi_market_data[ticker].loc[~st.session_state.multi_market_data[ticker].index.duplicated(keep='last')].tail(12)

    calculated_df = process_quant_signals(st.session_state.multi_market_data[ticker].copy())
    latest_info = calculated_df.iloc[-1]
    
    realtime_trading_value = latest_info['Close'] * latest_info['Volume']
    
    signal_weight = 2
    if latest_info["타이밍 신호"] == "🔥 매수":
        signal_weight = 0
    elif latest_info["타이밍 신호"] == "🚨 청산":
        signal_weight = 1

    summary_rows.append({
        "종목코드": ticker,
        "종목명": actual_name,  
        "현재 타이밍 신호": latest_info["타이밍 신호"],
        "현재가": int(latest_info['Close']),
        "수급선": int(latest_info['VWAP']),
        "RSI": int(latest_info["RSI"]),
        "저항선": int(latest_info['Local_High']),
        "실시간거래대금": realtime_trading_value,
        "신호가중치": signal_weight
    })

st.markdown("---")

# 스마트폰 화면 맞춤형 순위 보드 렌더링
if summary_rows:
    summary_df = pd.DataFrame(summary_rows)
    # 신호 우선 정렬 후 실시간 거래대금 순 정렬
    summary_df = summary_df.sort_values(by=['신호가중치', '실시간거래대금'], ascending=[True, False]).head(25).reset_index(drop=True)
    
    if not summary_df[summary_df["신호가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg") 

    for index, row in summary_df.iterrows():
        sig = row["현재 타이밍 신호"]
        rank = index + 1
        
        # 이름과 번호 결합 출력
        card_title = f"**[{rank}위] {row['종목명']} ({row['종목코드']})**"
        
        card_metrics = f"💰 **{row['현재가']:,}원** | RSI: `{row['RSI']}` | 📊 대금: **{int(row['실시간거래대금']/100000000):,}억**"
        card_sub_metrics = f"🍏 수급: {row['수급선']:,}원 / 🛑 저항: {row['저항선']:,}원"
        
        if sig == "🔥 매수":
            with st.container():
                st.error(f"🎯 **{sig} 타점!** │ {card_title}")
                st.markdown(card_metrics)
                st.caption(card_sub_metrics)
                st.markdown("---")
        elif sig == "🚨 청산":
            with st.container():
                st.warning(f"🚨 **{sig}/익절** │ {card_title}")
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

# =================================================================
# 🔄 초단위 자동 리프레시 루프 (1.2초 인터벌)
# =================================================================
time.sleep(1.2)
st.rerun()
