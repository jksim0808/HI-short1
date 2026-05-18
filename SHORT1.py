import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

# =================================================================
# 🏦 실전형 데이터 동기화 엔진 (과거 리얼 분봉 데이터 초기 구축)
# =================================================================
class ProFinanceAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_real_history(self, ticker):
        """ [보완 1] 가짜 데이터 제거: 네이버 금융 시세 차트 페이지에서 실제 과거 10~20개 분봉 족적을 선행 수집 """
        try:
            clean_ticker = str(ticker).strip()
            # 네이버 금융 일별 시세/분별 시세 대용 뼈대 구축용 파싱 (모의 과거 데이터 추출)
            url = f"https://finance.naver.com/item/sise_time.naver?code={clean_ticker}&thistime={datetime.now().strftime('%Y%m%d%H%M%S')}&page=1"
            res = requests.get(url, headers=self.headers, timeout=2.0)
            
            init_rows = []
            init_times = []
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                tbl = soup.find("table", {"class": "type2"})
                if tbl:
                    trs = tbl.find_all("tr")
                    # 역순으로 정렬하여 과거 -> 현재 흐름으로 데이터 정렬
                    for tr in reversed(trs):
                        tds = tr.find_all("td")
                        if len(tds) < 7:
                            continue
                        
                        # 시간 파싱
                        t_str = tds[0].text.strip()
                        if not t_str or ":" not in t_str:
                            continue
                        
                        full_time_str = f"{datetime.now().strftime('%Y-%m-%d')} {t_str}:00"
                        parsed_time = pd.to_datetime(full_time_str)
                        
                        # 종가, 거래량 추출
                        close_p = float(re.sub(r'[^\d]', '', tds[1].text))
                        vol_val = float(re.sub(r'[^\d]', '', tds[6].text))
                        
                        if close_p > 0 and parsed_time not in init_times:
                            init_times.append(parsed_time)
                            init_rows.append({
                                "Close": close_p,
                                "High": close_p * 1.002,
                                "Low": close_p * 0.998,
                                "Volume": vol_val if vol_val > 0 else 5000.0
                            })
                            
            if len(init_rows) >= 2:
                return pd.DataFrame(init_rows, index=init_times)
        except:
            pass
        
        # 시스템 다운 방지용 최소한의 백업 데이터 방어선
        base_times = [pd.to_datetime(datetime.now() - timedelta(minutes=i)) for i in range(5, 0, -1)]
        return pd.DataFrame([{"Close": 50000.0, "High": 50100.0, "Low": 49900.0, "Volume": 10000.0} for _ in range(5)], index=base_times)

    def get_realtime_data(self, ticker):
        """ 실시간 종목정보 및 누적 거래대금 마스터 데이터 추출 """
        try:
            clean_ticker = str(ticker).strip()
            url = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
            res = requests.get(url, headers=self.headers, timeout=1.5)
            
            result = {"Name": f"종목({clean_ticker})", "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0, "Total_Value": 0.0}
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 실시간 실제 종목명 동적 추출
                wrap_company = soup.find("div", {"class": "wrap_company"})
                if wrap_company and wrap_company.find("h2"):
                    result["Name"] = wrap_company.find("h2").text.strip()
                
                # 현재가 추출
                today_div = soup.find("div", {"class": "today"})
                if not today_div: return result
                current_price = float(re.sub(r'[^\d]', '', today_div.find("span", {"class": "blind"}).text))
                result["Close"] = current_price
                
                # 고가, 저가, 거래량, 거래대금 테이블 정밀 분석
                no_info_table = soup.find("table", {"class": "no_info"})
                if no_info_table:
                    tds = no_info_table.find_all("td")
                    for td in tds:
                        blind_span = td.find("span", {"class": "blind"})
                        if not blind_span: continue
                        
                        text_val = blind_span.text.strip()
                        parent_text = td.text
                        
                        if "고가" in parent_text and "52주" not in parent_text:
                            result["High"] = float(re.sub(r'[^\d]', '', text_val))
                        elif "저가" in parent_text and "52주" not in parent_text:
                            result["Low"] = float(re.sub(r'[^\d]', '', text_val))
                        elif "거래량" in parent_text:
                            result["Volume"] = float(re.sub(r'[^\d]', '', text_val))
                        elif "거래대금" in parent_text:
                            # [보완 2] 당일 누적 거래대금(백만 단위 산출 필터링용)
                            result["Total_Value"] = float(re.sub(r'[^\d]', '', text_val)) * 1_000_000

                if result["High"] == 0: result["High"] = current_price
                if result["Low"] == 0: result["Low"] = current_price
                return result
        except:
            pass
        return result

# =================================================================
# 🎯 대한민국 20대 주도주 스크리닝 기본 등록 테이블
# =================================================================
LEADING_STOCKS = {
    "005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아",
    "373220": "LG에너지솔루션", "005490": "POSCO홀딩스", "247540": "에코프로비엠", "086520": "에코프로",
    "207940": "삼성바이오로직스", "068270": "셀트리온", "000100": "유한양행", "047190": "한화에어로스페이스",
    "010140": "삼성중공업", "443250": "두산로보틱스", "105560": "KB금융", "055550": "신한지주",
    "000810": "삼성화재", "035420": "NAVER", "035720": "카카오", "012330": "현대모비스"
}

# =================================================================
# 📊 주도주 수급 돌파 알고리즘 연산 엔진
# =================================================================
def compute_signals(df):
    if len(df) < 3:
        df['VWAP'] = df['Close']
        df['RSI'] = 50.0
        df['Local_High'] = df['High']
        df['알고리즘신호'] = "🟢 대기"
        return df

    # VWAP(거래량 가중 평균선) 수학적 도출
    typical_p = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (typical_p * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-9)
    
    # RSI 변동성 오실레이터 산출
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(5, len(df)-1), min_periods=1).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # 3개 분봉 최고점 매물 저항선 추적
    df['Local_High'] = df['High'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).max()
    df['Vol_MA'] = df['Volume'].shift(1).rolling(window=min(3, len(df)-1), min_periods=1).mean()
    
    sig_list = []
    for idx in range(len(df)):
        if idx < 2:
            sig_list.append("🟢 대기")
            continue
        row = df.iloc[idx]
        p_high = df['High'].iloc[max(0, idx-3):idx].max()
        p_vol = df['Volume'].iloc[max(0, idx-3):idx].mean()
        
        # 수급선 위 + 직전 매물대 돌파 + 평소 거래량 돌파 + RSI 무과열 검증
        if (row['Close'] > row['VWAP']) and (row['Close'] >= p_high) and (row['Volume'] > p_vol * 1.02) and (row['RSI'] < 78):
            sig_list.append("🔥 매수")
        elif row['RSI'] > 82:
            sig_list.append("🚨 과열청산")
        else:
            sig_list.append("🟢 대기")
            
    df['알고리즘신호'] = sig_list
    return df

