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
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (방화벽 우회 패치)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.session = requests.Session()
        
        # [404 방어 핵심 1] 한투 방화벽 통과용 표준 크롬 브라우저 식별자 정의
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get_access_token(self):
        if "api_access_token" in st.session_state and datetime.now() < st.session_state.get("token_expire_time", datetime.min):
            return st.session_state.api_access_token
            
        try:
            r = self.session.post(
                f"{self.base_url}/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret},
                # 토큰 발급 시에도 User-Agent 전달 필수
                headers={"content-type": "application/json; charset=UTF-8", "User-Agent": self.user_agent},
                timeout=10
            )
            
            if r.status_code != 200:
                st.error(f"🚨 [토큰 발급 실패] 한투 서버 응답 오류 (HTTP {r.status_code})")
                return None
                
            j = r.json()
            token = j.get("access_token")
            if token:
                st.session_state.api_access_token = token
                exp = j.get("expires_in", 86400)
                st.session_state.token_expire_time = datetime.now() + timedelta(seconds=exp - 300)
            return token
        except Exception as e:
            st.error(f"💥 [인증 통신 예외] {str(e)}")
            return None

    def get_realtime_price(self, ticker):
        token = self.get_access_token()
        if not token: 
            return None
            
        try:
            # [404 방어 핵심 2] 가이드라인 필수 헤더 규격 완벽 동기화 (custtype 및 User-Agent 추가)
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": "FHKST01010200",
                "custtype": "P",  # P: 개인 고객 설정 필수
                "User-Agent": self.user_agent
            }
            
            r = self.session.get(
                f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price",
                headers=headers,
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()},
                timeout=10
            )
            
            if r.status_code != 200:
                st.error(f"🚨 [시세 호출 실패] 종목코드 {ticker} (HTTP {r.status_code})")
                return None
                
            res_json = r.json()
            out = res_json.get("output", {})
            
            if not out or "stck_prpr" not in out:
                st.warning(f"⚠️ [데이터 경고] 한투 응답 메시지: {res_json.get('msg1')}")
                return None
                
            return {
                "Close": float(out.get("stck_prpr", 0)),
                "High": float(out.get("stck_hgpr", 0)),
                "Low": float(out.get("stck_lwpr", 0)),
                "Volume": float(out.get("accl_tr_vol", 0) or 0),
                "Source": "🔥 한투 실전망"
            }
        except Exception as e:
            st.error(f"💥 [시세 통신 예외] {str(e)}")
            return None

# =================================================================
# 📊 퀀트 시그널 연산 엔진 (대표님 알고리즘 유지 보정)
# =================================================================
def process_quant_signals(df):
    if len(df) < 2:
        df["RSI"] = 50.0; df["VWAP"] = df["Close"]; df["타이밍 신호"] = "🟢 관망"
        return df
        
    tp = (df.High + df.Low + df.Close) / 3
    df["VWAP"] = (tp * df.Volume).cumsum() / df.Volume.replace(0, np.nan).cumsum()
    df["VWAP"] = df["VWAP"].ffill().fillna(df["Close"]) # 0거래량 예외 방어
    
    delta = df.Close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    
    df["RSI"] = (100 - 100 / (1 + gain / (loss + 1e-9))).fillna(50)
    
    # 타이밍 신호 분기 (기존 로직 유지)
    df["타이밍 신호"] = np.where(df.RSI > 82, "🚨 익절/청산", "🟢 관망")
    return df

# =================================================================
# 🖥️ UI 및 모니터링 화면 구성
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너 (개선판)", layout="centered")
st.title("🏹 실전 수급 스캐너 (개선판)")
st.caption("기존 코드 기반 방화벽 차단(404 에러) 완벽 패치 버전")

# 종목 풀 설정
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = ["005930", "000660", "005380", "000270"] # 삼전, 하이닉스, 현대, 기아
if "market_history" not in st.session_state:
    st.session_state.market_history = {}

# 데이터 갱신 및 조회 제어
api = KoreaInvestmentOfficialAPI()
col_left, col_right = st.columns(2)

if col_left.button("🔥 한투 실시간 시세 동기화", type="primary", use_container_width=True):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for ticker in st.session_state.stock_pool:
        data = api.get_realtime_price(ticker)
        if data and data["Close"] > 0:
            # 타임시리즈 데이터 프레임 누적 빌드
            new_row = pd.DataFrame([{
                "Close": data["Close"], "High": data["High"], "Low": data["Low"], "Volume": data["Volume"]
            }], index=[pd.to_datetime(current_time)])
            
            if ticker not in st.session_state.market_history:
                st.session_state.market_history[ticker] = new_row
            else:
                st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history[ticker], new_row]).tail(30)

