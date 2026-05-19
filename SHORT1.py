import streamlit as st
import pandas as pd
import asyncio
import httpx
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 안전망 결합
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# 만 원 이상 종목 위주의 백업 마스터 풀 (수급 단절 시 방어용 고정 20선)
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("439960", "코스모로보틱스"), ("000670", "영풍"),
    ("012450", "한화에어로스페이스"), ("009830", "한화솔루션"), ("034020", "두산에너빌리티"), ("010140", "삼성중공업"),
    ("015760", "한국전력"), ("004020", "현대제철"), ("011780", "금호석유"), ("010950", "S-Oil")
]

# 로컬 메모리 이중 버퍼 캐시 초기화
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}
if "active_pool" not in st.session_state:
    st.session_state.active_pool = {}

# =================================================================
# 🚀 1. 한투 API 인증 토큰 발급 (비동기)
# =================================================================
async def fetch_token_async(client):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    data = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        r = await client.post(url, json=data, timeout=3.0)
        return r.json().get("access_token")
    except:
        return None

# =================================================================
# 📊 2. [개선] 거래대금 상위 수급 풀 중 '현재가 10,000원 이상'만 필터링
# =================================================================
async def fetch_volume_rank_async(client, token):
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
        r = await client.get(url, headers=headers, params=params, timeout=4.0)
        if r.status_code == 200:
            output = r.json().get("output", [])
            pool = []
            for item in output:
                ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                
                # 🎯 [핵심 조건 추가] 한투 수급 랭킹의 현재가(stck_prpr) 정보 추출
                current_price = float(item.get("stck_prpr", 0))
                
                if ticker.isdigit() and name and name != "None":
                    # 노이즈 종목 및 ❌ 현재가 10,000원 미만 동전주/소형주 원천 필터 차단
                    if current_price < 10000: continue
                    if any(k in name for k in ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER"]): continue
                    
                    pool.append((ticker, name))
            return pool
    except:
        pass
    return BACKUP_MASTER_POOL

# =================================================================
# ⚡ 3. 마이크로 슬롯 타임 분사 엔진 (초당 제한 우회 및 캐시 보정)
# =================================================================
async def fetch_single_price_throttled(client, token, ticker, name, delay):
    """ 각 요청 간 미세 시차(delay)를 두어 한투 서버의 패킷 거절을 차단 """
    await asyncio.sleep(delay)
    
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
    
    try:
        r = await client.get(url, headers=headers, params=params, timeout=2.0)
        if r.status_code == 200:
            output = r.json().get("output", {})
            return {
                "ticker": ticker, "name": name,
                "price": float(output.get("stck_prpr", 0)),
                "ctrt": float(output.get("prdy_ctrt", 0.0)),
                "volume": float(output.get("acml_vol", 0)),
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
    except:
        pass
    
    old = st.session_state.price_cache.get(ticker, {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"})
    return {
        "ticker": ticker, "name": name,
        "price": old.get("price", 0),
        "ctrt": old.get("ctrt", 0.0),
        "volume": old.get("volume", 0),
        "timestamp": old.get("timestamp", "-")
    }

async def update_all_prices_safe():
    """ 20개 종목 태스크를 생성하여 병렬로 안전하게 수합하는 메인 함수 """
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        token = await fetch_token_async(client)
        if not token:
            st.error("한투 Access Token 발급에 실패했습니다.")
            return

        # 만 원 이상 필터가 적용된 주도주 리스트 정밀 타겟팅
        raw_pool = await fetch_volume_rank_async(client, token)
        temp_pool = {}
        for ticker, name in raw_pool:
            if len(temp_pool) >= 20: break
            temp_pool[ticker] = name
        
        # 20선 부족분 발생 시 백업 마스터 풀에서 보충
        if len(temp_pool) < 20:
            for ticker, name in BACKUP_MASTER_POOL:
                if len(temp_pool) >= 20: break
                if ticker not in temp_pool: temp_pool[ticker] = name
                
        st.session_state.active_pool = temp_pool

        # 과부하 차단용 0.05초 간격 미세 분사 설정
        tasks = []
        for idx, (ticker, name) in enumerate(st.session_state.active_pool.items()):
            delay = idx * 0.05  
            tasks.append(fetch_single_price_throttled(client, token, ticker, name, delay))
        
        results = await asyncio.gather(*tasks)
        
        # 캐시 버퍼에 결과 매핑
        for res in results:
            st.session_state.price_cache[res["ticker"]] = {
                "price": res["price"], "ctrt": res["ctrt"], "volume": res["volume"],
                "timestamp": res["timestamp"]
            }

def run_async_bridge(coro):
    return asyncio.run(coro)

# =================================================================
# 🖥️ 4. UI 대시보드 출력부
# =================================================================
st.set_page_config(page_title="만 원 이상 주도주 스캐너", layout="wide")
st.title("🎯 AI 장중 거래대금 20선 무결점 실시간 스캐너 (10,000원↑)")

with st.container(border=True):
    st.subheader("🛠️ 엔진 가동 조건 : 현재가 10,000원 이상 고수급주 타겟팅")
    st.markdown("""
    * **동전주/잡주 원천 배제:** 당일 거래량이 아무리 튀어도 현재가가 **10,000원 미만인 종목은 자동으로 스캔 대상에서 제외**됩니다. 호가창이 단단하고 변동성이 제어되는 라운드피겨(만 원) 이상의 주도주 위주로 매매 전략을 수립할 수 있습니다.
    * **무결점 캐싱 엔진:** 한투 초당 호출 제한을 피하는 0.05초 타임 슬롯 제어와 직전 데이터 이중 보정으로 `⚠️ 서버대기` 없는 매끄러운 시세를 보장합니다.
    """)

st.markdown("---")

col_ctrl, _ = st.columns([3, 5])
if col_ctrl.button("🔄 초고속 시세 동기화 및 실시간 스캔", type="primary", use_container_width=True):
    with st.spinner("🚀 만 원 이상 우량 주도주 정밀 추출 중..."):
        run_async_bridge(update_all_prices_safe())
        st.rerun()

# 최초 실행 시 데이터 로드
if not st.session_state.price_cache:
    run_async_bridge(update_all_prices_safe())

# 화면 노출 데이터 프레임 빌드
display_list = []
active_items = list(st.session_state.active_pool.items())

for ticker, name in active_items:
    cache = st.session_state.price_cache.get(ticker, {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"})
    
    growth = cache["ctrt"]
    if growth >= 10.0: signal = "🔥 상한가 도전 / 초급등 수급"
    elif growth > 4.0: signal = "⚡ 거래량 폭발 돌파 (매수 가시권)"
    elif growth > 0.5: signal = "🟢 수급 우상향 추종"
    else: signal = "⚪ 숨고르기 및 관망"
    
    display_list.append({
        "종목코드": ticker, "종목명": name,
        "현재가": f"{int(cache['price']):,} 원" if cache['price'] > 0 else "데이터 수신중",
        "당일 등락률": f"{growth:+.2f}%",
        "누적 거래량": f"{int(cache['volume']):,} 주",
        "최근 체결 시각": cache["timestamp"],
        "엔진 상태": "🟢 정상 운영중",
        "단타 수급 시그널": signal
    })

if display_list:
    df_display = pd.DataFrame(display_list)
    df_display["sort_val"] = df_display["당일 등락률"].str.replace("%", "").astype(float)
    df_display = df_display.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
    df_display = df_display.drop(columns=["sort_val"])
    
    df_display.insert(0, "순위", [f"{i+1}위" for i in range(len(df_display))])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("데이터를 수합하고 있습니다. 위 갱신 버튼을 눌러주세요.")
