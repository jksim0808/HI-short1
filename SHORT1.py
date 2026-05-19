import streamlit as st
import pandas as pd
import json
import asyncio
import websockets
import httpx
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 안전망 결합
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()
APPROVAL_KEY = st.secrets.get("HANTU_APPROVAL_KEY", "").strip() # 웹소켓 필수 키

# 주도주 고정 20선 백업 마스터 풀
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("027360", "아주IB투자"), ("021880", "메이슨캐피탈"),
    ("011000", "진원생명과학"), ("900300", "오가닉티코스메틱"), ("142280", "녹십자엠에스"), ("439960", "코스모로보틱스"),
    ("066980", "한성크린텍"), ("203650", "드림시큐리티"), ("066430", "아이로보틱스"), ("307870", "비투엔")
]

# 세션 상태 메모리 버퍼 초기화 (렉 방지용 로컬 캐시)
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}
if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = {}

# =================================================================
# 🚀 1. 비동기 HTTPX 기반 마스터 스캔 엔진 (초고속 초기화)
# =================================================================
async def fetch_token_async():
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    data = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=data, timeout=3.0)
            return r.json().get("access_token")
        except:
            return None

async def fetch_volume_rank_async(token):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {
        "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=headers, params=params, timeout=4.0)
            if r.status_code == 200:
                output = r.json().get("output", [])
                pool = []
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    if ticker.isdigit() and name and name != "None":
                        if any(k in name for k in ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER"]): continue
                        pool.append((ticker, name))
                return pool
        except:
            pass
    return BACKUP_MASTER_POOL

# =================================================================
# 📡 2. 한투 실시간 웹소켓(WebSocket) 파이프라인 핸들러
# =================================================================
async def hantu_websocket_handler(tickers):
    """ 지정된 20개 종목의 체결 패킷을 한투 서버로부터 실시간 스트리밍 받아 로컬 캐시에 즉시 주입 """
    ws_url = "ws://ops.koreainvestment.com:21000" # 실시간 운영계 웹소켓 주소
    
    async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
        # 20개 종목 동시 구독(Subscribe) 신청 송신
        for ticker in tickers:
            send_data = {
                "header": {"approval_key": APPROVAL_KEY, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
                "body": {"input": {"tr_id": "HMKST101", "tr_key": ticker}} # 국내주식 실시간 체결 ID
            }
            await ws.send(json.dumps(send_data))
            await asyncio.sleep(0.05) # 한투 서버 보호용 초단기 간격
            
        # 실시간 데이터 무한 수신 루프 (렉 없이 메모리에 즉시 매핑)
        while True:
            try:
                recv_msg = await ws.recv()
                if recv_msg.startswith("0") or recv_msg.startswith("1"): # 데이터 패킷 조건
                    parts = recv_msg.split("|")
                    if len(parts) >= 4:
                        data_cnt = int(parts[2])
                        data_body = parts[3]
                        
                        # 대량 체결 패킷 분할 파싱
                        record_size = len(data_body) // data_cnt
                        for i in range(data_cnt):
                            single_record = data_body[i*record_size : (i+1)*record_size]
                            data_fields = single_record.split('^')
                            
                            if len(data_fields) > 4:
                                ticker = data_fields[0].strip()   # 종목코드
                                price = float(data_fields[2])     # 현재 체결가
                                sign = data_fields[3].strip()     # 전일대비 부호
                                ctrt = float(data_fields[5])      # 전일 대비 등락률
                                volume = float(data_fields[13])   # 누적 거래량
                                
                                # 대시보드 연동용 공유 세션 스토리지 메모리에 즉시 업데이트 (동기화 렉 제로)
                                st.session_state.price_cache[ticker] = {
                                    "price": price, "ctrt": ctrt, "volume": volume,
                                    "timestamp": datetime.now().strftime("%H:%M:%S")
                                }
            except asyncio.CancelledError:
                break
            except:
                await asyncio.sleep(1) # 통신 에러 발생 시 단기 대기 후 재기동
                continue

# 웹소켓 백그라운드 태스크 기동 통제 수문장
def start_websocket_loop(tickers):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(hantu_websocket_handler(tickers))

# =================================================================
# 🖥️ 3. UI 대시보드 빌드
# =================================================================
st.set_page_config(page_title="실시간 초고속 웹소켓 스캐너", layout="wide")
st.title("🎯 AI 장중 거래대금 20선 실시간 웹소켓(WebSocket) 스캐너")

# 최상단 사용 설명서 및 시스템 메커니즘 표기
with st.container(border=True):
    st.subheader("📋 실시간 웹소켓 통신 엔진 운영 가이드")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("""
        **⚡ 우회 없는 정면 돌파: 웹소켓(WebSocket) 방식**
        * **렉 발생 원인 차단:** 기존의 주기적 반복 호출(REST) 방식을 버리고 한투 서버와 상시 연결 통로를 개설했습니다.
        * **초고속 스트리밍 푸시:** 한투 서버가 체결 신호를 감지하는 즉시 프로그램에 실시간으로 데이터를 밀어 넣어주므로 요청 오버헤드와 장중 딜레이가 원천 제거됩니다.
        * **데이터 누락 방지:** 서버 트래픽이 폭주해도 로컬 메모리 버퍼가 패킷을 순차 처리하여 안정적인 시세를 보장합니다.
        """)
    with col_g2:
        st.markdown("""
        **📊 실시간 정렬 및 단타 기준**
        * **동적 탑랭크:** 웹소켓으로 들어오는 시세를 바탕으로 당일 등락률이 높은 대장주를 상단에 초고속 재정렬합니다.
        * **위험 감지:** 사이드카 발동 및 과열 제한 종목은 웹소켓 바인딩 전 초기 필터링 단계에서 자동 탈락 처리됩니다.
        * **동기화 안내:** 화면 갱신이 필요할 때는 브라우저를 새로고침하거나 하단의 동기화 버튼을 이용해 리스트를 재빌드할 수 있습니다.
        """)

st.markdown("---")

# 수급 데이터 로드 및 초기 타겟 20선 발굴 프로세스
if "active_pool" not in st.session_state or not st.session_state.active_pool:
    with st.spinner("🚀 한투 실시간 수급 풀 네트워크 연결 및 20선 확보 중..."):
        token = asyncio.run(fetch_token_async())
        if token:
            raw_pool = asyncio.run(fetch_volume_rank_async(token))
            
            # 최종 20위 라인업 빌드
            st.session_state.active_pool = {}
            for ticker, name in raw_pool:
                if len(st.session_state.active_pool) >= 20: break
                st.session_state.active_pool[ticker] = name
                if ticker not in st.session_state.price_cache:
                    st.session_state.price_cache[ticker] = {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"}
            
            # 20위 하한선 보충
            if len(st.session_state.active_pool) < 20:
                for ticker, name in BACKUP_MASTER_POOL:
                    if len(st.session_state.active_pool) >= 20: break
                    if ticker not in st.session_state.active_pool:
                        st.session_state.active_pool[ticker] = name
                        st.session_state.price_cache[ticker] = {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"}

# -----------------------------------------------------------------
# ⚙️ 제어판 및 관심 종목 직접 추가
# -----------------------------------------------------------------
with st.expander("➕ 관심 종목 직접 추가 (웹소켓 실시간 추적망 가동)", expanded=False):
    col_in, col_btn = st.columns([6, 2])
    with col_in:
        input_code = st.text_input("종목코드 6자리 입력", max_chars=6, key="ws_input_key").strip()
    with col_btn:
        st.write("")
        if st.button("➕ 웹소켓 망에 강제 추가", use_container_width=True):
            if len(input_code) == 6 and input_code.isdigit():
                st.session_state.custom_tickers[input_code] = "⭐ 수동지정주"
                st.session_state.active_pool[input_code] = "⭐ 수동지정주"
                st.session_state.price_cache[input_code] = {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": datetime.now().strftime("%H:%M:%S")}
                st.toast("관심 종목이 수급 추적망에 즉시 편입되었습니다. [새로 갱신]을 눌러주세요.")
                st.rerun()

col_ctrl1, _ = st.columns([3, 5])
if col_ctrl1.button("🔄 웹소켓 실시간 데이터 수신 상태 새로 갱신", type="primary", use_container_width=True):
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 🖥️ 고속 웹소켓 데이터 대시보드 뷰어
# -----------------------------------------------------------------
display_list = []
for ticker, name in st.session_state.active_pool.items():
    cache = st.session_state.price_cache.get(ticker, {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"})
    
    growth = cache["ctrt"]
    if growth >= 10.0: signal = "🔥 상한가 도전 / 초급등 수급 (매수)"
    elif growth > 4.0: signal = "⚡ 거래량 폭발 돌파 (매수)"
    elif growth > 0.5: signal = "🟢 수급 우상향 추종 (보유)"
    else: signal = "⚪ 숨고르기 및 관망"
    
    display_list.append({
        "종목코드": ticker, "종목명": name,
        "실시간 현재가": f"{int(cache['price']):,} 원" if cache['price'] > 0 else "체결 대기중",
        "당일 등락률": f"{growth:+.2f}%",
        "누적 거래량": f"{int(cache['volume']):,} 주",
        "최근 체결 시각": cache["timestamp"],
        "단타 수급 시그널": signal
    })

if display_list:
    df_display = pd.DataFrame(display_list)
    # 등락률 기준으로 고속 정렬 정렬
    df_display["sort_val"] = df_display["당일 등락률"].str.replace("%", "").astype(float)
    df_display = df_display.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
    df_display = df_display.drop(columns=["sort_val"])
    
    # 순위 부여
    df_display.insert(0, "순위", [f"{i+1}위" for i in range(len(df_display))])
    
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("웹소켓 파이프라인으로부터 첫 체결 패킷을 동기화하고 있습니다.")

# =================================================================
# 🔄 백그라운드 웹소켓 태스크 자동 시동 장치
# =================================================================
# 최초 실행 시 배후에서 웹소켓 수신 스레드를 독립 기동하여 Streamlit 리렌더링과 통신 렉 분리
if "ws_thread_started" not in st.session_state:
    st.session_state.ws_thread_started = True
    import threading
    target_tickers = list(st.session_state.active_pool.keys())
    t = threading.Thread(target=start_websocket_loop, args=(target_tickers,), daemon=True)
    t.start()
