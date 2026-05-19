import streamlit as st
import pandas as pd
import asyncio
import httpx
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
    ("006400", "삼성SDI"), ("035720", "카카오"), ("439960", "코스모로보틱스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = BACKUP_MASTER_POOL

# =====================================================================
# ⚡ 초고속 비동기 데이터 통신 엔진 (httpx 기반 구조 전환)
# =====================================================================
async def fetch_token_async(client):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    try:
        r = await client.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=3.0)
        return r.json().get("access_token")
    except: return None

async def fetch_market_pool_async(client, token):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {
        "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
    }
    # 명세서 기준 가상 필터 파라미터 완전 매핑
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"
    }
    try:
        r = await client.get(url, headers=headers, params=params, timeout=4.0)
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

async def fetch_single_price_async(client, token, ticker, name, delay):
    await asyncio.sleep(delay)
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
    try:
        r = await client.get(url, headers=headers, params=params, timeout=3.0)
        if r.status_code == 200:
            res_json = r.json()
            out = res_json.get("output") if res_json.get("output") else res_json.get("output1")
            if out:
                return {
                    "ticker": ticker, "name": name,
                    "price": float(out.get("stck_prpr", 0)),
                    "ctrt": float(out.get("prdy_ctrt", 0.0)),
                    "volume": float(out.get("acml_vol", out.get("accl_tr_vol", 0))),
                    "stat": str(out.get("iscd_stat_cls_code", "00")).strip(),
                    "time": datetime.now().strftime("%H:%M:%S")
                }
    except: pass
    return {"ticker": ticker, "name": name, "price": -1, "ctrt": 0.0, "volume": 0, "stat": "00", "time": "❌ 통신 누락"}

async def run_async_pipeline():
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        token = await fetch_token_async(client)
        if not token:
            st.session_state["token_error"] = "토큰 발급 실패 (키 또는 계정 권한 문제)"
            return
            
        # 1. 상위 수급 주도주 풀 동적 확보
        dynamic_pool = await fetch_market_pool_async(client, token)
        st.session_state.last_pool = dynamic_pool
        
        # 2. 비동기 쪼개기 분사 방식을 통한 고속 시세 수집
        tasks = []
        for idx, (t, n) in enumerate(dynamic_pool[:20]):
            tasks.append(fetch_single_price_async(client, token, t, n, idx * 0.15))
            
        results = await asyncio.gather(*tasks)
        for res in results:
            st.session_state.engine_cache[res["ticker"]] = res

# =====================================================================
# 🖥️ 깔끔한 UI 단독 렌더링 파트 (Columns 레이아웃 배제)
# =====================================================================
st.title("🎯 AI 실시간 고안정성 주도주 스캐너 (10,000원↑)")

if st.button("🔄 즉시 마켓 시세 스캔 및 갱신", type="primary", use_container_width=True):
    if "token_error" in st.session_state: del st.session_state["token_error"]
    with st.spinner("한투 오피셜 커넥터 가동 중..."):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_scanner_pipeline())
        loop.close()
    st.rerun()

if "token_error" in st.session_state:
    st.error(f"❌ 가동 실패: {st.session_state['token_error']}")

# 데이터 취합부 생성
display_list = []
for t, n in st.session_state.last_pool[:20]:
    c = st.session_state.engine_cache.get(t, {})
    price_val = c.get("price", 0)
    
    # 에러 및 수신 상태 분기 정밀 렌더링
    if price_val == -1:
        current_price_str = "❌ 통신 오류"
    elif price_val > 0:
        current_price_str = f"{int(price_val):,}원"
    else:
        current_price_str = "대기중 (새로고침 요망)"

    display_list.append({
        "종목코드": t,
        "종목명": c.get("name", n),
        "현재가": current_price_str,
        "등락률": f"{c.get('ctrt', 0.0):+.2f}%" if price_val > 0 else "0.00%",
        "거래량": f"{int(c['volume']):,}주" if c.get("volume") else "-",
        "상태": "⚠️ 유의종목" if c.get("stat") in ["51", "52", "53", "54", "58", "59"] else "🟢 정상",
        "갱신시각": c.get("time", "-")
    })

# 시원하게 아래로 길게 떨어지는 고정형 테이블 출력
st.dataframe(pd.DataFrame(display_list), use_container_width=True, hide_index=True, height=750)
