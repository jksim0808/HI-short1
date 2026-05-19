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
if "debug_msg" not in st.session_state: st.session_state.debug_msg = "🔌 전일 및 장중 실시간 수급 체킹 준비 완료"

# =====================================================================
# 🖥️ 상단 가이드라인
# =====================================================================
st.title("🎯 AI 실시간 주도주 검색기 (실전 단타 전용 Pro)")
st.info(f"📡 **시스템 실시간 통신 진단 리포트:** {st.session_state.debug_msg}")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### ⚡ 프로그램 3대 핵심 특징")
    st.markdown("1. **전일 거래대금 기반 소싱**: 장 초반 데이터 공백을 막기 위해 24시간 내 돈이 가장 많이 터졌던 검증된 우량주 풀을 기본 소싱합니다.\n2. **장 초반 가변 필터**: 아침 9시 직후에는 거래대금 문턱을 낮춰 돈이 막 들어오는 대장주를 초동 포착합니다.\n3. **금융 노이즈 완벽 차단**: ETF/인버스/우선주/스팩은 100% 자동 필터링하여 순수 단타 현물만 취급합니다.")
with col2:
    st.markdown("### 📊 AI 단타 종목 분류 기준")
    st.markdown("* **🔥 A급 (최우선 대장주)**: 등락률 **+10% ~ +25% 미만**. 당일 쏠림이 증명된 진짜 대장주\n* **⚡ B급 (과열/추격금지)**: 등락률 **+25% 이상**. 상한가 직전 리스크 구간 (추격 금지)\n* **⚡ B급 (후발/방망이짧게)**: 등락률 **+1% ~ +10% 미만**. 수급 재유입 초기 및 후발주 (짧은 단타용)\n* **❌ 매매대상 제외**: 등락률 **+1% 미만(보합/하락)**은 장중 리스크 방지를 위해 자동 제외")
with col3:
    st.markdown("### 📈 아침 9시 장 개시 직후 팁")
    st.markdown("1. 장 시작 직후(09:00~09:15)에는 어제 거래대금이 컸던 종목 중 **오늘 아침 일찍 +1% 이상 갭을 띄우거나 빠르게 수급이 붙는 종목**이 상위에 랭크됩니다.\n2. 9시 15분 이후에는 당일 거래대금 50억 이상 조건이 자동으로 발동되어 진짜 당일 주도주만 걸러집니다.")

st.write("---") 

# =====================================================================
# 🏹 전일 거래대금 상위 기반 + 당일 실시간 추적 하이브리드 엔진
# =====================================================================
class HantuSyncEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        if not APP_KEY or not APP_SECRET:
            st.session_state.debug_msg = "❌ 에러: Streamlit Secrets 키 설정을 확인하세요."
            return None
        now = datetime.now(tz=timezone.utc)
        if st.session_state.hantu_token and st.session_state.token_expires_at and st.session_state.token_expires_at > now:
            return st.session_state.hantu_token
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    st.session_state.hantu_token = token
                    st.session_state.token_expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=5)
                    return token
        except: pass
        return None

    def fetch_market_pool(self, token):
        pool = []
        # 🛠️ [24시간 데이터 해결] '전일대비 거래대금 주도주 순위' API 활용 (어제 누적 상위 풀 확보)
        url_amt = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/trade-amount-range"
        headers_amt = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, 
            "tr_id": "HHDFS76200100", 
            "custtype": "P"
        }
        params_amt = {
            "FID_COND_MRKT_DIV_CODE": "J", # 주식만 소싱
            "FID_COND_SCR_DIV_CODE": "20172",
            "FID_INPUT_ISCD": "0000" 
        }
        try:
            r = self.session.get(url_amt, headers=headers_amt, params=params_amt, timeout=4.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                # 🛠️ 장 개시 이후 시간 체크 (가변 자금 필터용)
                now_time = datetime.now()
                is_market_start = (now_time.hour == 9 and now_time.minute <= 15)
                
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    
                    try: amt_val = float(item.get("amt", 0)) * 1000000  # 당일 거래대금 (원 단위)
                    except: amt_val = 0
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    try: ctrt = float(item.get("prdy_ctrt", 0.0))
                    except: ctrt = 0.0
                    
                    if ticker.isdigit() and name and name != "None":
                        # 1단계: 기본 노이즈 및 동전주 차단
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                        if price < 2000: continue
                        
                        # 2단계: 🛠️ 장 초반 사각지대 해제 알고리즘
                        if is_market_start:
                            # 아침 9시~9시 15분 사이에는 거래대금 1억 이상만 되어도 오늘 +1% 이상 치고 나가면 소싱
                            if amt_val < 100000000 or ctrt < 1.0: continue
                        else:
                            # 9시 15분 이후 본격적인 장중에는 거래대금 당일 50억 이상, 등락률 +1% 이상만 필터링
                            if amt_val < 5000000000 or ctrt < 1.0: continue
                        
                        pool.append((ticker, name, amt_val, price, ctrt))
        except Exception as e:
            st.session_state.debug_msg = f"❌ 통신 오류 발생: {str(e)}"
        return pool

# =====================================================================
# 🖥️ 데이터 제어 및 렌더링 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 주도주 새로 불러오기 (장초반 전일 수급 연동)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 토큰 세션 강제 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.last_pool = []
    st.session_state.debug_msg = "♻️ 세션 리셋 완료. 버튼을 눌러 다시 소싱하세요."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("최근 24시간 거래대금 검증 풀 기반 실시간 수급 동기화 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.error("❌ 한투 API 토큰 발급 실패")
        else:
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            if dynamic_pool:
                st.session_state.debug_msg = f"🟢 동기화 완료: 실시간 매매 대상 종목 총 {len(dynamic_pool)}개 포착!"
            else:
                st.session_state.debug_msg = "⚠️ 최근 수급 유입 종목 중 현재 +1% 이상 상승 중인 종목이 없습니다."
            st.rerun()

# 렌더링 파트
display_list = []
if st.session_state.last_pool:
    for t, n, amt, price, ctrt in st.session_state.last_pool:
        
        if ctrt >= 25.0:
            rank_grade = "⚡ B급 (과열/추격금지)"
        elif ctrt >= 10.0 and ctrt < 25.0:
            rank_grade = "🔥 A급 (최우선 대장주)"
        else:
            rank_grade = "⚡ B급 (후발/방망이짧게)"

        display_list.append({
            "종목코드": t,
            "종목명": n,
            "AI 매매등급": rank_grade,
            "현재가": f"{int(price):,}원",
            "등락률": f"{ctrt:+.2f}%",
            "당일 누적 거래대금": f"{int(amt / 100000000):,}억 원" if amt >= 100000000 else "1억 미만",
            "실시간 상태": "🟢 즉시 매매 가능"
        })

df_final = pd.DataFrame(display_list)
if not df_final.empty:
    df_final.insert(0, "수급 종합 순위", [f"{i+1}위" for i in range(len(df_final))])
    st.dataframe(df_final, use_container_width=True, hide_index=True, height=600)
else:
    st.info("📊 현재 등락률 조건(+1% 이상 상승 우량주)에 부합하는 종목이 없습니다. 장초반 움직임이 시작되면 새로고침을 진행해 주세요.")
