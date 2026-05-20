import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="오전 전종목 3단계 수급 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "hantu_token" not in st.session_state: st.session_state.hantu_token = None
if "token_expires_at" not in st.session_state: st.session_state.token_expires_at = None

# =====================================================================
# ⏳ 08:00 ~ 12:00 [한국 표준시(KST) 적용] 타임 제어 연산
# =====================================================================
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

# 한국 표준시 기준 상태 체크 (8시 ~ 12시 여부)
is_active_hour = (8 <= now_kst.hour < 12)
is_golden_hour = (9 <= now_kst.hour < 12) # 실제 장중
is_before_market = (now_kst.hour < 8)
is_after_market = (now_kst.hour >= 12)

# 카운트다운 및 타임 배너 제어
if is_golden_hour:
    remaining_hours = 11 - now_kst.hour
    remaining_min = 60 - now_kst.minute
    time_status_msg = f"🔥 [전체 수급 실시간 추적 중] 12:00 마감까지 **{remaining_hours}시간 {remaining_min}분** 남았습니다. (현재 서울: {current_time_str})"
    status_color = "inverse"
elif now_kst.hour == 8:
    time_status_msg = f"💤 [장 개시 전 세팅 상태] 한국 표준시 9시 정각부터 무제한 3단계 소싱이 활성화됩니다. (현재 서울: {current_time_str})"
    status_color = "info"
elif is_before_market:
    time_status_msg = f"💤 [운영 전] 본 프로그램은 한국 시간 오전 8시부터 낮 12시까지만 작동합니다. (현재 서울: {current_time_str})"
    status_color = "info"
else:
    time_status_msg = f"🛑 [오전 운영 마감] 낮 12시가 경과하여 오전 스캐너 운영이 마감되었습니다. (현재 서울: {current_time_str})"
    status_color = "error"

# =====================================================================
# 🖥️ 상단 고정 가이드라인
# =====================================================================
st.title("⚡ AI 오전 전종목 3단계 실시간 수급 스캐너 (Pro - KST)")

if status_color == "inverse":
    st.success(time_status_msg)
elif status_color == "info":
    st.info(time_status_msg)
else:
    st.error(time_status_msg)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 🏹 3단계 수급 등급 필터 안내")
    st.markdown(
        """
        * **🔥 A급 (수급 대장주)**: 등락률 **+10% 이상** 무조건 표출
        * **⚡ B급 (후발/단기수급)**: 등락률 **+1% 이상 ~ +10% 미만** 무조건 표출
        * **⚪ C급 (보합이하/하락)**: 등락률 **+1% 미만 전체** 무조건 표출
        """
    )
with col2:
    st.markdown("### 📊 수급 차단 제로(Zero) 원칙")
    st.markdown(
        """
        * **수급 제한 완전 해제**: 최소 거래대금 문턱(50억 등)을 통째로 파괴하여 돈이 조금이라도 몰린 종목은 100% 화면에 바로 바인딩됩니다.
        * **단타 전용 기본 노이즈 노출 제외**: 단타의 본질을 흐리는 불필요한 금융 노이즈(스팩/리츠/인버스/레버리지/우선주)만 깨끗하게 걸러냅니다.
        """
    )
with col3:
    st.markdown("### 🚨 장초반 실전 트레이딩 가이드")
    st.markdown(
        """
        1. **오픈 직후**: 리스트에 대량의 종목이 쏟아져 들어옵니다. 등락률과 거래대금 순위를 대조하며 대장주를 고르세요.
        2. **C급 종목 활용**: 당일 거래대금은 많이 터졌으나 주가가 마이너스인 녀석들은 C급에 배치되니, '낚시성 매수'를 거르는 용도로 씁니다.
        """
    )

st.write("---")

