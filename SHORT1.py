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
if "debug_msg" not in st.session_state: st.session_state.debug_msg = "🔌 장중 실시간 수급 체킹 준비 완료"

# =====================================================================
# 🖥️ 상단 가이드라인
# =====================================================================
st.title("🎯 AI 실시간 주도주 검색기 (실전 단타 전용 Pro)")
st.info(f"📡 **시스템 실시간 통신 진단 리포트:** {st.session_state.debug_msg}")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### ⚡ 프로그램 3대 핵심 특징")
    st.markdown("1. **진짜 돈 몰리는 종목 소싱**: 단순 거래량이 아닌 '당일 거래대금' 최상위 순서로 한국투자증권 서버에서 실시간 소싱합니다.\n2. **금융 노이즈 완벽 차단**: ETF, ETN, 인버스, 레버리지 및 '우선주'를 완벽히 걸러내어 순수 현물 주식만 표출합니다.\n3. **가격 문턱 완화**: 2,000원 이상 우량 테마주부터 대형주(삼성전자 등)까지 수급 유입 시 즉시 포착합니다.")
with col2:
    st.markdown("### 📊 AI 단타 종목 분류 기준")
    st.markdown("* **🔥 A급 (최우선 대장주)**: 등락률 **+10% ~ +25% 미만**. 당일 거래대금 터진 진짜 주도주 (주 타깃)\n* **⚡ B급 (과열/추격금지)**: 등락률 **+25% 이상**. 상한가 직전 고점 리스크 구간 (진입 자제)\n* **⚡ B급 (후발/방망이짧게)**: 등락률 **+1% ~ +10% 미만**. 수급 유입 초기 혹은 후발주 (짧은 단타용)\n* **❌ 매매대상 제외**: 등락률 **+1% 미만(보합/하락)**이거나 투자유의 종목은 원금 보존을 위해 자동 차단")
with col3:
    st.markdown("### 📈 실전 사용 매뉴얼")
    st.markdown("1. 아침 9시 장 개시 직후 수급이 들어올 때 버튼을 누르면 실시간 대장주들이 거래대금 순으로 정렬됩니다.\n2. 만약 장전이거나 시장 전체가 폭락하여 거래대금 상위주들이 죄다 마이너스라면 표는 깨끗하게 비워집니다.\n3. **'대기자금을 보존하십시오'** 메시지가 뜬다면 억지로 매매하지 말고 돈을 지키는 것이 이기는 길입니다.")

st.write("---") 

# =====================================================================
# 🏹 진짜 당일 거래대금 상위 순위 전용 API 커넥터 엔진
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
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=5.0)
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
        # 🛠️ [엔진 전면 교체] 잡주/인버스를 원천 차단하고 진짜 돈 쏠리는 '전일대비 거래대금 상위' API 사용
        url_amt = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/trade-amount-range"
        headers_amt = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, 
            "tr_id": "HHDFS76200100", # 거래대금 상위 전용 TR ID
            "custtype": "P"
        }
        params_amt = {
            "FID_COND_MRKT_DIV_CODE": "J", # 0: 전체, J: 주식 (ETF/인버스 자동 제외)
            "FID_COND_SCR_DIV_CODE": "20172",
            "FID_INPUT_ISCD": "0000" # 전체 시장
        }
        try:
            r = self.session.get(url_amt, headers=headers_amt, params=params_amt, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    
                    # 🛠️ 실시간 거래대금(단위: 백만) 및 현재가 파싱
                    try: amt_val = float(item.get("amt", 0)) * 1000000  # 원 단위 환산
                    except: amt_val = 0
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    try: ctrt = float(item.get("prdy_ctrt", 0.0))
                    except: ctrt = 0.0
                    
                    if ticker.isdigit() and name and name != "None":
                        # 1단계: 금융 노이즈(스팩, 리츠) 및 동전주(2,000원 미만) 차단
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                        if price < 2000: continue
                        
                        # 2단계: 단타용 최소 자금 및 거래 필터 (당일 거래대금 최소 50억 이상, 등락률 +1% 이상만 원천 소싱)
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
    btn_fetch = st.button("🔄 장중 실시간 주도주 새로 불러오기 (거래대금 상위 픽)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 토큰 세션 강제 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.last_pool = []
    st.session_state.debug_msg = "♻️ 세션 리셋 완료. 장 개시 후 '새로 불러오기'를 클릭하세요."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("한국투자증권 실시간 당일 최고 거래대금 주도주 분석 중..."):
        engine = HantuSyncEngine()
        token = engine.get_token()
        
        if not token:
            st.error("❌ 한투 API 토큰 발급에 실패했습니다. Secrets 설정을 확인하세요.")
        else:
            dynamic_pool = engine.fetch_market_pool(token)
            st.session_state.last_pool = dynamic_pool
            if dynamic_pool:
                st.session_state.debug_msg = f"🟢 수집 성공: 당일 거래대금 50억 이상, +1% 이상 주도주 {len(dynamic_pool)}개 포착!"
            else:
                st.session_state.debug_msg = "⚠️ 현재 시장에 거래대금 50억 이상 및 +1% 이상 상승 중인 단타 대상 종목이 없습니다."
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
            "당일 거래대금": f"{int(amt / 100000000):,}억 원",
            "실시간 상태": "🟢 수급 유입 완료"
        })

df_final = pd.DataFrame(display_list)
if not df_final.empty:
    df_final.insert(0, "시장돈 몰리는 순위", [f"{i+1}위" for i in range(len(df_final))])
    st.dataframe(df_final, use_container_width=True, hide_index=True, height=600)
else:
    st.info("📊 현재 장전 동시호가 기간이거나 시장에 돈이 실린 상승 우량주(+1% 이상, 거래대금 50억 이상)가 없습니다. 장 개시(09:00) 이후 새로고침을 진행하여 대기자금을 보존하십시오.")
