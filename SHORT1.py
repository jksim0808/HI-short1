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
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (데이터 파싱 규격 보정)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.session = requests.Session()
        
        # 한투 방화벽 통과용 표준 크롬 브라우저 식별자
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
            
            if r.status_code != 200:
                st.error(f"🚨 [토큰 발급 실패] 한투 실전 서버가 연결을 거부했습니다. (HTTP {r.status_code})")
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
            
        # 404 우회 듀얼 라우팅 유지
        primary_url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        secondary_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200", # 국내주식 주식현재가 시세 조회 tr_id
            "custtype": "P",  
            "User-Agent": self.user_agent
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            r = self.session.get(primary_url, headers=headers, params=params, timeout=10)
            if r.status_code == 404:
                r = self.session.get(secondary_url, headers=headers, params=params, timeout=10)
                
            if r.status_code != 200:
                st.error(f"🚨 [시세 호출 실패] 종목코드 {ticker} (HTTP {r.status_code})")
                return None
                
            res_json = r.json()
            out = res_json.get("output", {})
            
            # [수정 핵심] 한투 실전망 데이터 필드 검증 및 예외 완전 차단 방어막
            # 일부 실전 API 응답 체계에 따라 데이터가 리스트로 오거나 key 형식이 다를 때를 대비한 3중 안전 안전장치
            if isinstance(out, list) and len(out) > 0:
                out = out[0]
                
            # 한투 공식 실전 필드명 대조 및 안전 가로채기
            close_val = out.get("stck_prpr") or out.get("stck_prc")
            
            if not close_val:
                st.warning(f"⚠️ [데이터 매핑 경고] '정상처리' 되었으나 데이터 필드가 비어있습니다. 응답 메시지: {res_json.get('msg1')}")
                # 디버깅을 위해 서버가 준 원본 Key 목록 출력
                logger.info(f"한투 서버 응답 필드 목록: {list(out.keys()) if out else 'None'}")
                return None
                
            return {
                "Close": float(close_val),
                "High": float(out.get("stck_hgpr", close_val)),
                "Low": float(out.get("stck_lwpr", close_val)),
                "Volume": float(out.get("accl_tr_vol", 0) or 0),
                "Source": "🔥 한투 실전망 직결 성공"
            }
        except Exception as e:
            st.error(f"💥 [시세 통신 예외] {str(e)}")
            return None

# =================================================================
# 📊 퀀트 시그널 연산 엔진
# =================================================================
def process_quant_signals(df):
    if len(df) < 2:
        df["RSI"] = 50.0; df["VWAP"] = df["Close"]; df["타이밍 신호"] = "🟢 관망"
        return df
        
    tp = (df.High + df.Low + df.Close) / 3
    df["VWAP"] = (tp * df.Volume).cumsum() / df.Volume.replace(0, np.nan).cumsum()
    df["VWAP"] = df["VWAP"].ffill().fillna(df["Close"])
    
    delta = df.Close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    
    df["RSI"] = (100 - 100 / (1 + gain / (loss + 1e-9))).fillna(50)
    df["타이밍 신호"] = np.where(df.RSI > 82, "🚨 익절/청산", "🟢 관망")
    return df

# =================================================================
# 🖥️ UI 및 모니터링 화면 구성
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너 (개선판)", layout="centered")
st.title("🏹 실전 수급 스캐너 (개선판)")
st.caption(f"💡 현재 화면 데이터 시점: {datetime.now().strftime('%H:%M:%S')} | 📡 가동모드: 실전매매 데이터 필드 튜닝 완료")

# 종목 풀 설정
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = ["005930", "000660", "005380", "000270"]
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
        
        name_map = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아"}
        stock_name = name_map.get(ticker, f"종목({ticker})")
        
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
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (듀얼 라우팅 우회 패치)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.session = requests.Session()
        
        # [방어 핵심 1] 한투 방화벽 통과용 표준 크롬 브라우저 식별자 정의
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
            
            if r.status_code != 200:
                st.error(f"🚨 [토큰 발급 실패] 한투 실전 서버가 연결을 거부했습니다. (HTTP {r.status_code})")
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
            
        # [방어 핵심 2] 한투 서버 내부 URL 매핑 버그 교차 검증용 듀얼 라우팅 주소 리스트
        primary_url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        secondary_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price" # 복수형 변형 경로
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200",
            "custtype": "P",  # P: 개인 고객 설정 필수
            "User-Agent": self.user_agent
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            # 1차 시도 (기본 경로)
            r = self.session.get(primary_url, headers=headers, params=params, timeout=10)
            
            # 1차 시도에서 404가 발생하면 즉시 2차 예비 경로로 스위칭
            if r.status_code == 404:
                logger.info(f"🔄 1차 URL 404 감지: {ticker} 대체 경로 라우팅 우회를 시도합니다.")
                r = self.session.get(secondary_url, headers=headers, params=params, timeout=10)
                
            if r.status_code != 200:
                st.error(f"🚨 [시세 호출 실패] 종목코드 {ticker} (최종 HTTP {r.status_code})")
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
                "Source": "🔥 한투 실전망 직결 성공"
            }
        except Exception as e:
            st.error(f"💥 [시세 통신 예외] {str(e)}")
            return None

# =================================================================
# 📊 퀀트 시그널 연산 엔진
# =================================================================
def process_quant_signals(df):
    if len(df) < 2:
        df["RSI"] = 50.0; df["VWAP"] = df["Close"]; df["타이밍 신호"] = "🟢 관망"
        return df
        
    tp = (df.High + df.Low + df.Close) / 3
    df["VWAP"] = (tp * df.Volume).cumsum() / df.Volume.replace(0, np.nan).cumsum()
    df["VWAP"] = df["VWAP"].ffill().fillna(df["Close"])
    
    delta = df.Close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    
    df["RSI"] = (100 - 100 / (1 + gain / (loss + 1e-9))).fillna(50)
    df["타이밍 신호"] = np.where(df.RSI > 82, "🚨 익절/청산", "🟢 관망")
    return df

# =================================================================
# 🖥️ UI 및 모니터링 화면 구성
# =================================================================
st.set_page_config(page_title="실전 수급 스캐너 (개선판)", layout="centered")
st.title("🏹 실전 수급 스캐너 (개선판)")
st.caption(f"💡 현재 화면 데이터 시점: {datetime.now().strftime('%H:%M:%S')} | 📡 가동모드: 실전매매 전용 주소 보완판")

# 종목 풀 설정
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = ["005930", "000660", "005380", "000270"]
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
        
        name_map = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차", "000270": "기아"}
        stock_name = name_map.get(ticker, f"종목({ticker})")
        
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
    st.info("상단 '🔥 한투 실시간 시세 동기화' 버튼을 누르시면 실전망 데이터를 호출하여 퀀트 스캔을 시작합니다.")