# =====================================================================
# 🏹 전종목 직송 출력형 거래대금 엔진
# =====================================================================
class HantuGoldenEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        if not APP_KEY or not APP_SECRET:
            return None
        now_tz = datetime.now(tz=timezone.utc)
        if st.session_state.hantu_token and st.session_state.token_expires_at and st.session_state.token_expires_at > now_tz:
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
        if not is_golden_hour:
            return pool

        url_amt = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/trade-amount-range"
        headers_amt = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "HHDFS76200100", "custtype": "P"
        }
        params_amt = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20172", "FID_INPUT_ISCD": "0000"
        }
        try:
            r = self.session.get(url_amt, headers=headers_amt, params=params_amt, timeout=4.0)
            if r.status_code == 200:
                output = r.json().get("output", [])
                
                for item in output:
                    ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    
                    try: amt_val = float(item.get("amt", 0)) * 1000000
                    except: amt_val = 0
                    try: price = float(item.get("stck_prpr", 0))
                    except: price = 0
                    try: ctrt = float(item.get("prdy_ctrt", 0.0))
                    except: ctrt = 0.0
                    
                    if ticker.isdigit() and name and name != "None":
                        # 단타에 전혀 무의미한 순수 파생상품/금융 노이즈류만 차단
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                        if price < 100: continue # 초저가 예외만 방지
                        
                        # 🛠️ [무제한 해제] 거래대금 제한 조건, 등락률 하한선 조건 완전히 삭제
                        pool.append((ticker, name, amt_val, price, ctrt))
        except: pass
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 수급 현황 전체 불러오기 (3단계 즉시 분류)", type="primary", use_container_width=True, disabled=not is_golden_hour)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.last_pool = []
    st.rerun()

if btn_fetch and is_golden_hour:
    st.session_state.last_pool = []
    with st.spinner("한국투자증권 실시간 수급 데이터 연산 엔진 가동 중..."):
        engine = HantuGoldenEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool(token)
            st.rerun()

# =====================================================================
# 📊 실시간 3단계 등급 바인딩 및 최종 렌더링
# =====================================================================
display_list = []

if st.session_state.last_pool:
    for t, n, amt, price, ctrt in st.session_state.last_pool:
        
        if is_after_market:
            rank_grade = "❌ 오전 장 마감"
            action_tag = "🔴 매매 종료"
        else:
            # 🛠️ 정밀한 3단계 조건 분류 바인딩
            if ctrt >= 10.0:
                rank_grade = "🔥 1단계: A급 (수급 대장주)"
                action_tag = "🟢 최우선 돌파/눌림 타깃"
            elif ctrt >= 1.0 and ctrt < 10.0:
                rank_grade = "⚡ 2단계: B급 (후발/단기수급)"
                action_tag = "🟢 방망이 짧게 스캘핑"
            else:
                rank_grade = "⚪ 3단계: C급 (보합이하/관망)"
                action_tag = "🟡 수급 유입만 확인/진입 자제"

        display_list.append({
            "종목코드": t,
            "종목명": n,
            "수급 등급 분류": rank_grade,
            "현재가": f"{int(price):,}원",
            "등락률": f"{ctrt:+.2f}%",
            "당일 누적 거래대금": f"{int(amt / 100000000):,}억 원" if amt >= 100000000 else "1억 미만",
            "실시간 실전 지침": action_tag
        })

df_final = pd.DataFrame(display_list)

# 출력부 제어
if is_after_market:
    st.error(f"🛑 한국 표준시 오전 집중 운영 시간(08:00~12:00)이 마감되었습니다. (현재 서울: {current_time_str})")
elif now_kst.hour == 8:
    st.info(f"📊 장 개시 전 동시호가 수급 대기 중입니다. 9시 정각부터 데이터가 노출됩니다. (현재 서울: {current_time_str})")
elif is_before_market:
    st.info(f"📊 시스템 가동 전입니다. 한국 시간 오전 8시부터 대기 모드가 시작됩니다. (현재 서울: {current_time_str})")
else:
    if not df_final.empty:
        df_final.insert(0, "실시간 자금유입 순위", [f"{i+1}위" for i in range(len(df_final))])
        st.dataframe(df_final, use_container_width=True, hide_index=True, height=600)
    else:
        st.info("📊 데이터 분석은 정상 작동 중이나 소싱 풀이 비어있습니다. 새로고침을 다시 한 번 눌러주세요.")
