import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="주도주 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("012330", "현대모비스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = BACKUP_MASTER_POOL

# =====================================================================
# 🏹 무결점 동기식 한투 API 커넥터 엔진 (requests Session 기반)
# =====================================================================
class HantuSyncEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=3.0)
            return r.json().get("access_token")
        except: return None

    def fetch_market_pool(self, token):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"
        }
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=4.0)
            if r.status_code == 200:
                output = r.json().get("output", [])
                pool = []
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    
                    if ticker.isdigit() and name and name != "None" and price >= 10000:
                        if any(k in name for k in ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER"]): continue
                        pool.append((ticker, name))
                return pool if pool else BACKUP_MASTER_POOL
        except: pass
        return BACKUP_MASTER_POOL

    def fetch_single_price(self, token, ticker, name):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=3.0)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output") if res_json.get("output") else res_json.get("output1")
                if res_json.get("rt_cd") == "0" and out:
                    return {
                        "ticker": ticker, "name": name,
                        "price": float(out.get("stck_prpr", 0)),
                        "ctrt": float(out.get("prdy_ctrt", 0.0)),
                        "volume": float(out.get("acml_vol", out.get("accl_tr_vol", 0))),
                        "stat": str(out.get("iscd_stat_cls_code", "00")).strip(),
                        "time": datetime.now().strftime("%H:%M:%S")
                    }
        except: pass

        # 🎯 [메모리 복원 시스템] 통신이 튀더라도 기존 성공 데이터를 복원해 '대기중'이나 '누락'을 화면에서 지워버립니다.
        old = st.session_state.engine_cache.get(ticker, {})
        return {
            "ticker": ticker, "name": name,
            "price": old.get("price", -1),
            "ctrt": old.get("ctrt", 0.0),
            "volume": old.get("volume", 0),
            "stat": old.get("stat", "00"),
            "time": old.get("time", "❌ 수신대기")
        }

# =====================================================================
# 🖥️ UI 대시보드 및 동기 처리 제어 파트
# =====================================================================
st.title("🎯 AI 실시간 고안정성 주도주 스캐너 (10,000원↑)")

if st.button("🔄 즉시 마켓 시세 스캔 및 갱신", type="primary", use_container_width=True):
    if "token_error" in st.session_state: del st.session_state["token_error"]
    
    with st.spinner("한투 보안 규격을 준수하여 20개 주도주 정밀 스캔 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.session_state["token_error"] = "토큰 발급 실패 (비밀키 권한 재점검 요망)"
        else:
            # 1. 수급 주도주 20선 갱신
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            
            # 2. 🎯 칼같은 0.12초 동기식 타임 슬롯 분사 (한투 초당 제한 TPS 100% 우회 정공법)
            for idx, (t, n) in enumerate(dynamic_pool[:20]):
                res = engine.fetch_single_price(token, t, n)
                st.session_state.engine_cache[t] = res
                time.sleep(0.12)
                
            st.rerun()

if "token_error" in st.session_state:
    st.error(f"❌ 가동 실패: {st.session_state['token_error']}")

# 데이터 취합부 생성
display_list = []
for t, n in st.session_state.last_pool[:20]:
    c = st.session_state.engine_cache.get(t, {})
    price_val = c.get("price", -1)
    
    if price_val > 0:
        current_price_str = f"{int(price_val):,}원"
        ctrt_str = f"{c.get('ctrt', 0.0):+.2f}%"
        vol_str = f"{int(c['volume']):,}주"
        time_str = c.get("time", "-")
    else:
        current_price_str = "대기중 (위 갱신 버튼을 눌러주세요)"
        ctrt_str = "0.00%"
        vol_str = "-"
        time_str = c.get("time", "-")

    display_list.append({
        "종목코드": t,
        "종목명": c.get("name", n),
        "현재가": current_price_str,
        "등락률": ctrt_str,
        "거래량": vol_str,
        "상태": "⚠️ 유의종목" if c.get("stat") in ["51", "52", "53", "54", "58", "59"] else "🟢 정상",
        "갱신시각": time_str
    })

st.dataframe(pd.DataFrame(display_list), use_container_width=True, hide_index=True, height=750)
