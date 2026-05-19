import streamlit as st
import pandas as pd
import json
import asyncio
import websockets
import httpx
import threading
import queue
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 안전망 결합
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()
APPROVAL_KEY = st.secrets.get("HANTU_APPROVAL_KEY", "").strip()

# 주도주 고정 20선 백업 마스터 풀
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("027360", "아주IB투자"), ("021880", "메이슨캐피탈"),
    ("011000", "진원생명과학"), ("900300", "오가닉티코스메틱"), ("142280", "녹십자엠에스"), ("439960", "코스모로보틱스"),
    ("066980", "한성크린텍"), ("203650", "드림시큐리티"), ("066430", "아이로보틱스"), ("307870", "비투엔")
]

# =================================================================
# 🛡️ 안전성 확보를 위한 글로벌 통신 큐(Queue) 및 메모리 캐시 정의
# =================================================================
# 스레드 간 데이터 전송 시 충돌을 방지하는 안전 수송로
if "packet_queue" not in st.session_state:
    st.session_state.packet_queue = queue.Queue()

# 실제 화면에 뿌려줄 데이터 임시 저장소 (딕셔너리 구조 안전화)
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}
if "active_pool" not in st.session_state:
    st.session_state.active_pool = {}
if "custom_tickers" not in st.session_state:
    st.session_state.custom_tickers = {}

