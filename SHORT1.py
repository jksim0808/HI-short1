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

# =====================================================================
# 🖥️ 상단 고정: 프로그램 특징 / 종목 분류 방법 / 실전 사용법 (장중 변화 추가)
# =====================================================================
st.title("🎯 AI 실시간 주도주 검색기 (실전 단타 전용 Pro)")

# 3단 분할 레이아웃으로 가이드라인 시각화
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

st.write("---") # 시각적 구분을 위한 구분선

# =====================================================================
# 🏹 오피셜 순위 출력 한투 API 커넥터 엔진 (거래대금 순위 개조 버전)
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
            "FID_SORT_CLS_CODE": "3" # 거래대금순 정렬 적용
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
                    
                    # 🛠️ [조건 완화] 최소 가격 제한을 10,000원에서 2,000원으로 낮춤 (알짜 테마주 소싱 허용)
                    if ticker.isdigit() and name and name != "None" and price >= 2000:
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF", "SOL", "ACE", "HANARO"]): 
                            continue
                        
                        if name.endswith("우") or any(name.endswith(f"우{suffix}") for suffix in ["B", "C", " 우선주", "1", "2", "3"]):
                            continue
                            
                        pool.append((ticker, name))
        except: pass
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
if st.button("🔄 시장 실시간 주도주 새로 불러오기", type="primary", use_container_width=True):
    if "token_error" in st.session_state: del st.session_state["token_error"]
    
    st.session_state.engine_cache = {}
    st.session_state.last_pool = []
    
    with st.spinner("현재 마켓 수급 원본을 분석하여 실시간 단타 대상주 선별 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.session_state["token_error"] = "토큰 발급 실패 (잠시 후 다시 시도해 주세요)"
        else:
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            
            for idx, (t, n) in enumerate(dynamic_pool):
                res = engine.fetch_single_price(token, t, n)
                if res:
                    st.session_state.engine_cache[t] = res
                time.sleep(0.12) 
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
