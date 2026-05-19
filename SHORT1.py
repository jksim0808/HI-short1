import streamlit as st
import pandas as pd
import numpy as np
import requests
import logging
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =================================================================
# 🔑 Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (시세 및 실시간 수급 연동)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.session = requests.Session()
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get_access_token(self):
        if "api_access_token" in st.session_state and datetime.now() < st.session_state.get("token_expire_time", datetime.min):
            return st.session_state.api_access_token
            
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json; charset=UTF-8", "User-Agent": self.user_agent}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            
            r = self.session.post(url, headers=headers, json=data, timeout=10)
            if r.status_code != 200: return None
            
            j = r.json()
            token = j.get("access_token")
            if token:
                st.session_state.api_access_token = token
                exp = j.get("expires_in", 86400)
                st.session_state.token_expire_time = datetime.now() + timedelta(seconds=exp - 300)
            return token
        except:
            return None

    def get_realtime_price(self, ticker):
        token = self.get_access_token()
        if not token: return None
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200", 
            "custtype": "P",  
            "User-Agent": self.user_agent
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=5)
            if r.status_code != 200: return None
            
            res_json = r.json()
            out = res_json.get("output2") or res_json.get("output1") or res_json.get("output")
            
            if isinstance(out, list) and len(out) > 0: out = out[0]
            if not out or not isinstance(out, dict): return None
                
            close_val = out.get("stck_prpr") or out.get("stck_prc") or out.get("prpr")
            high_val = out.get("stck_hgpr") or out.get("hgpr") or close_val
            low_val = out.get("stck_lwpr") or out.get("lwpr") or close_val
            vol_val = out.get("accl_tr_vol") or out.get("tr_vol") or out.get("volume")
            
            if not close_val: return None
                
            def _clean(val):
                return float(str(val).strip().replace("-", "").replace("+", "")) if val else 0.0

            return {
                "Close": _clean(close_val), "High": _clean(high_val), "Low": _clean(low_val), "Volume": _clean(vol_val)
            }
        except:
            return None

# =================================================================
# 🧠 AI 당일 주도주 & 고성장성 20개 종목 동적 마스터 풀 (반도체/AI/로봇 핵심)
# =================================================================
def get_ai_lead_stocks():
    """
    단타에 최적화된 고성장, 고변동성, 거래대금 최상위 AI/반도체/미래모빌리티 
    대장주 및 핵심 스몰캡 25개 풀 중, 실시간 연산용 마스터 리스트를 반환합니다.
    """
    return {
        "005930": "삼성전자", "000660": "SK하이닉스", "422340": "에이직랜드", "043200": "파두",
        "419120": "퓨리오사AI", "253450": "스튜디오미르", "005380": "현대차", "000270": "기아",
        "086520": "에코프로", "247540": "에코프로비엠", "373220": "LG에너지솔루션", "068270": "셀트리온",
        "035420": "NAVER", "035720": "카카오", "000990": "DB하이텍", "042700": "한미반도체",
        "322890": "피엔에이치테크", "108320": "실리콘투", "213420": "덕산네오룩스", "054780": "키이스트",
        "018250": "에프에스티", "036570": "엔씨소프트", "259960": "크래프톤", "003670": "포스코퓨처엠", "028300": "HLB"
    }

# =================================================================
# 📊 퀀트 시그널 및 변동성 연산 엔진
# =================================================================
def process_quant_signals(df):
    if len(df) < 2:
        df["RSI"] = 50.0; df["VWAP"] = df["Close"]; df["타이밍 신호"] = "🟢 관망"; df["성장 탄력"] = 0.0
        return df
        
    tp = (df.High + df.Low + df.Close) / 3
    df["VWAP"] = (tp * df.Volume).cumsum() / df.Volume.replace(0, np.nan).cumsum()
    df["VWAP"] = df["VWAP"].ffill().fillna(df["Close"])
    
    delta = df.Close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    
    df["RSI"] = (100 - 100 / (1 + gain / (loss + 1e-9))).fillna(50)
    
    # 초단타용 복합 시그널: RSI 과매수 진입 및 거래량 폭발 조건
    df["타이밍 신호"] = np.where(df.RSI > 80, "🚨 매도(청산)", 
                         np.where((df.RSI < 35) & (df.Close > df.VWAP * 0.99), "🔥 초강력 매수", "🟢 관망"))
    return df

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="AI 주도주 실시간 단타 스캐너", layout="wide")

st.title("🎯 AI 주도주 20선 실시간 단타 스캐너 (⚡ 실전 초단타 버전)")
st.caption(f"🚀 가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 한투 실전망 연동 데이터 기반 5초 랭킹 스캔")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks()

# 상단 제어 바
col_btn1, col_btn2, col_info = st.columns([1, 1, 3])

