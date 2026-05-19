import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="장 초반 1시간 골든아워 스캐너 Pro (KST)", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "hantu_token" not in st.session_state: st.session_state.hantu_token = None
if "token_expires_at" not in st.session_state: st.session_state.token_expires_at = None

# =====================================================================
# ⏳ 09:00 ~ 10:00 [한국 표준시(KST) 강제 바인딩] 타임 제어 연산
# =====================================================================
# 🛠️ [대한민국 표준시 설정] 서버 위치와 상관없이 무조건 한국 시간으로 강제 동기화
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

# 한국 표준시 기준 상태 체크 (9시~10시 여부)
is_golden_hour = (now_kst.hour == 9)
is_before_market = (now_kst.hour < 9)
is_after_market = (now_kst.hour >= 10)

# 카운트다운 및 타임 배너 제어
if is_golden_hour:
    remaining_min = 60 - now_kst.minute
    time_status_msg = f"🔥 [한국 표준시 기준 골든아워 운영 중] 오전 10시 마감까지 **{remaining_min}분** 남았습니다. 칼손절/칼익절 필수! (현재 서울: {current_time_str})"
    status_color = "inverse"
elif is_before_market:
    time_status_msg = f"💤 [장 개시 전] 한국 표준시 오전 9시 정각부터 10시까지만 작동하는 모드입니다. (현재 서울: {current_time_str})"
    status_color = "info"
else:
    time_status_msg = f"🛑 [운영 종료] 대한민국 표준시 오전 10시 골든아워가 마감되었습니다. 현재 시간 이후 진입은 무조건 뇌동매매입니다. (현재 서울: {current_time_str})"
    status_color = "error"

# =====================================================================
# 🖥️ 상단 고정 가이드라인
# =====================================================================
st.title("⚡ AI 9시~10시 단타 골든아워 검색기 (Pro - KST 전용)")

if status_color == "inverse":
    st.success(time_status_msg)
elif status_color == "info":
    st.info(time_status_msg)
else:
    st.error(time_status_msg)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 🏹 1시간 초집중 가변 수급 로직")
    st.markdown(
        """
        * **09:00 ~ 09:10**: 당일 거래대금 **5억 이상** 즉시 포착 (초동 대장주)
        * **09:10 ~ 09:30**: 당일 거래대금 **30억 이상** 락업 (주도주 압축)
        * **09:30 ~ 10:00**: 당일 거래대금 **50억 이상** 검증 (진짜 대장주)
        """
    )
with col2:
    st.markdown("### 📊 골든아워 AI 등급 체계")
    st.markdown(
        """
        * **🔥 A급 (골든 대장주)**: 등락률 **+10% ~ +25% 미만** (돌파/눌림목 최적 타깃)
        * **⚡ B급 (후발/단기수급)**: 등락률 **+1% ~ +10% 미만** (짧은 스캘핑 타깃)
        * **❌ 매매금지/과열**: 등락률 **+25% 이상** (상한가 털기 리스크 최고조 부근)
        * **❌ 10시 이후**: 10시 정각 통과 시 **모든 종목 자동 매매 금지 전환**
        """
    )
with col3:
    st.markdown("### 🚨 실전 매매 행동 수칙")
    st.markdown(
        """
        1. **9시 5분 전후 첫 진입**: 거래대금 5억 필터로 가장 빠르게 쏘아 올리는 1등주에 편승합니다.
        2. **9시 40분 이후 보수적 접근**: 거래대금 50억 족쇄가 채워지며, 힘이 빠지는 종목은 리스트에서 자동 소멸합니다.
        3. **10시 정각 올 청산**: 수익이든 손실이든 한국 시간 10시 정각에는 무조건 컴퓨터를 끄는 것이 상책입니다.
        """
    )

st.write("---")

# =====================================================================
# 🏹 골든아워 전용 거래대금 엔진 (KST 제어 탑재)
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
        # 한국 표준시로 10시가 넘어가면 API 호출 자체를 락인(Lock-in)하여 불필요한 트래픽 해제
        if is_after_market:
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
                
                # 🛠️ 한국 표준시(KST) 타임 윈도우별 자금 커트라인 정교화
                now_check = datetime.now(tz=KST)
                if now_check.hour == 9 and now_check.minute <= 10:
                    min_amt = 500000000       # 09:00 ~ 09:10 -> 최소 5억 원
                elif now_check.hour == 9 and now_check.minute <= 30:
                    min_amt = 3000000000      # 09:10 ~ 09:30 -> 최소 30억 원
                else:
                    min_amt = 5000000000      # 09:30 ~ 10:00 -> 최소 50억 원
                
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
                        # 금융 노이즈(스팩, 리츠, 우선주, 인버스, 레버리지) 및 동전주 필터링
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                        if price < 2000: continue
                        
                        # KST 가변 거래대금 및 최소 등락률(+1% 이상) 적용
                        if amt_val < min_amt or ctrt < 1.0: continue
                        
                        pool.append((ticker, name, amt_val, price, ctrt))
        except: pass
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 골든아워 주도주 새로고침 (한국시간 09~10시만 작동)", type="primary", use_container_width=True, disabled=is_after_market)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    st.session_state.hantu_token = None
    st.session_state.token_expires_at = None
    st.session_state.last_pool = []
    st.rerun()

if btn_fetch and is_golden_hour:
    st.session_state.last_pool = []
    with st.spinner("한국 표준시 기준 실시간 자금 필터링 연산 중..."):
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
        
        # 장중에 앱을 띄워놓고 보다가 한국 시간 10시를 통과하면 실시간으로 화면 정지 및 매매 금지 표기
        if is_after_market:
            rank_grade = "❌ 장 마감 (진입 금지 / 전량 청산)"
            status_tag = "🔴 운영 종료"
        else:
            if ctrt >= 25.0:
                rank_grade = "❌ 과열 (추격 금지 구간)"
                status_tag = "🟡 관망"
            elif ctrt >= 10.0 and ctrt < 25.0:
                rank_grade = "🔥 A급 (골든 대장주)"
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
            "당일 누적 거래대금": f"{int(amt / 100000000):,}억 원",
            "실시간 행동 지침": status_tag
        })

df_final = pd.DataFrame(display_list)

# 출력부 제어 (모두 한국 표준시 기준)
if is_after_market:
    st.error(f"🛑 한국 표준시 오전 10시가 경과하여 당일 스캐너가 자동 셧다운되었습니다. (현재 서울: {current_time_str})")
elif is_before_market:
    st.info(f"📊 장 개시 전입니다. 한국 시간 아침 9시 정각부터 실시간 대장주 추적을 시작합니다. (현재 서울: {current_time_str})")
else:
    if not df_final.empty:
        df_final.insert(0, "골든아워 수급순위", [f"{i+1}위" for i in range(len(df_final))])
        st.dataframe(df_final, use_container_width=True, hide_index=True, height=550)
    else:
        st.info("📊 한국 표준시 기준 주도주 조건에 맞는 종목이 없습니다. 새로고침을 진행해 주세요.")
