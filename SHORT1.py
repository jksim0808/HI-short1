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

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "hantu_token" not in st.session_state: st.session_state.hantu_token = None
if "token_expires_at" not in st.session_state: st.session_state.token_expires_at = None
if "debug_msg" not in st.session_state: st.session_state.debug_msg = "🔌 통신 대기 중..."

# =====================================================================
# 🖥️ 상단 고정: 프로그램 특징 / 종목 분류 방법 / 실전 사용법
# =====================================================================
st.title("🎯 AI 실시간 주도주 검색기 (실전 단타 전용 Pro)")

# 현재 시스템의 통신 상태를 상단에 직관적으로 표시
st.info(f"📡 **시스템 실시간 통신 진단 리포트:** {st.session_state.debug_msg}")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### ⚡ 프로그램 3대 핵심 특징")
    st.markdown(
        """
        1. **리얼타임 시장 동적 연동**: 고정된 종목이 아니라, 버튼을 누르는 순간 한국투자증권 서버에서 당일 거래대금이 가장 많이 터진 최상위 순서대로 종목을 소싱합니다.
        2. **초저가 잡주 및 금융노이즈 차단**: 단타 매매 시 리스크가 큰 동전주를 막기 위해 현재가 2,000원 이상 종목만 선별하며, ETF/스팩/인버스/레버리지 등은 자동으로 100% 걸러냅니다.
        3. **연타 방지 보안 캐시**: 장중 새로고침 버튼을 연속으로 난타해도 이미 발급된 안전 토큰을 메모리에서 재사용하므로 한투 서버로부터의 IP 차단 및 토큰 에러를 원천 봉쇄합니다.
        """
    )

with col2:
    st.markdown("### 📊 AI 단타 종목 분류 기준")
    st.markdown(
        """
        * **🔥 A급 (최우선 대장주)**: 등락률 **+10% 이상 ~ +25% 미만**인 정상 종목입니다. 당일 돈이 위로 강력하게 붙는 진짜 주도주이므로 돌파/눌림목 매매의 핵심 타깃입니다.
        * **⚡ B급 (과열/추격금지)**: 등락률 **+25% 이상**으로 상한가 직전인 종목입니다. 단기 고점 리스크가 매우 크므로 절대 추격 매수를 금지합니다.
        * **⚡ B급 (후발/방망이짧게)**: 등락률 **+1% 이상 ~ +10% 미만** 종목입니다. 수급은 들어왔으나 탄력이 약하므로 아주 짧은 스캘핑 위주로만 접근합니다.
        * **❌ 매매대상 완전 제외**: 등락률 **+1% 미만(보합/하락)**이거나 한투 시스템상 **투자유의/관리종목** 마크가 붙은 쓰레기 종목은 대표님의 원금을 지키기 위해 표에서 자동 소멸시킵니다.
        """
    )

with col3:
    st.markdown("### 📈 아침 9시 장 개시 후 실전 변화")
    st.markdown(
        """
        1. **과거 유령 종목 자동 소멸**: 장 시작 후 전일 거래대금이 죽어버린 종목들은 순위권 밖으로 즉시 밀려나 화면에서 완벽하게 사라집니다.
        2. **새로운 실전 대장주 실시간 갱신**: 아침 9시 정각부터 실시간 거래대금이 수백억씩 폭발하며 위로 강력하게 쏘아 올리는 당일 최신 주도테마주들이 1위부터 순서대로 뷰어에 정확히 꽂힙니다.
        3. **하락장 리스크 자동 차단**: 만약 당일 시장 분위기가 험악하여 거래대금 상위권 종목들이 죄다 마이너스 하락세를 타면, 표에는 종목이 단 1개도 안 나오고 **"대기자금을 보존하십시오"**라는 경고창만 떠서 대표님의 투자 원금을 강제로 수호합니다.
        """
    )

st.write("---") 

