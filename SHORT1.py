import streamlit as st
import pandas as pd
import requests
import time
import os
import json
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="오전 3단계 스캐너 × 네이버 차트 직송 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 통신 준비 중..."

# =====================================================================
# ⏳ 08:00 ~ 12:00 [한국 표준시(KST) 적용] 타임 제어 연산
# =====================================================================
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

is_golden_hour = (9 <= now_kst.hour < 12)
is_before_market = (now_kst.hour < 8)
is_after_market = (now_kst.hour >= 12)

TOKEN_FILE = "hantu_token_cache.json"

# =====================================================================
# 🖥️ 상단 실시간 통신 진단 모니터
# =====================================================================
st.title("🎯 AI 오전 전종목 3단계 스캐너 × 네이버 실시간 차트")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 404/403 우회 + 3단계 분류 직송 엔진
# =====================================================================
class HantuGoldenEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        if not APP_KEY or not APP_SECRET:
            st.session_state.net_log = "❌ Secrets 키 설정 오류! 앱 키가 비어있습니다."
            return None

        now_utc = datetime.now(tz=timezone.utc)

        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, "r") as f:
                    cache = json.load(f)
                expire_time = datetime.fromisoformat(cache["expires_at"])
                if expire_time > now_utc and cache.get("token"):
                    return cache["token"]
            except:
                pass

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=4.0)
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    expires_at = (datetime.now(tz=timezone.utc) + timedelta(hours=5)).isoformat()
                    with open(TOKEN_FILE, "w") as f:
                        json.dump({"token": token, "expires_at": expires_at}, f)
                    return token
            else:
                st.session_state.net_log = f"❌ 토큰 발급 실패 ({r.status_code})"
        except Exception as e:
            st.session_state.net_log = f"❌ 인증 연결 실패 -> {str(e)}"
        return None

    def fetch_market_pool(self, token):
        pool = []
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "3" # 거래대금순 상위 소싱
        }
        try:
            r = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                st.session_state.net_log = f"🟢 수급 파이프라인 동기화 성공! 원본 수: {len(output)}개 ({current_time_str} 기준)"
                
                for item in output:
                    try:
                        ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        raw_price = item.get("stck_prpr", "0")
                        raw_ctrt = item.get("prdy_ctrt", "0.0")
                        raw_volume = item.get("acml_vol", "0")
                        
                        price = float(raw_price) if str(raw_price).replace('.','',1).isdigit() else 0
                        ctrt = float(raw_ctrt) if str(raw_ctrt).replace('-','',1).replace('.','',1).isdigit() else 0.0
                        volume = float(raw_volume) if str(raw_volume).replace('.','',1).isdigit() else 0
                        
                        amt_val = price * volume
                        
                        if ticker.isdigit() and name and name != "None":
                            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                            if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                            
                            pool.append((ticker, name, amt_val, price, ctrt))
                    except:
                        continue
        except Exception as e:
            st.session_state.net_log = f"❌ 수급 데이터 통신 유실 에러 -> {str(e)}"
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 수급 현황 전체 불러오기 (네이버 차트 동기화)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리가 청소되었습니다. 새로고침을 누르세요."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("가장 안전한 채널로 수급 원본 파이프라인 동기화 중..."):
        engine = HantuGoldenEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 수급 테이블 광폭 배치
# =====================================================================
st.markdown("### 📊 실시간 수급 종합 순위표 (원하는 종목 앞 체크박스를 선택하세요)")

display_list = []
if st.session_state.last_pool:
    for t, n, amt, price, ctrt in st.session_state.last_pool:
        if ctrt >= 10.0:
            rank_grade = "🔥 1단계: A급 (수급 대장주)"
            action_tag = "🟢 최우선 돌파/눌림"
        elif ctrt >= 1.0 and ctrt < 10.0:
            rank_grade = "⚡ 2단계: B급 (후발주)"
            action_tag = "🟢 짧은 스캘핑"
        else:
            rank_grade = "⚪ 3단계: C급 (관망)"
            action_tag = "🟡 진입 자제"

        display_list.append({
            "종목코드": t,
            "종목명": n,
            "수급 등급 분류": rank_grade,
            "현재가": f"{int(price):,}원" if price > 0 else "데이터 오류",
            "등락률": f"{ctrt:+.2f}%",
            "추정 거래대금": f"{int(amt / 100000000):,}억 원",
            "실전 지침": action_tag
        })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    df_final.insert(1, "순위", [f"{i+1}위" for i in range(len(df_final))])
    
    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "추정 거래대금", "실전 지침"],
        height=350
    )
    
    selected_rows = edited_df[edited_df["선택"] == True]
    if not selected_rows.empty:
        selected_ticker = selected_rows.iloc[0]["종목코드"]
        selected_name = selected_rows.iloc[0]["종목명"]
    else:
        selected_ticker = df_final.iloc[0]["종목코드"]
        selected_name = df_final.iloc[0]["종목명"]
else:
    st.info("💡 실시간 주도주 불러오기 버튼을 클릭하시면 전 종목 3단계 분류 그리드가 가동됩니다.")

st.write("---")

# =====================================================================
# 📈 [하단 구역] 네이버 실시간 차트 직송 스튜디오 (연결 거부 100% 우회)
# =====================================================================
st.markdown("### 📈 네이버 증권 실시간 오리지널 차트 패널")

if selected_ticker:
    st.success(f"🔍 현재 네이버 실시간 차트 연동 완료: **{selected_name} ({selected_ticker})**")
    
    # 단타용 탭 구성 (분봉 차트와 일봉 차트를 대표님이 원터치로 교체할 수 있게 배정)
    tab1, tab2 = st.tabs(["⚡ 단타 필수: 실시간 당일 분봉 차트", "📅 추세 확인: 일봉 차트"])
    
    with tab1:
        # 🛠️ 네이버 금융 실시간 당일 분봉 차트 서버 이미지 엔진 다이렉트 소싱 주소
        naver_minute_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/area/day/{selected_ticker}.png?sid={int(time.time())}"
        st.image(naver_minute_chart, caption=f"[{selected_name}] 네이버 금융 실시간 당일 거래량 매칭 분봉 현황", use_container_width=True)
        
    with tab2:
        # 🛠️ 네이버 금융 실시간 일봉 차트 서버 이미지 엔진 다이렉트 소싱 주소
        naver_day_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/candle/day/{selected_ticker}.png?sid={int(time.time())}"
        st.image(naver_day_chart, caption=f"[{selected_name}] 네이버 금융 실시간 일봉 캔들 현황", use_container_width=True)
else:
    st.info("⬆️ 상단 순위 리스트에서 원하시는 종목의 [선택] 체크박스를 켜시면 하단에 네이버 오리지널 차트 모니터가 즉시 가동됩니다.")
