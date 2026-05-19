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
# 🏦 한투 실전투자 전용 정밀 통신 엔진 (output2 시세 교차 매핑 패치)
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
            
        primary_url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        secondary_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
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
            r = self.session.get(primary_url, headers=headers, params=params, timeout=10)
            if r.status_code == 404:
                r = self.session.get(secondary_url, headers=headers, params=params, timeout=10)
                
            if r.status_code != 200:
                st.error(f"🚨 [시세 호출 실패] 종목코드 {ticker} (HTTP {r.status_code})")
                return None
                
            res_json = r.json()
            
            # -------------------------------------------------------------
            # 🎯 [수정 핵심] 대포 포커싱을 output2(시세/체결 패킷)로 전면 전환
            # -------------------------------------------------------------
            # 현재 호가 데이터가 output1에 들어오는 것이 확인되었으므로, 체결 데이터인 output2를 최우선 타깃으로 잡습니다.
            out = res_json.get("output2") or res_json.get("output1") or res_json.get("output")
            
            if isinstance(out, list) and len(out) > 0:
                out = out[0]
                
            if not out or not isinstance(out, dict):
                out = res_json if isinstance(res_json, dict) else {}
                
            # 시세 필드 매핑 데이터 추출 (stck_prpr, stck_hgpr, stck_lwpr, accl_tr_vol 추출 자동 스위칭)
            close_val = out.get("stck_prpr") or out.get("stck_prc") or out.get("prpr")
            high_val = out.get("stck_hgpr") or out.get("hgpr") or close_val
            low_val = out.get("stck_lwpr") or out.get("lwpr") or close_val
            vol_val = out.get("accl_tr_vol") or out.get("tr_vol") or out.get("volume")

            # 만약 복합 수색으로도 못 잡았을 경우, 딕셔너리 내부 전체 탐색 (방어선)
            if not close_val:
                # 최악의 경우 output1과 output2를 뒤집어서 재수색
                alt_out = res_json.get("output1") if "output2" in res_json else res_json.get("output2")
                if isinstance(alt_out, list) and len(alt_out) > 0: alt_out = alt_out[0]
                if isinstance(alt_out, dict):
                    close_val = alt_out.get("stck_prpr") or alt_out.get("stck_prc")
                    high_val = alt_out.get("stck_hgpr") or close_val
                    low_val = alt_out.get("stck_lwpr") or close_val
                    vol_val = alt_out.get("accl_tr_vol")

            # 최종 데이터 유실 보호벽
            if not close_val:
                st.warning(f"⚠️ [필드 구조 최종 오류] 체결 데이터 필드를 수색하지 못했습니다.\n\n해당 파트 필드샘플: `{list(out.keys())[:5]}`")
                return None
                
            def _clean(val):
                if val is None: return 0.0
                return float(str(val).strip().replace("-", "").replace("+", ""))

            return {
                "Close": _clean(close_val),
                "High": _clean(high_val),
                "Low": _clean(low_val),
                "Volume": _clean(vol_val) if _clean(vol_val) > 0 else 1.0,
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
st.caption(f"💡 현재 화면 데이터 시점: {datetime.now().strftime('%H:%M:%S')} | 📡 가동모드: 실전망 output2(시세 체결) 정밀 정조준 상태")

# 종목 풀 설정
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = ["005930", "000660", "005380", "000270"]
if "market_history" not in st.session_state:
    st.session_state.market_history = {}

# 데이터 갱신 및 조회 제어
api = KoreaInvestmentOfficialAPI()
col_left, col_right = st.columns(2)

if col_left.button("🔥 한투 실시간 시세 동기화", type="primary", use_container_width=True, key="btn_sync_live_output2"):
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

if col_right.button("🧹 캐시 데이터 초기화", use_container_width=True, key="btn_clear_cache_output2"):
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