# =====================================================================
# 🏹 오피셜 순위 출력 한투 API 커넥터 엔진 (디버깅 진단 강화)
# =====================================================================
class HantuSyncEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        # API Key 입력 자체 검증
        if not APP_KEY or not APP_SECRET:
            st.session_state.debug_msg = "❌ 에러: Streamlit Secrets에 한투 APP_KEY 또는 APP_SECRET이 비어있거나 설정되지 않았습니다."
            return None

        now = datetime.now(tz=timezone.utc)
        if st.session_state.hantu_token and st.session_state.token_expires_at and st.session_state.token_expires_at > now:
            return st.session_state.hantu_token

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=5.0)
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    st.session_state.hantu_token = token
                    st.session_state.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=5)
                    return token
                else:
                    st.session_state.debug_msg = f"❌ 에러: 한투 응답 데이터에 토큰이 없음 -> {r.text}"
            else:
                st.session_state.debug_msg = f"❌ 에러: 토큰 발급 HTTP 실패 ({r.status_code}) -> APP_KEY/SECRET을 재확인하세요."
        except Exception as e:
            st.session_state.debug_msg = f"❌ 에러: 한투 인증 서버와 연결 불통 (네트워크/방화벽 확인) -> {str(e)}"
        return None

    def fetch_market_pool(self, token):
        pool = []
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, 
            "tr_id": "FHPST01710000",
            "custtype": "P"
        }
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", 
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", 
            "FID_DIV_CLS_CODE": "0", 
            "FID_SORT_CLS_CODE": "3" # 거래대금순 정렬
        }
        try:
            r = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                # API 수신 자체 성공 여부 체크
                if res_data.get("rt_cd") != "0":
                    st.session_state.debug_msg = f"❌ 한투 API 에러 반환: {res_data.get('msg1')}"
                    return pool
                    
                if not output:
                    st.session_state.debug_msg = "⚠️ 한투에서 거래대금 순위 원본 데이터를 비어있게 반환했습니다. (장 개시 전이거나 서버 지연)"
                
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    
                    if ticker.isdigit() and name and name != "None" and price >= 2000:
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF", "SOL", "ACE", "HANARO"]): 
                            continue
                        if name.endswith("우") or any(name.endswith(f"우{suffix}") for suffix in ["B", "C", " 우선주", "1", "2", "3"]):
                            continue
                        pool.append((ticker, name))
            else:
                st.session_state.debug_msg = f"❌ 에러: 순위 데이터 호출 HTTP 실패 ({r.status_code})"
        except Exception as e:
            st.session_state.debug_msg = f"❌ 에러: 순위 데이터 통신 실패 -> {str(e)}"
        return pool

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
        return None

# =====================================================================
# 🖥️ 하단 데이터 제어 및 렌더링 파트
# =====================================================================
# 🛠️ [세션 초기화 버튼 추가] 통신이 완전히 꼬였을 때를 위한 강력한 초기화 수단
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 시장 실시간 주도주 새로 불러오기", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 토큰/세션 강제 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.engine_cache = {}
    st.session_state.last_pool = []
    st.session_state.debug_msg = "♻️ 토큰 캐시가 강제 삭제되었습니다. 다시 '새로 불러오기'를 눌러주세요."
    st.rerun()

if btn_fetch:
    if "token_error" in st.session_state: del st.session_state["token_error"]
    st.session_state.engine_cache = {}
    st.session_state.last_pool = []
    
    with st.spinner("현재 마켓 수급 원본을 분석하여 실시간 단타 대상주 선별 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.session_state["token_error"] = "토큰 발급 실패 (상단 통신 진단 리포트를 확인하세요)"
        else:
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            
            if dynamic_pool:
                st.session_state.debug_msg = f"🟢 통신 성공: 총 {len(dynamic_pool)}개의 기초 종목 풀을 확보하여 실시간 가격 연산 중..."
                for idx, (t, n) in enumerate(dynamic_pool):
                    res = engine.fetch_single_price(token, t, n)
                    if res:
                        st.session_state.engine_cache[t] = res
                    time.sleep(0.12) # 모의투자/실전 API 초당 제한 회피용 안정 버퍼
            else:
                if "❌" not in st.session_state.debug_msg:
                    st.session_state.debug_msg = "⚠️ 서버 통신은 성공했으나 필터링 조건에 맞는 종목이 수집되지 않았습니다."
            st.rerun()

if "token_error" in st.session_state:
    st.error(f"❌ {st.session_state['token_error']}")

# 데이터 취합 및 실시간 등급 연산부
display_list = []

if st.session_state.last_pool:
    for t, n in st.session_state.last_pool:
        c = st.session_state.engine_cache.get(t)
        if not c: continue
        
        price_val = c.get("price", -1)
        ctrt_val = c.get("ctrt", 0.0)
        stat_val = c.get("stat", "00")
        
        is_restricted = stat_val in ["51", "52", "53", "54", "58", "59"]
        
        if price_val <= 0 or is_restricted or ctrt_val < 1.0:
            continue
            
        if ctrt_val >= 25.0:
            rank_grade = "⚡ B급 (과열/추격금지)"
        elif ctrt_val >= 10.0 and ctrt_val < 25.0:
            rank_grade = "🔥 A급 (최우선 대장주)"
        else:
            rank_grade = "⚡ B급 (후발/방망이짧게)"

        display_list.append({
            "종목코드": t,
            "종목명": c.get("name", n),
            "AI 매매등급": rank_grade,
            "현재가": f"{int(price_val):,}원",
            "등락률": f"{ctrt_val:+.2f}%",
            "거래량": f"{int(c['volume']):,}주",
            "상태": "🟢 정상",
            "수집시각": c.get("time", "-")
        })

df_final = pd.DataFrame(display_list)
if not df_final.empty:
    df_final.insert(0, "시장투자순위", [f"{i+1}위" for i in range(len(df_final))])
    st.dataframe(df_final, use_container_width=True, hide_index=True, height=650)
else:
    st.info("📊 현재 당일 주도주 조건(+1% 이상 상승 우량주)에 부합하는 매매 대상 종목이 없습니다. 무리한 진입을 피하고 대기자금을 보존하십시오.")