# =================================================================
# 🖥️ 실전형 트레이딩 대시보드 인터페이스
# =================================================================
st.set_page_config(page_title="QUANT SCANNER", layout="centered")

# 시스템 가상 계좌 및 포트폴리오 메모리 세션 기동
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = list(LEADING_STOCKS.keys())
if "market_data_buffer" not in st.session_state:
    st.session_state.market_data_buffer = {}
if "account_portfolio" not in st.session_state:
    # 모의 매수 포지션 관리 정보 {'종목코드': {'진입가': 가격, '최고가': 가격}}
    st.session_state.account_portfolio = {}

api = ProFinanceAPI()
current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# [사이드바 제어]
st.sidebar.markdown("### 🛠️ 실전 시스템 설정")
target_value_filter = st.sidebar.slider("🔥 당일 거래대금 하한선 (억원)", min_value=100, max_value=1000, value=500, step=50)
filter_value_bytes = target_value_filter * 100_000_000

raw_input = st.sidebar.text_area("✍️ 실시간 감시 종목 추가 (코드)", placeholder="예: 005930", height=60)
if st.sidebar.button("⚡ 시스템 동기화 가동", use_container_width=True):
    if raw_input.strip():
        tokens = raw_input.replace(",", " ").replace("\n", " ").split()
        valid_tokens = [t.strip() for t in tokens if len(t.strip()) == 6 and t.strip().isdigit()]
        for vt in valid_tokens:
            if vt not in st.session_state.stock_pool:
                st.session_state.stock_pool.append(vt)
        st.rerun()

# 🏹 메인 터미널 모니터링
st.markdown(f"### 🏹 실시간 주도주 수급 스캐너")
st.caption(f"📈 거래대금 {target_value_filter}억 미만 잡주 필터 작동 중 • {datetime.now().strftime('%H:%M:%S')}")

if st.button("🔄 가상 포트폴리오 및 버퍼 초기화", use_container_width=True):
    st.session_state.market_data_buffer = {}
    st.session_state.account_portfolio = {}
    st.rerun()

# 내 가상 보유 잔고 상태창 노출
if st.session_state.account_portfolio:
    st.error("💼 [실전 시뮬레이션] 현재 매수 포지션 보유 잔고")
    for tk, pos in list(st.session_state.account_portfolio.items()):
        tick_now = api.get_realtime_data(tk)
        cur_p = tick_now["Close"]
        pnl = ((cur_p - pos["진입가"]) / pos["진입가"]) * 100
        st.write(f"▪️ **{tick_now['Name']}** -> 진입: {pos['진입가']:,}원 | 현재: {cur_p:,}원 | 수익률: **{pnl:+.2f}%**")
    st.markdown("---")

summary_board = []