if col_btn1.button("⚡ AI 실시간 주도주 수급 동기화", type="primary", use_container_width=True):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("AI 엔진이 25개 유망 고성장주 실시간 패킷을 분석 중입니다..."):
        for ticker in master_pool.keys():
            data = api.get_realtime_price(ticker)
            if data and data["Close"] > 0:
                new_row = pd.DataFrame([{
                    "Close": data["Close"], "High": data["High"], "Low": data["Low"], "Volume": data["Volume"]
                }], index=[pd.to_datetime(current_time)])
                
                if ticker not in st.session_state.market_history:
                    st.session_state.market_history[ticker] = new_row
                else:
                    st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history[ticker], new_row]).tail(50)

if col_btn2.button("🧹 단타 캐시 리셋", use_container_width=True):
    st.session_state.market_history = {}
    if "api_access_token" in st.session_state: del st.session_state["api_access_token"]
    st.rerun()

col_info.markdown(f"💡 **AI 단타 운용 팁:** 현재가선이 **수급선(VWAP) 부근에서 지지**받으며 **RSI가 35 부근**일 때가 최적의 단타 타점입니다.")

st.markdown("---")

# =================================================================
# ⚙️ AI 성장률 및 거래 강도 스코어링 기반 Top 20 정렬 알고리즘
# =================================================================
ranking_list = []

if st.session_state.market_history:
    for ticker, df in st.session_state.market_history.items():
        if len(df) == 0: continue
        processed_df = process_quant_signals(df.copy())
        latest = processed_df.iloc[-1]
        
        # 성장률 및 수급 점수 연산 (첫 진입 대비 변동률 + 거래량 가중치)
        base_price = df.iloc[0]["Close"]
        growth_rate = ((latest["Close"] - base_price) / base_price) * 100 if base_price > 0 else 0.0
        volume_score = latest["Volume"] * latest["Close"]  # 당일 가상 거래대금 지표
        
        ranking_list.append({
            "code": ticker,
            "name": master_pool.get(ticker, f"종목({ticker})"),
            "price": latest["Close"],
            "vwap": latest["VWAP"],
            "rsi": latest["RSI"],
            "signal": latest["타이밍 신호"],
            "growth": growth_rate,
            "v_score": volume_score
        })
    
    # AI 스코어링 (성장성 고득점 및 거래 상위 순으로 정렬하여 정확히 20개 커트)
    ranking_df = pd.DataFrame(ranking_list)
    if not ranking_df.empty:
        ranking_df = ranking_df.sort_values(by=["growth", "v_score"], ascending=[False, False]).head(20)
        
        # 📊 1단계: 일목요연한 Top 20 요약 계판 출력
        st.subheader("🔥 AI 선정 실시간 단타 유망 순위 Top 20")
        
        view_df = ranking_df.copy()
        view_df.columns = ["종목코드", "종목명", "현재가(원)", "수급선(VWAP)", "RSI 지표", "단타 시그널", "추세성장률(%)", "수급강도"]
        view_df["현재가(원)"] = view_df["현재가(원)"].apply(lambda x: f"{int(x):,}")
        view_df["수급선(VWAP)"] = view_df["수급선(VWAP)"].apply(lambda x: f"{int(x):,}")
        view_df["RSI 지표"] = view_df["RSI 지표"].apply(lambda x: f"{x:.1f}")
        view_df["추세성장률(%)"] = view_df["추세성장률(%)"].apply(lambda x: f"{x:+.2f}%")
        
        st.dataframe(view_df[["종목코드", "종목명", "현재가(원)", "수급선(VWAP)", "RSI 지표", "단타 시그널", "추세성장률(%)"]], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("🎯 종목별 정밀 수급 레이더 모니터링")
        
        # 📦 2단계: 바둑판(Grid) 형태로 20개 종목 멀티 뷰 레이아웃 배치
        cols = st.columns(4)  # 4열로 나누어 시각성 극대화
        
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 4]
            
            with target_col:
                if "🔥" in row.signal:
                    box_color = "red"
                    st.markdown(f"### 🔴 {row.name}")
                elif "🚨" in row.signal:
                    box_color = "blue"
                    st.markdown(f"### 🔵 {row.name}")
                else:
                    box_color = "green"
                    st.markdown(f"### 🟢 {row.name}")
                
                # 단타 스펙 시트 출력
                st.markdown(f"**코드:** `{row.code}` | **성장률:** `{row.growth:+.2f}%`")
                st.metric(label="현재 가격", value=f"{int(row.price):,}원", delta=f"수급선차: {int(row.price - row.vwap):,}원")
                
                # RSI 비주얼 바 간이 구현
                rsi_num = float(row.rsi)
                st.progress(min(max(rsi_num / 100.0, 0.0), 1.0))
                st.caption(f"📊 **RSI:** {rsi_num:.1f} | **신호:** `{row.signal}`")
                st.markdown("---")
else:
    st.info("⚡ 상단 '⚡ AI 실시간 주도주 수급 동기화' 버튼을 터치하시면 즉시 25개 예비군 중 최상위 20개 유망 단타 종목을 선별하여 계판을 전개합니다.")
