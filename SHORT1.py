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
st.set_page_config(page_title="실시간 거래대금 주도주 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 주도주 실시간 파이프라인 대기 중..."

KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

st.title("🎯 AI 당일 상승 주도주 실시간 다이렉트 스캐너 (거래대금 정렬판)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")
st.write("---")

# =====================================================================
# 🏹 잡주를 버리고 진짜 메이저 뭉칫돈을 추적하는 거래대금 소싱 엔진
# =====================================================================
class HantuAmountSourceEngine:
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

    def fetch_market_pool_by_indices(self, token):
        pool = []
        
        # 🛠️ [개조 핵심] 단순 거래량이 아닌 시장의 진짜 '돈'이 도는 [거래대금 순위] API 파이프 바인딩
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        
        # FID_SORT_CLS_CODE = "4" (거래대금 순 정렬 강제 지정)
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "4"
        }
        
        try:
            r_vol = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=4.0)
            if r_vol.status_code == 200:
                vol_output = r_vol.json().get("output", [])
                for rank_idx, item in enumerate(vol_output):
                    t_code = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    if not t_code.isdigit(): continue
                    
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    
                    # 🚫 필터 1단계: 금융 파생상품 노이즈 실시간 파쇄
                    if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                    
                    # 가격 문자열 정수 세척
                    p_str_raw = "".join(filter(str.isdigit, str(item.get("stck_prpr", "0"))))
                    price = int(p_str_raw) if p_str_raw else 0
                    
                    ctrt = float(str(item.get("prdy_ctrt", "0.0")).strip())
                    stat = str(item.get("iscd_stat_cls_code", "00")).strip()
                    
                    # 🛠️ 거래대금 전처리 파싱 (억 원 단위 표시용)
                    raw_amt = float(str(item.get("acml_tr_pbmn", "0")).strip())
                    
                    # 🚫 필터 2단계: 10,000원 이하 호가 지저분한 동전주/잡주 전면 격리
                    if price < 10000: continue
                    
                    # 🚫 필터 3단계: 대표님 절대 명령 - 전일 대비 마이너스 및 보합 하락주 즉시 전면 제거 (양봉 100% 보장)
                    if ctrt <= 0.0: continue
                    
                    pool.append((rank_idx + 1, t_code, name, ctrt, raw_amt, stat))
            else:
                st.session_state.net_log = f"❌ 한투 서버 응답 실패 ({r_vol.status_code})"
        except Exception as e:
            st.session_state.net_log = f"❌ 데이터 통신 오류 -> {str(e)}"

        st.session_state.net_log = f"🟢 실시간 거래대금 상위 주도주 레이더 가동 성공! ({current_time_str})"
        
        # 거래대금 순위로 정렬
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 당일 플러스(+) 상승 주도주 전체 다이렉트 소싱 가동", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리 청소 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("돈이 쏠리는 진짜 우량 대장주 스캔 중... 동전주 자동 패스 완료"):
        engine = HantuAmountSourceEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool_by_indices(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 플러스 상승 우량주 전용 종합 수급 표
# =====================================================================
st.markdown("### 📊 당일 실시간 상승(+) 주도주 마스터 종합 순위표")

display_list = []
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for row in st.session_state.last_pool:
        if isinstance(row, tuple) and len(row) == 6:
            raw_rank, t, n, ctrt, amt, stat = row
            
            stat_prefix = ""
            if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
            elif stat == "52": stat_prefix = "[⚠️유의] "
            elif stat == "51": stat_prefix = "[❌관리] "
            elif stat == "57": stat_prefix = "[🔥경고] "

            if raw_rank <= 30 and ctrt >= 5.0:
                display_name = f"🔥[우량주도-최강] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (지수 주도주)"
                action_tag = "🚀 대한민국 시장 자금을 싹 쓸어담는 핵심 대장 (최우선 공략)"
            elif ctrt >= 5.0:
                display_name = f"💎[우량주도-대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (시세 분출)"
                action_tag = "💎 순위와 무관하게 힘이 폭발하는 지수 내 테마 대장주"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (견고한 양봉 흐름)"
                action_tag = "🟢 수급 확인 완료 / 하단 차트 패널에서 분봉 눌림목 스캘핑 영역 포착"

            # 원본 한투 거래대금 규격 그대로 억 단위 환산 후 깔끔한 포맷팅 마감
            amt_display = f"{int(amt / 100000000):,}억 원" if amt > 0 else "실시간 집계 중"

            display_list.append({
                "당일 대금 순위": f"{raw_rank}위",
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"⬇️ 하단 실시간 오리지널 차트에서 정품 가격 즉시 연동",
                "등락률": f"{ctrt:+.2f}%",
                "당일 누적대금": amt_display,
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
    # 주성엔지니어링 발견 시 즉시 체크 락인 활성화
    for i, r in df_final.iterrows():
        if "주성엔지니어링" in r["종목명"]:
            df_final.loc[i, "선택"] = True
            break

    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["당일 대금 순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "당일 누적대금", "실전 행동 지침"],
        height=450
    )
    
    selected_rows = edited_df[edited_df["선택"] == True]
    if not selected_rows.empty:
        selected_ticker = selected_rows.iloc[0]["종목코드"]
        raw_selected_name = selected_rows.iloc[0]["종목명"]
        selected_name = raw_selected_name.split("]")[-1].strip()
    else:
        selected_ticker = df_final.iloc[0]["종목코드"]
        raw_selected_name = df_final.iloc[0]["종목명"]
        selected_name = raw_selected_name.split("]")[-1].strip()
else:
    st.info("💡 동기화 대기 중입니다. 위의 버튼을 누르시면 거래대금 깡패 종목들이 유실 없이 화면 가득 대거 쏟아집니다.")

st.write("---")

# =====================================================================
# 📈 [하단 구역] 네이버 실시간 차트 스튜디오
# =====================================================================
st.markdown("### 📈 네이버 페이 증권 실시간 오리지널 차트 패널")

if selected_ticker:
    st.success(f"🔍 현재 분석 동기화 차트: **{selected_name} ({selected_ticker})**")
    
    tab1, tab2 = st.tabs(["⚡ 단타 필수: 실시간 당일 분봉 차트", "📅 추세 확인: 일봉 차트"])
    time_seed = int(time.time())
    
    with tab1:
        naver_minute_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/area/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_minute_chart, caption=f"[{selected_name}] 네이버 실시간 분봉 및 당일 세력 거래량 분석", use_container_width=True)
        
    with tab2:
        naver_day_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/candle/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_day_chart, caption=f"[{selected_name}] 네이버 실시간 일봉 캔들 추세 지지선", use_container_width=True)
else:
    st.info("⬆ 상단 순위 리스트에서 원하시는 종목의 [선택] 체크박스를 켜시면 하단에 네이버 오리지널 차트가 표출됩니다.")