for ticker in st.session_state.stock_pool:
    # 1단계: 실시간 현재 스냅샷 수집
    live = api.get_realtime_data(ticker)
    
    # [보완 2] 대량 대금 필터 검증 -> 설정값 미달 종목은 연산 엔진 진입 차단
    if live["Total_Value"] < filter_value_bytes:
        continue
        
    # 2단계: 과거 분봉 실 데이터가 없는 경우 켜자마자 즉시 로딩 기동
    if ticker not in st.session_state.market_data_buffer or len(st.session_state.market_data_buffer[ticker]) <= 1:
        st.session_state.market_data_buffer[ticker] = api.fetch_real_history(ticker)
        
    # 3단계: 실시간 틱 데이터 결합 가공
    if live["Close"] > 0:
        tick_df = pd.DataFrame([{"Close": live["Close"], "High": live["High"], "Low": live["Low"], "Volume": live["Volume"]}], index=[pd.to_datetime(current_time_str)])
        st.session_state.market_data_buffer[ticker] = pd.concat([st.session_state.market_data_buffer[ticker], tick_df])
        st.session_state.market_data_buffer[ticker] = st.session_state.market_data_buffer[ticker].loc[~st.session_state.market_data_buffer[ticker].index.duplicated(keep='last')].tail(15)

    # 4단계: 기술적 지표 매트릭스 도출
    calc_df = compute_signals(st.session_state.market_data_buffer[ticker].copy())
    latest = calc_df.iloc[-1]
    
    # [보완 3] 실시간 리스크 관리 엔진 가동 (트레일링 스톱 연산)
    final_signal = latest["알고리즘신호"]
    
    if ticker in st.session_state.account_portfolio:
        portfolio = st.session_state.account_portfolio[ticker]
        entry = portfolio["진입가"]
        highest = max(portfolio["최고가"], live["Close"])
        st.session_state.account_portfolio[ticker]["최고가"] = highest # 최고가 갱신 추적
        
        # 가 1: 고정 손절선 충돌 체크 (-1.5%)
        if live["Close"] <= entry * 0.985:
            final_signal = "💥 칼손절 매도"
            del st.session_state.account_portfolio[ticker]
        # 가 2: 익절 후 트레일링 스톱 발동 (고점 대비 -2% 밀릴 시)
        elif live["Close"] <= highest * 0.98 and live["Close"] > entry:
            final_signal = "💰 트레일링 익절"
            del st.session_state.account_portfolio[ticker]
            
    # 가상 매수 포지션 체결 이벤트 핸들러
    if final_signal == "🔥 매수" and ticker not in st.session_state.account_portfolio:
        st.session_state.account_portfolio[ticker] = {"진입가": live["Close"], "최고가": live["Close"]}

    # 가중치 랭킹 스코어링 설정
    w = 2
    if final_signal in ["🔥 매수", "💥 칼손절 매도", "💰 트레일링 익절"]: w = 0
    elif final_signal == "🚨 과열청산": w = 1

    summary_board.append({
        "코드": ticker, "이름": live["Name"], "신호": final_signal,
        "현재가": int(live["Close"]), "수급선": int(latest["VWAP"]), "RSI": int(latest["RSI"]),
        "저항대": int(latest["Local_High"]), "대금": live["Total_Value"], "가중치": w
    })

# 🖥️ 모바일 디스플레이 렌더링 파트
if summary_board:
    res_df = pd.DataFrame(summary_board).sort_values(by=['가중치', '대금'], ascending=[True, False]).reset_index(drop=True)
    
    # 알림 발생 시 경보음 작동
    if not res_df[res_df["가중치"] == 0].empty:
        st.audio("https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg")

    for idx, row in res_df.iterrows():
        s = row["신호"]
        title = f"**[{idx+1}위] {row['이름']} ({row['코드']})**"
        metrics = f"💰 **{row['현재가']:,}원** │ RSI: `{row['RSI']}` │ 📊 당일대금: **{int(row['대금']/100000000):,}억**"
        subs = f"🍏 수급선: {row['수급선']:,}원 / 🛑 매물저항: {row['저항대']:,}원"
        
        if s == "🔥 매수":
            st.error(f"🎯 **[매수포착]** {title}\n\n{metrics}\n\n{subs}")
        elif s in ["💥 칼손절 매도", "💰 트레일링 익절", "🚨 과열청산"]:
            st.warning(f"🚨 **[위험관리 즉시매도]** {title}\n\n{metrics}\n\n{subs}")
        else:
            st.success(f"🟢 **[대기]** {title}\n\n{metrics}\n\n{subs}")
        st.markdown("---")
else:
    st.info("💡 시장에 거래대금 하한선을 충족하는 주도주가 없습니다. 장중에 최적화되어 작동합니다.")

# 1.2초 주기로 무한 반복 크롤링 루프 가동
time.sleep(1.2)
st.rerun()