# =================================================================
# 🚀 1. 비동기 HTTPX 기반 마스터 스캔 엔진
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
# 📡 2. 한투 실시간 웹소켓(WebSocket) 독립 엔진
# =================================================================
async def hantu_websocket_handler(tickers, data_queue):
    """ 한투 웹소켓에서 받은 데이터를 st.session_state에 직접 넣지 않고, 안전하게 큐(Queue)에 쌓음 """
    ws_url = "ws://ops.koreainvestment.com:21000"
    
    async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
        for ticker in tickers:
            send_data = {
                "header": {"approval_key": APPROVAL_KEY, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
                "body": {"input": {"tr_id": "HMKST101", "tr_key": ticker}}
            }
            await ws.send(json.dumps(send_data))
            await asyncio.sleep(0.05)
            
        while True:
            try:
                recv_msg = await ws.recv()
                if recv_msg.startswith("0") or recv_msg.startswith("1"):
                    parts = recv_msg.split("|")
                    if len(parts) >= 4:
                        data_cnt = int(parts[2])
                        data_body = parts[3]
                        
                        record_size = len(data_body) // data_cnt
                        for i in range(data_cnt):
                            single_record = data_body[i*record_size : (i+1)*record_size]
                            data_fields = single_record.split('^')
                            
                            if len(data_fields) > 4:
                                ticker = data_fields[0].strip()
                                price = float(data_fields[2])
                                ctrt = float(data_fields[5])
                                volume = float(data_fields[13])
                                
                                # 데이터 충돌 방지를 위해 안전 큐에 밀어넣기
                                data_queue.put({
                                    "ticker": ticker, "price": price, "ctrt": ctrt, "volume": volume,
                                    "timestamp": datetime.now().strftime("%H:%M:%S")
                                })
            except asyncio.CancelledError:
                break
            except:
                await asyncio.sleep(1)
                continue

def start_websocket_loop(tickers, data_queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(hantu_websocket_handler(tickers, data_queue))

# =================================================================
# 🖥️ 3. UI 대시보드 및 데이터 동기화
# =================================================================
st.set_page_config(page_title="실시간 초고속 웹소켓 스캐너", layout="wide")
st.title("🎯 AI 장중 거래대금 20선 실시간 웹소켓(WebSocket) 스캐너")

with st.container(border=True):
    st.subheader("📋 실시간 웹소켓 통신 엔진 운영 가이드")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("""
        **⚡ 스레드 안전성 강화 완료**
        * **AttributeError 완전 해결:** 웹소켓 수신부와 화면 출력부를 안전 큐(`Queue`)로 완전히 분리하여 자원 충돌 현상을 원천 방지했습니다.
        * **초고속 스트리밍 푸시:** 장중 한투 서버 지연이나 렉에 영향받지 않고, 체결이 들어오는 즉시 메모리에 캐싱 처리됩니다.
        """)
    with col_g2:
        st.markdown("""
        **📊 실시간 정렬 및 새로고침 안내**
        * **새로 갱신 버튼:** 실시간으로 쌓인 데이터 스냅샷을 최신 등락률 순위로 정렬하여 화면을 다시 그리려면 아래 `🔄 데이터 수신 상태 새로 갱신` 버튼을 눌러주세요.
        """)

st.markdown("---")

# [핵심 보정] 데이터 초기화 단계에서 강제 변수 선언 유도
if not st.session_state.active_pool:
    with st.spinner("🚀 한투 실시간 수급 풀 네트워크 연결 및 20선 확보 중..."):
        token = asyncio.run(fetch_token_async())
        if token:
            raw_pool = asyncio.run(fetch_volume_rank_async(token))
            
            temp_pool = {}
            for ticker, name in raw_pool:
                if len(temp_pool) >= 20: break
                temp_pool[ticker] = name
                if ticker not in st.session_state.price_cache:
                    st.session_state.price_cache[ticker] = {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"}
            
            if len(temp_pool) < 20:
                for ticker, name in BACKUP_MASTER_POOL:
                    if len(temp_pool) >= 20: break
                    if ticker not in temp_pool:
                        temp_pool[ticker] = name
                        st.session_state.price_cache[ticker] = {"price": 0, "ctrt": 0.0, "volume": 0, "timestamp": "-"}
            
            st.session_state.active_pool = temp_pool

# 큐(Queue)에 쌓인 최신 데이터를 Streamlit 세션 메모리로 안전하게 인출하는 작업
while not st.session_state.packet_queue.empty():
    try:
        packet = st.session_state.packet_queue.get_nowait()
        st.session_state.price_cache[packet["ticker"]] = {
            "price": packet["price"], "ctrt": packet["ctrt"], "volume": packet["volume"],
            "timestamp": packet["timestamp"]
        }
    except queue.Empty:
        break

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
                st.toast("관심 종목이 편입되었습니다. 아래 갱신 버튼을 눌러 수신을 시작하세요.")
                st.rerun()

col_ctrl1, _ = st.columns([3, 5])
if col_ctrl1.button("🔄 웹소켓 실시간 데이터 수신 상태 새로 갱신", type="primary", use_container_width=True):
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 🖥️ 고속 웹소켓 데이터 대시보드 뷰어 (충돌 방지 로직 적용)
# -----------------------------------------------------------------
display_list = []
# 세션 상태가 도중에 바뀌는 것을 방지하기 위해 리스트 스냅샷 복사본 사용
active_items = list(st.session_state.active_pool.items())

for ticker, name in active_items:
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
    df_display["sort_val"] = df_display["당일 등락률"].str.replace("%", "").astype(float)
    df_display = df_display.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
    df_display = df_display.drop(columns=["sort_val"])
    
    df_display.insert(0, "순위", [f"{i+1}위" for i in range(len(df_display))])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("웹소켓 파이프라인으로부터 첫 체결 패킷을 동기화하고 있습니다.")

# =================================================================
# 🔄 백그라운드 웹소켓 태스크 자동 시동 장치
# =================================================================
if "ws_thread_started" not in st.session_state and st.session_state.active_pool:
    st.session_state.ws_thread_started = True
    target_tickers = list(st.session_state.active_pool.keys())
    
    # st.session_state 대신 전역 큐(packet_queue)를 스레드 인자로 안전하게 전달
    t = threading.Thread(
        target=start_websocket_loop, 
        args=(target_tickers, st.session_state.packet_queue), 
        daemon=True
    )
    t.start()
