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
st.set_page_config(page_title="오전 전종목 3단계 수급 스캐너 Pro", layout="wide")

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
st.title("⚡ AI 오전 전종목 3단계 실시간 수급 스캐너 (Pro - KST)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 1분당 1회 초과 발급 원천방쇄형 파일 캐시 엔진
# =====================================================================
class HantuGoldenEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        if not APP_KEY or not APP_SECRET:
            st.session_state.net_log = "❌ Secrets 키 설정 오류! 앱 키가 비어있습니다."
            return None

        now_utc = datetime.now(tz=timezone.utc)

        # 🛠️ [해결책] 1단계: 파일에 저장된 영구 토큰이 있는지 체크
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, "r") as f:
                    cache = json.load(f)
                expire_time = datetime.fromisoformat(cache["expires_at"])
                
                # 아직 토큰 유효 시간이 남아있다면 파일에서 꺼내서 즉시 반환 (한투 서버 호출 안함)
                if expire_time > now_utc and cache.get("token"):
                    st.session_state.net_log = "🟢 [안전 캐시] 로컬 파일 캐시에서 유효 토큰을 재사용합니다. (안전 구동 중)"
                    return cache["token"]
            except:
                pass

        # 2단계: 파일에 없거나 만료된 경우에만 딱 1번만 한투 서버에 요청
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        try:
            r = self.session.post(url, json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}, timeout=4.0)
            if r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    # 유효기간 5시간 설정 후 파일에 쓰기
                    expires_at = (datetime.now(tz=timezone.utc) + timedelta(hours=5)).isoformat()
                    with open(TOKEN_FILE, "w") as f:
                        json.dump({"token": token, "expires_at": expires_at}, f)
                    
                    st.session_state.net_log = "🟢 [신규 발급] 한투 서버로부터 안전하게 토큰을 신규 갱신했습니다."
                    return token
            else:
                # 🛠️ 디버깅 가시성 강화
                if "EGW00133" in r.text:
                    st.session_state.net_log = "❌ [한투 시스템 거부] 1분 제한에 걸렸습니다! 30초만 가만히 기다렸다가 다시 새로고침을 누르세요."
                else:
                    st.session_state.net_log = f"❌ 토큰 발급 HTTP 실패 ({r.status_code}) -> {r.text}"
        except Exception as e:
            st.session_state.net_log = f"❌ 인증 서버 연결 실패 -> {str(e)}"
        return None

    def fetch_market_pool(self, token):
        pool = []
        url_amt = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/trade-amount-range"
        headers_amt = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "HHDFS76200100", "custtype": "P"
        }
        params_amt = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20172", "FID_INPUT_ISCD": "0000"
        }
        try:
            r = self.session.get(url_amt, headers=headers_amt, params=params_amt, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                st.session_state.net_log = f"🟢 수급 분석 완료! 서버 수신 데이터 수: {len(output)}개 (현재 시각: {current_time_str})"
                
                for item in output:
                    try:
                        ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        raw_amt = item.get("amt", "0")
                        raw_price = item.get("stck_prpr", "0")
                        raw_ctrt = item.get("prdy_ctrt", "0.0")
                        
                        amt_val = float(raw_amt) * 1000000 if str(raw_amt).replace('.','',1).isdigit() else 0
                        price = float(raw_price) if str(raw_price).replace('.','',1).isdigit() else 0
                        ctrt = float(raw_ctrt) if str(raw_ctrt).replace('-','',1).replace('.','',1).isdigit() else 0.0
                        
                        if ticker.isdigit() and name and name != "None":
                            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                            if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                            
                            pool.append((ticker, name, amt_val, price, ctrt))
                    except:
                        continue
            else:
                st.session_state.net_log = f"❌ 데이터 요청 HTTP 에러 ({r.status_code})"
        except Exception as e:
            st.session_state.net_log = f"❌ 수급 데이터 패킷 유실 에러 -> {str(e)}"
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 수급 현황 전체 불러오기 (토큰 잠금 우회 버전)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 캐시 강제 강제 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 로컬 토큰 파일과 메모리가 완전히 청소되었습니다. 1분 뒤 새로고침을 누르세요."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("서버 원본 데이터 안전 소싱 중..."):
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
        if ctrt >= 10.0:
            rank_grade = "🔥 1단계: A급 (수급 대장주)"
            action_tag = "🟢 최우선 돌파/눌림 타깃"
        elif ctrt >= 1.0 and ctrt < 10.0:
            rank_grade = "⚡ 2단계: B급 (후발/단기수급)"
            action_tag = "🟢 방망이 짧게 스캘핑"
        else:
            rank_grade = "⚪ 3단계: C급 (보합이하/관망)"
            action_tag = "🟡 진입 자제 / 단순 자금유입"

        display_list.append({
            "종목코드": t,
            "종목명": n,
            "수급 등급 분류": rank_grade,
            "현재가": f"{int(price):,}원" if price > 0 else "데이터 오류",
            "등락률": f"{ctrt:+.2f}%",
            "당일 누적 거래대금": f"{int(amt / 100000000):,}억 원" if amt >= 100000000 else "1억 미만",
            "실시간 실전 지침": action_tag
        })

df_final = pd.DataFrame(display_list)

if not df_final.empty:
    df_final.insert(0, "실시간 자금유입 순위", [f"{i+1}위" for i in range(len(df_final))])
    st.dataframe(df_final, use_container_width=True, hide_index=True, height=600)
else:
    st.info(f"📊 대기 상태입니다. 위의 모니터 확인 후 [실시간 수급 현황 전체 불러오기]를 눌러주세요.")
