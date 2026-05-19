import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ Streamlit 최상단 설정 및 환경변수
# =====================================================================
st.set_page_config(page_title="주도주 스캐너 Pro", layout="wide")
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("439960", "코스모로보틱스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

RESTRICTED_STAT = ["51", "52", "53", "54", "58", "59"] 

# =====================================================================
# 🛠️ 유틸리티 함수군
# =====================================================================
def safe_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace(",", "")
        if s.endswith("%"):
            s = s[:-1]
        if s.startswith("+") or s.startswith("-"):
            s = s[1:]
        return float(s)
    except:
        return default

def extract_six_digits(val):
    if not val:
        return None
    s = str(val).strip()
    import re
    match = re.search(r'(?<!\d)\d{6}(?!\d)', s)
    return match.group(0) if match else None

def is_noise_name(name):
    if not name:
        return False
    n = str(name).upper()
    noise_keywords = ["KODEX", "TIGER", "스팩", "리츠", "우", "인버스", "레버리지"]
    return any(k in n for k in noise_keywords)

# =====================================================================
# 🔄 세션 및 재시도 제어 엔진
# =====================================================================
class RetrySession:
    def __init__(self):
        self.session = requests.Session()

    def get(self, url, headers=None, params=None, timeout=3.0):
        return self._request_with_retry("GET", url, headers=headers, params=params, timeout=timeout)

    def post(self, url, json=None, timeout=3.0):
        return self._request_with_retry("POST", url, json=json, timeout=timeout)

    def _request_with_retry(self, method, url, headers=None, params=None, json=None, timeout=3.0):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.session.request(method, url, headers=headers, params=params, json=json, timeout=timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    time.sleep(0.5)
                    continue
                return resp
            except:
                if attempt == max_retries - 1:
                    return None
                time.sleep(0.5)
        return None

# =====================================================================
# 🏹 한투 API 코어 오피셜 클래스 (시세 규격 오피셜 보정 완료)
# =====================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret
        self.session = RetrySession()
        self._token_cache = {"token": None, "expires_at": None}

    def get_fresh_access_token(self, force_refresh=False):
        now = datetime.now(tz=timezone.utc)
        if not force_refresh and self._token_cache["token"] and self._token_cache["expires_at"] > now:
            return self._token_cache["token"]

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        payload = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        resp = self.session.post(url, json=payload, timeout=3.0)
        
        if resp is not None:
            data = resp.json()
            if resp.status_code == 200:
                token = data.get("access_token")
                expired_at_str = data.get("token_expired_at")
                if expired_at_str:
                    try:
                        exp_dt = datetime.strptime(expired_at_str.strip(), "%Y-%m-%d %H:%M:%S")
                        expires_at = exp_dt.replace(tzinfo=timezone.utc)
                    except:
                        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(data.get("expires_in", 86400)))
                else:
                    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(data.get("expires_in", 86400)))
                
                self._token_cache = {"token": token, "expires_at": expires_at}
                return token
            else:
                err_code = data.get("error_code", "알 수 없음")
                err_msg = data.get("error_description", "앱키/시크릿 키 권한 인증 실패")
                st.error(f"❌ 한투 인증 에러 [{err_code}]: {err_msg}")
        else:
            st.error("❌ 한투 인증 서버 통신 타임아웃")
        return None

    def get_market_leading_tickers(self, token):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        # 오피셜 필수 규격 헤더 전체 동기화
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}", 
            "appkey": self.app_key, 
            "appsecret": self.app_secret, 
            "tr_id": "FHPST01710000",
            "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"}
        
        resp = self.session.get(url, headers=headers, params=params, timeout=4.0)
        if not resp or resp.status_code != 200:
            return BACKUP_MASTER_POOL
            
        res = resp.json()
        output = res.get("output")
        if isinstance(output, dict):
            output = [output]
        if not output:
            return BACKUP_MASTER_POOL

        pool = []
        for item in output:
            ticker = extract_six_digits(item.get("mksc_shrn_iscd", ""))
            name = item.get("hts_kor_isnm", item.get("data_name", ""))
            try:
                price = float(item.get("stck_prpr", 0))
            except:
                price = 0

            if ticker and name and price >= 10000 and not is_noise_name(name):
                pool.append((ticker, name))
            if len(pool) >= 20: 
                break
        return pool if pool else BACKUP_MASTER_POOL

    def get_realtime_price(self, ticker, token, default_name=""):
        if not token:
            return None
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        
        # 🎯 [핵심 수정] 시세 수신 거절을 방지하기 위해 오피셜 필수 규격 완전 결합
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}", 
            "appkey": self.app_key, 
            "appsecret": self.app_secret, 
            "tr_id": "FHPST01010000", # 국내주식 현재가 TR 고정
            "custtype": "P"            # 개인 고객 고정
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        
        resp = self.session.get(url, headers=headers, params=params, timeout=3.0)
        
        # 만약 한투 서버가 시세 패킷을 거절했다면 원인을 추출해 화면에 인쇄하기 위한 임시 딕셔너리 생성
        if not resp or resp.status_code != 200:
            msg = f"HTTP {resp.status_code}" if resp else "통신 타임아웃"
            return {"name": default_name, "Close": 0.0, "PrdyCtrt": 0.0, "Volume": 0, "is_restricted": False, "time": f"❌ 실패 ({msg})"}
            
        res = resp.json()
        out = res.get("output") if res.get("output") else res.get("output1")
        
        # 한투 내부 처리 에러코드(rt_cd) 검증
        if res.get("rt_cd") != "0" or not out:
            msg = res.get("msg1", "한투 거절")
            return {"name": default_name, "Close": 0.0, "PrdyCtrt": 0.0, "Volume": 0, "is_restricted": False, "time": f"❌ {msg[:10]}"}
            
        close_p = safe_float(out.get("stck_prpr", 0))
        stat_code = str(out.get("iscd_stat_cls_code", "00")).strip()
        name = out.get("hts_kor_isnm", "") if out.get("hts_kor_isnm") else default_name
        
        return {
            "name": name,
            "Close": close_p,
            "High": safe_float(out.get("stck_hgpr", 0)),
            "Low": safe_float(out.get("stck_lwpr", 0)),
            "Volume": safe_float(out.get("acml_vol", out.get("accl_tr_vol", 0))),
            "PrdyCtrt": safe_float(out.get("prdy_ctrt", 0.0)),
            "is_restricted": stat_code in RESTRICTED_STAT,
            "time": datetime.now().strftime("%H:%M:%S")
        }