if col_right.button("🧹 캐시 데이터 초기화", use_container_width=True):
    st.session_state.market_history = {}
    if "api_access_token" in st.session_state:
        del st.session_state["api_access_token"]
    st.rerun()

st.markdown("---")

# 실시간 모니터링 카드 대시보드 출력
if st.session_state.market_history:
    for ticker, df in st.session_state.market_history.items():
        processed_df = process_quant_signals(df.copy())
        latest = processed_df.iloc[-1]
        
        # 종목명 가독성 처리
        name_map = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아"}
        stock_name = name_map.get(ticker, f"종목({ticker})")
        
        # 신호별 카드 UI 분기
        if latest["타이밍 신호"] == "🚨 익절/청산":
            with st.container():
                st.warning(f"🚨 **{latest['타이밍 신호']} | {stock_name} ({ticker})**")
                st.markdown(f"**현재가:** {int(latest['Close'])}원 | **수급선(VWAP):** {int(latest['VWAP'])}원 | **RSI:** {int(latest['RSI'])}")
                st.markdown("---")
        else:
            with st.container():
                st.success(f"🟢 **{latest['타이밍 신호']} | {stock_name} ({ticker})**")
                st.markdown(f"**현재가:** {int(latest['Close'])}원 | **수급선(VWAP):** {int(latest['VWAP'])}원 | **RSI:** {int(latest['RSI'])}")
                st.markdown("---")
else:
    st.info("상단 '🔥 한투 실시간 시세 동기화' 버튼을 누르시면 실전망 데이터를 호출하여 퀀트 스캔을 시작합니다.")import streamlit as st
import pandas as pd, numpy as np, requests, logging
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
APP_KEY = st.secrets.get("HANTU_APP_KEY","").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET","").strip()

class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url="https://openapi.koreainvestment.com:9443"
        self.app_key=APP_KEY; self.app_secret=APP_SECRET
        self.session=requests.Session()
        retry=Retry(total=3,backoff_factor=1,status_forcelist=[500,502,503,504])
        self.session.mount("https://",HTTPAdapter(max_retries=retry))

    def get_access_token(self):
        if "api_access_token" in st.session_state and datetime.now() < st.session_state.get("token_expire_time",datetime.min):
            return st.session_state.api_access_token
        r=self.session.post(
            f"{self.base_url}/oauth2/tokenP",
            json={"grant_type":"client_credentials","appkey":self.app_key,"appsecret":self.app_secret},
            headers={"content-type":"application/json"},
            timeout=10
        )
        j=r.json(); token=j.get("access_token")
        if token:
            st.session_state.api_access_token=token
            exp=j.get("expires_in",86400)
            st.session_state.token_expire_time=datetime.now()+timedelta(seconds=exp-300)
        return token

    def get_realtime_price(self,ticker):
        token=self.get_access_token()
        if not token: return None
        r=self.session.get(
            f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price",
            headers={"authorization":f"Bearer {token}","appkey":self.app_key,"appsecret":self.app_secret,"tr_id":"FHKST01010200"},
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":ticker},
            timeout=10
        )
        out=r.json().get("output",{})
        return {
            "Close":float(out.get("stck_prpr",0)),
            "High":float(out.get("stck_hgpr",0)),
            "Low":float(out.get("stck_lwpr",0)),
            "Volume":float(out.get("accl_tr_vol",0) or 0),
            "Source":"🔥 한투 실전망"
        }

def process_quant_signals(df):
    if len(df)<2:
        df["RSI"]=50; df["VWAP"]=df["Close"]; df["타이밍 신호"]="🟢 관망"; return df
    tp=(df.High+df.Low+df.Close)/3
    df["VWAP"]=(tp*df.Volume).cumsum()/df.Volume.replace(0,np.nan).cumsum()
    delta=df.Close.diff()
    gain=delta.clip(lower=0).rolling(14,min_periods=1).mean()
    loss=(-delta.clip(upper=0)).rolling(14,min_periods=1).mean()
    df["RSI"]=(100-100/(1+gain/(loss+1e-9))).fillna(50)
    df["타이밍 신호"]=np.where(df.RSI>82,"🚨 익절/청산","🟢 관망")
    return df

st.title("실전 수급 스캐너 (개선판)")
st.write("기존 코드 기반 안정성 개선 버전")
