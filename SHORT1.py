import streamlit as st
import pandas as pd
import asyncio
import httpx
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 및 환경설정
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# 만 원 이상 우량 주도주 백업 풀
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("439960", "코스모로보틱스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

if "price_cache" not in st.session_state: st.session_state.price_cache = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}

# =================================================================
# 🚀 API 통신 엔진
# =================================================================
async def fetch_token_async(client):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    data = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        r = await client.post(url, json=data, timeout=3.0)
        return r.json().get("access_token")
    except: return None

async def fetch_volume_rank_async(client, token):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {"authorization": f"Bearer {token}", "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000"}
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_SORT_CLS_CODE": "1"}
    try:
        r = await client.get(url, headers=headers, params=params, timeout=4.0)
        if r.status_code == 200:
            pool = []
            for item in r.json().get("output", []):
                ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                name = str(item.get("hts_kor_isnm", "")).strip()
                if float(item.get("stck_prpr", 0)) >= 10000 and ticker.isdigit():
                    if any(k in name for k in ["우", "스팩", "리츠", "인버스"]): continue
                    pool.append((ticker, name))
                if len(pool) >= 20: break
            return pool
    except: pass
    return BACKUP_MASTER_POOL

async def fetch_single_price(client, token, ticker, name, delay):
    await asyncio.sleep(delay)
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {"authorization": f"Bearer {token}", "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000"}
    try:
        r = await client.get(url, headers=headers, params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}, timeout=2.0)
        if r.status_code == 200:
            out = r.json().get("output", {})
            return {"ticker": ticker, "name": name, "price": float(out.get("stck_prpr", 0)), "ctrt": float(out.get("prdy_ctrt", 0.0)), "volume": float(out.get("acml_vol", 0)), "time": datetime.now().strftime("%H:%M:%S")}
    except: pass
    return None

async def update_all_prices():
    async with httpx.AsyncClient() as client:
        token = await fetch_token_async(client)
        if not token: return
        
        # 종목풀 확보
        pool = await fetch_volume_rank_async(client, token)
        st.session_state.active_pool = {t: n for t, n in pool}
        
        # 0.1초 간격으로 서버 과부하 방지
        tasks = [fetch_single_price(client, token, t, n, i*0.1) for i, (t, n) in enumerate(pool)]
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if res: st.session_state.price_cache[res["ticker"]] = res

# =================================================================
# 🖥️ 화면 출력
# =================================================================
st.set_page_config(page_title="주도주 스캐너", layout="wide")
st.title("🎯 만 원 이상 우량 주도주 실시간 스캐너")

if not st.session_state.price_cache:
    with st.spinner("🚀 엔진 가동 중..."):
        asyncio.run(update_all_prices())

if st.button("🔄 실시간 시세 갱신"):
    asyncio.run(update_all_prices())
    st.rerun()

display_data = []
for ticker, name in st.session_state.active_pool.items():
    c = st.session_state.price_cache.get(ticker, {"price": 0, "ctrt": 0.0, "volume": 0, "time": "수신대기"})
    display_data.append({
        "순위": len(display_data)+1, "종목명": name, "현재가": f"{int(c['price']):,}원",
        "등락률": f"{c['ctrt']:+.2f}%", "거래량": f"{int(c['volume']):,}주", "최근시각": c['time']
    })

st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
