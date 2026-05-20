import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="오전 집중 주도주 스캐너 Pro (KST)", layout="wide")

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
is_golden_hour = (9 <= now_kst.hour < 12) # 실제 장중 (9시, 10시, 11시)
is_before_market = (now_kst.hour < 8)
is_after_market = (now_kst.hour >= 12)

# 카운트다운 및 타임 배너 제어
if is_golden_hour:
    remaining_hours = 11 - now_kst.hour
    remaining_min = 60 - now_kst.minute
    time_status_msg = f"🔥 [오전 주도주 모드 가동 중] 12:00 마감까지 **{remaining_hours}시간 {remaining_min}분** 남았습니다. (현재 서울: {current_time_str})"
    status_color = "inverse"
elif now_kst.hour == 8:
    time_status_msg = f"💤 [장 개시 전 세팅 상태] 한국 표준시 9시 정각부터 실시간 주도주 소싱이 활성화됩니다. (현재 서울: {current_time_str})"
    status_color = "info"
elif is_before_market:
    time_status_msg = f"💤 [운영 전] 본 프로그램은 한국 시간 오전 8시부터 낮 12시까지만 작동합니다. (현재 서울: {current_time_str})"
    status_color = "info"
else:
    time_status_msg = f"🛑 [오전 운영 마감] 낮 12시가 경과하여 오전 스캐너가 마감되었습니다. (현재 서울: {current_time_str})"
    status_color = "error"

# =====================================================================
# 🖥️ 상단 고정 가이드라인
# =====================================================================
st.title("⚡ AI 08시~12시 오전 집중 단타 스캐너 (Pro - KST)")

if status_color == "inverse":
    st.success(time_status_msg)
elif status_color == "info":
    st.info(time_status_msg)
else:
    st.error(time_status_msg)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 🏹 오전 시간대별 동적 수급 로직")
    st.markdown(
        """
        * **08:00 ~ 09:00**: 장전 대기 모드 (데이터 소싱 제한)
        * **09:00 ~ 09:15**: 당일 거래대금 **1억 이상** (초동 시초가 대장주 유연 포착)
        * **09:15 ~ 12:00**: 당일 거래대금 **30억 이상** (오전 최종 주도주 검증 및 압축)
        """
    )
with col2:
    st.markdown("### 📊 AI 단타 매매 등급")
    st.markdown(
        """
        * **🔥 A급 (오전 대장주)**: 등락률 **+10% ~ +25% 미만** (돌파/눌림목 핵심 타깃)
        * **⚡ B급 (후발/단기수급)**: 등락률 **+1% ~ +10% 미만** (짧은 방망이 스캘핑 타깃)
        * **❌ 과열/추격 금지**: 등락률 **+25% 이상** (상한가 풀림 및 고점 투매 리스크 고조)
        * **❌ 12시 이후**: 12시 정각 통과 시 **모든 데이터 셧다운 및 매매 금지**
        """
    )
with col3:
    st.markdown("### 🚨 실전 매매 수칙")
    st.markdown(
        """
        1. **09:00 오픈 직후**: 수급이 급격하게 회전하므로, 새로고침을 통해 상위에 빠르게 붙는 1등주에 주목합니다.
        2. **09:15 이후 안정기**: 가짜 갭상승 종목들이 거래대금 30억 문턱에 걸려 필터링되므로, 진짜 주도주만 걸러집니다.
        3. **12:00 기계적 청산**: 점심시간 직전 변동성이 죽는 투매 구간에 당하지 말고 오전 매매를 마감합니다.
        """
    )

st.write("---")

# =====================================================================
# 🏹 오전 집중형 거래대금 엔진 (필터 꼬임 해결 버전)
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
        # 장중(9시~12시)이 아니면 API 호출 차단
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
                
                # 🛠️ [로직 단순화] 9시 극초반 필터 오류 가능성을 없애기 위해 15분 기준으로만 크게 양분
                now_check = datetime.now(tz=KST)
                if now_check.hour == 9 and now_check.minute <= 15:
                    min_amt = 100000000       # 09:00 ~ 09:15 -> 최소 1억 원 (초동 수급 다 잡아냄)
                else:
                    min_amt = 3000000000      # 09:15 ~ 12:00 -> 최소 30억 원 (검증된 주도주)
                
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
                        # 금융 노이즈(스팩, 리츠, 우선주, 인버스, 레버리지) 및 동전주 차단
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                        if price < 2000: continue
                        
                        # 가변 거래대금 문턱 및 당일 상승 수급(+1% 이상) 적용
                        if amt_val < min_amt or ctrt < 1.0: continue
                        
                        pool.append((ticker, name, amt_val, price, ctrt))
        except: pass
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    # 9시~12시 사이에만 버튼 활성화
    btn_fetch = st.button("🔄 실시간 오전 주도주 새로고침 (한국시간 09~12시 작동)", type="primary", use_container_width=True, disabled=not is_golden_hour)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.last_pool = []
    st.rerun()

if btn_fetch and is_golden_hour:
    st.session_state.last_pool = []
    with st.spinner("오전 실시간 주도주 수급 스캐닝 중..."):
        engine = HantuGoldenEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool(token)
            st.rerun()

# =====================================================================
# 📊 실시간 등급 바인딩 및 최종 렌더링
# =====================================================================
display_list = []

if st.session_state.last_pool:
    for t, n, amt, price, ctrt in st.session_state.last_pool:
        
        if is_after_market:
            rank_grade = "❌ 오전 장 마감 (진입 금지 / 전량 청산)"
            status_tag = "🔴 운영 종료"
        else:
            if ctrt >= 25.0:
                rank_grade = "❌ 과열 (추격 금지 구간)"
                status_tag = "🟡 관망"
            elif ctrt >= 10.0 and ctrt < 25.0:
                rank_grade = "🔥 A급 (오전 대장주)"
                status_tag = "🟢 주 타깃"
            else:
                rank_grade = "⚡ B급 (후발/단기수급)"
                status_tag = "🟢 스캘핑"

        display_list.append({
            "종목코드": t,
            "종목명": n,
            "AI 단타 매매등급": rank_grade,
            "현재가": f"{int(price):,}원",
            "등락률": f"{ctrt:+.2f}%",
            "당일 누적 거래대금": f"{int(amt / 100000000):,}억 원" if amt >= 100000000 else "1억 미만",
            "실시간 행동 지침": status_tag
        })

df_final = pd.DataFrame(display_list)

# 출력부 제어 (한국 표준시 기준 안내 배너)
if is_after_market:
    st.error(f"🛑 한국 표준시 오전 집중 운영 시간(08:00~12:00)이 마감되었습니다. (현재 서울: {current_time_str})")
elif now_kst.hour == 8:
    st.info(f"📊 장 개시 전 동시호가 분석 대기 중입니다. 9시 정각부터 실시간 대장주 추적이 활성화됩니다. (현재 서울: {current_time_str})")
elif is_before_market:
    st.info(f"📊 시스템 가동 전입니다. 한국 시간 오전 8시부터 대기 모드가 시작됩니다. (현재 서울: {current_time_str})")
else:
    if not df_final.empty:
        df_final.insert(0, "오전 수급순위", [f"{i+1}위" for i in range(len(df_final))])
        st.dataframe(df_final, use_container_width=True, hide_index=True, height=550)
    else:
        st.info("📊 현재 등락률 및 거래대금 조건을 만족하는 오전 주도주가 없습니다. 새로고침을 다시 한 번 진행해 주세요.")