# =====================================================================
# 🖥️ Streamlit UI 대시보드 렌더링 파트
# =====================================================================
if "engine_cache" not in st.session_state:
    st.session_state.engine_cache = {}
if "last_pool" not in st.session_state:
    st.session_state.last_pool = BACKUP_MASTER_POOL

st.title("🎯 AI 실시간 고안정성 주도주 스캐너 (10,000원↑)")

if st.button("🔄 즉시 마켓 시세 스캔 및 갱신", type="primary", use_container_width=True):
    with st.spinner("한투 오피셜 세션 가동 및 실시간 데이터 수합 중..."):
        api = KoreaInvestmentOfficialAPI(APP_KEY, APP_SECRET)
        token = api.get_fresh_access_token()
        if token:
            tickers = api.get_market_leading_tickers(token)
            st.session_state.last_pool = tickers
            for idx, (t, n) in enumerate(tickers[:20]):
                time.sleep(0.15) # 한투 초당 5건 요청 과부하 회피용 안전 시차 늘림
                data = api.get_realtime_price(t, token, default_name=n)
                if data:
                    st.session_state.engine_cache[t] = data
            st.rerun()

# 화면 출력 테이블 렌더링
display_list = []
for t, n in st.session_state.last_pool[:20]:
    c = st.session_state.engine_cache.get(t, {})
    close_val = c.get("Close", 0.0)
    
    display_list.append({
        "종목코드": t, 
        "종목명": c.get("name", n),
        "현재가": f"{int(close_val):,}원" if close_val > 0 else c.get("time", "대기중"),
        "등락률": f"{c.get('PrdyCtrt', 0.0):+.2f}%" if close_val > 0 else "0.00%",
        "거래량": f"{int(c['Volume']):,}주" if c.get("Volume") else "-",
        "유의종목여부": "⚠️ 투자유의" if c.get("is_restricted") else "🟢 정상",
        "동기화상태": c.get("time", "-")
    })

st.dataframe(pd.DataFrame(display_list), use_container_width=True, hide_index=True, height=750)
