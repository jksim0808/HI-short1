import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="AI 실시간 주도주 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("012330", "현대모비스"), ("000670", "영풍")
]

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "hantu_token" not in st.session_state: st.session_state.hantu_token = None
if "token_expires_at" not in st.session_state: st.session_state.token_expires_at = None

# =====================================================================
# 🏹 하이브리드 수급 소싱 한투 API 커넥터 엔진
# =====================================================================
class HantuSyncEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        now = datetime.now(tz=timezone.utc)
        if st.session_state.hantu_token and st.session_state.token_expires_at and st.session_state.token_expires_at > now:
            return st.session_state.hantu_token

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                st.session_state.hantu_token = token
                st.session_state.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=5)
                return token
        except: pass
        return None

    def fetch_market_pool(self, token):
        pool = []
        unique_tickers = set()

        # 🎯 [하이브리드 1단계]: 거래대금 최상위 종목군 1차 조사
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "2" # 거래대금 순
        }
        try:
            r = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=4.0)
            if r.status_code == 200:
                output = r.json().get("output", [])
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    
                    if ticker.isdigit() and name and name != "None" and price >= 10000:
                        if any(k in name for k in ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF", "SOL", "ACE", "HANARO"]): continue
                        if ticker not in unique_tickers:
                            unique_tickers.add(ticker)
                            pool.append((ticker, name))
        except: pass

        # 🎯 [하이브리드 2단계]: 20개가 안 채워졌다면 전종목 등락률 상위 API 2차 결합 (ETF 자동 필터링 기능 내장)
        if len(pool) < 20:
            url_rank = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/fluctuation-rank"
            headers_rank = {
                "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
                "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01730000", "custtype": "P"
            }
            # 등락률 상위 순으로 가져오되 우량주 탐색 풀 극대화
            params_rank = {
                "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20173",
                "FID_INPUT_ISCD": "0000", "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "9999999", # 가격 필터 한투 서버에 직접 요청
                "FID_SORT_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "0",
                "FID_TRGT_EXCL_CLS_CODE": "0", "FID_VOL_CNT": "0"
            }
            try:
                r = self.session.get(url_rank, headers=headers_rank, params=params_rank, timeout=4.0)
                if r.status_code == 200:
                    output = r.json().get("output", [])
                    for item in output:
                        ticker = str(item.get("stck_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", "")).strip()
                        
                        if ticker.isdigit() and name and name != "None":
                            if any(k in name for k in ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF", "SOL", "ACE", "HANARO"]): continue
                            if ticker not in unique_tickers:
                                unique_tickers.add(ticker)
                                pool.append((ticker, name))
                        if len(pool) >= 20: break
            except: pass

        # 🎯 [최종 안전장치]: 주말, 폐장 직후 시스템 점검 등으로도 부족하면 백업 마스터 리스트로 20위 라인 강제 충전
        if len(pool) < 20:
            for b_ticker, b_name in BACKUP_MASTER_POOL:
                if len(pool) >= 20: break
                if b_ticker not in unique_tickers:
                    unique_tickers.add(b_ticker)
                    pool.append((b_ticker, b_name))
                    
        return pool[:20]

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
st.title("🎯 AI 실시간 시장 주도주 검색기 (하이브리드 20선 고속 소싱)")

if st.button("🔄 시장 거래대금 최상위 주도주 새로 불러오기", type="primary", use_container_width=True):
    if "token_error" in st.session_state: del st.session_state["token_error"]
    
    with st.spinner("거래대금 및 등락률 최상위 풀을 하이브리드로 정밀 융합 분석 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.session_state["token_error"] = "토큰 발급 실패 (잠시 후 다시 시도해 주세요)"
        else:
            # 🎯 3개만 잘리던 현상 완벽 조치, 무조건 만 원 이상 단타 대장주 20개 확보
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            
            for idx, (t, n) in enumerate(dynamic_pool):
                res = engine.fetch_single_price(token, t, n)
                st.session_state.engine_cache[t] = res
                time.sleep(0.12) 
            st.rerun()

if "token_error" in st.session_state:
    st.error(f"❌ {st.session_state['token_error']}")

# 데이터 취합 및 실시간 등급 연산부
display_list = []
target_pool = st.session_state.last_pool if st.session_state.last_pool else BACKUP_MASTER_POOL

for t, n in target_pool[:20]:
    c = st.session_state.engine_cache.get(t, {})
    price_val = c.get("price", -1)
    ctrt_val = c.get("ctrt", 0.0)
    stat_val = c.get("stat", "00")
    
    is_restricted = stat_val in ["51", "52", "53", "54", "58", "59"]
    
    if price_val <= 0:
        rank_grade = "⚙️ 분석대기"
    elif is_restricted:
        rank_grade = "❌ 매매제외 (위험주)"
    elif ctrt_val <= 0.0:
        rank_grade = "❌ 매매제외 (하락/보합)"
    elif ctrt_val >= 25.0:
        rank_grade = "⚡ B급 (과열/추격금지)"
    elif ctrt_val >= 10.0 and ctrt_val < 25.0:
        rank_grade = "🔥 A급 (최우선 대장주)"
    elif ctrt_val >= 5.0 and ctrt_val < 10.0:
        rank_grade = "⚡ B급 (후발/방망이짧게)"
    else:
        rank_grade = "📋 일반 관망"

    if price_val > 0:
        current_price_str = f"{int(price_val):,}원"
        ctrt_str = f"{ctrt_val:+.2f}%"
        vol_str = f"{int(c['volume']):,}주"
        time_str = c.get("time", "-")
    else:
        current_price_str = "대기중 (위 갱신 버튼을 클릭하여 새 종목을 불러오세요)"
        ctrt_str = "0.00%"
        vol_str = "-"
        time_str = c.get("time", "-")

    display_list.append({
        "종목코드": t,
        "종목명": c.get("name", n),
        "AI 매매등급": rank_grade,
        "현재가": current_price_str,
        "등락률": ctrt_str,
        "거래량": vol_str,
        "상태": "⚠️ 유의종목" if is_restricted else "🟢 정상",
        "수집시각": time_str
    })

df_final = pd.DataFrame(display_list)
if not df_final.empty:
    df_final.insert(0, "순위", [f"{i+1}위" for i in range(len(df_final))])

st.dataframe(df_final, use_container_width=True, hide_index=True, height=750)
