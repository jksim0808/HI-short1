import streamlit as st
import pandas as pd
import asyncio
import httpx
from datetime import datetime

# =================================================================
# ⚙️ [최우선 배치] Streamlit 페이지 설정
# =================================================================
st.set_page_config(page_title="주도주 스캐너", layout="wide")

# =================================================================
# 🔑 환경설정 및 비밀키 결합
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# 10,000원 이상 우량주 백업 리스트
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("439960", "코스모로보틱스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

if "price_cache" not in st.session_state: st.session_state.price_cache = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {t: n for t, n in BACKUP_MASTER_POOL}

# =================================================================
# 🚀 데이터 수집 엔진 (10,000원 필터링 핵심)
# =================================================================
async def get_token(client):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    resp = await client.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET})
    return resp.json().get("access_token")

async def fetch_pool(client, token):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {"authorization": f"Bearer {token}", "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000"}
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_SORT_CLS_CODE": "1"}
    try:
        resp = await client.get(url, headers=headers, params=params, timeout=4.0)
        output = resp.json().get("output", [])
        pool = {}
        for item in output:
            price = float(item.get("stck_prpr", 0))
            name = item.get("hts_kor_isnm", "")
            if price >= 10000 and not any(k in name for k in ["우", "스팩", "리츠", "인버스", "KODEX", "TIGER"]):
                pool[str(item.get("mksc_shrn_iscd", ""))] = name
            if len(pool) >= 20: break
        return pool if pool else {t: n for t, n in BACKUP_MASTER_POOL}
    except: return {t: n for t, n in BACKUP_MASTER_POOL}

async def fetch_price(client, token, ticker, name, delay):
    await asyncio.sleep(delay)
    headers = {"authorization": f"Bearer {token}", "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000"}
    try:
        resp = await client.get("https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price", 
                                headers=headers, params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}, timeout=2.0)
        out = resp.json().get("output", {})
        return {"ticker": ticker, "name": name, "price": float(out.get("stck_prpr", 0)), 
                "ctrt": float(out.get("prdy_ctrt", 0.0)), "vol": float(out.get("acml_vol", 0)), "time": datetime.now().strftime("%H:%M:%S")}
    except: return None

async def run_scanner():
    async with httpx.AsyncClient() as client:
        token = await get_token(client)
        if not token: return
        st.session_state.active_pool = await fetch_pool(client, token)
        tasks = [fetch_price(client, token, t, n, i*0.1) for i, (t, n) in enumerate(st.session_state.active_pool.items())]
        results = await asyncio.gather(*tasks)
        for res in results:
            if res: st.session_state.price_cache[res["ticker"]] = res

# =================================================================
# 🖥️ 화면 출력부 (에러 유발 요스 st.columns 완전 배제)
# =================================================================
st.title("🎯 10,000원 이상 우량 주도주 실시간 스캐너")

# 🔄 갱신 버튼을 상단 전면에 크게 배치 (충돌 가능성 0%)
if st.button("🔄 실시간 시세 고속 동기화", type="primary", use_container_width=True):
    asyncio.run(run_scanner())
    st.rerun()

# 데이터 수합 및 정렬용 데이터 프레임 빌드
display_list = []
for ticker, name in st.session_state.active_pool.items():
    c = st.session_state.price_cache.get(ticker, {})
    display_list.append({
        "종목명": name,
        "현재가": f"{int(c.get('price', 0)):,}원" if c.get('price') else "데이터 대기중",
        "등락률": f"{c.get('ctrt', 0.0):+.2f}%",
        "거래량": f"{int(c.get('vol', 0)):,}주",
        "최근시각": c.get('time', '-')
    })

if display_list:
    df_display = pd.DataFrame(display_list)
    df_display["sort_val"] = df_display["등락률"].str.replace("%", "").astype(float)
    df_display = df_display.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
    df_display = df_display.drop(columns=["sort_val"])
    
    df_display.insert(0, "순위", [f"{i+1}위" for i in range(len(df_display))])
    
    # 상단 갱신 버튼 바로 밑에 대시보드 상태를 안정적으로 노출
    st.markdown(f"📊 **현재 상위 수급포착:** 10,000원 이상 {len(df_display)}개 종목 실시간 감시 중")
    st.markdown("---")
    
    # 데이터 표 시원하게 출력
    st.dataframe(df_display, use_container_width=True, hide_index=True, height=750)
else:
    st.info("데이터가 비어있습니다. 위 갱신 버튼을 눌러주세요.")
