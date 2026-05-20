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
st.set_page_config(page_title="실시간 주도주 다이렉트 소싱 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 실시간 파이프라인 대기 중..."

KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

st.title("🎯 AI 당일 상승 주도주 실시간 다이렉트 스캐너 (명단 제한 해제판)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")
st.write("---")

# =====================================================================
# 🏹 수동 제한 명단 없이 한투 수급 데이터를 실시간 다이렉트 파싱하는 엔진
# =====================================================================
class HantuDirectSourceEngine:
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
        
        # 🛠️ 수동 고정 명단을 완전히 삭제하고, 한투 서버가 실시간으로 집계하는 수급 상위 패킷을 다이렉트로 직접 호출
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        
        # 장중 자금 쏠림의 양대 축인 [3: 거래대금순] 및 [5: 시가총액비중순] 전체를 복합 다이렉트 스캔 수행
        for sort_cls in ["3", "5"]:
            params_vol = {
                "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": sort_cls
            }
            try:
                r_vol = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=4.0)
                if r_vol.status_code == 200:
                    vol_output = r_vol.json().get("output", [])
                    for rank_idx, item in enumerate(vol_output):
                        t_code = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        if not t_code.isdigit(): continue
                        
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        # 🚫 필터 1단계: ETF / 파생상품 노이즈 실시간 무조건 파쇄
                        if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                        
                        # 데이터 오염을 막기 위한 문자열 순수 정수 세척
                        p_str_raw = "".join(filter(str.isdigit, str(item.get("stck_prpr", "0"))))
                        price = int(p_str_raw) if p_str_raw else 0
                        
                        ctrt = float(str(item.get("prdy_ctrt", "0.0")).strip())
                        stat = str(item.get("iscd_stat_cls_code", "00")).strip()
                        
                        # 🚫 필터 2단계: 10,000원 이하 호가 변동 지저분한 동전주/잡주 컷
                        if price < 10000: continue
                        
                        # 🚫 필터 3단계: 대표님 절대 명령 - 전일 대비 마이너스 및 보합 하락주 즉시 전면 격리 제거 (양봉 고정)
                        if ctrt <= 0.0: continue
                        
                        raw_rank = rank_idx + 1 if sort_cls == "3" else 999
                        
                        # 중복 종목 유입 방지 처리
                        if not any(x[1] == t_code for x in pool):
                            pool.append((raw_rank, t_code, name, ctrt, stat))
                time.sleep(0.1)
            except: pass

        st.session_state.net_log = f"🟢 실시간 다이렉트 소싱 엔진 가동 성공! ({current_time_str})"
        
        # 자금력 집중 순위(거래대금 상위 순)로 칼정렬
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
    with st.spinner("명단 제한 철폐 완료! 한투 실시간 주도주 직접 파이프라인 수집 중..."):
        engine = HDirectSourceEngine = HantuDirectSourceEngine()
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
        if isinstance(row, tuple) and len(row) == 5:
            raw_rank, t, n, ctrt, stat = row
            
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

            display_list.append({
                "시장 자금 순위": f"{raw_rank}위" if raw_rank <= 100 else "100위권 밖",
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"⬇️ 하단 실시간 오리지널 차트에서 정품 가격 즉시 연동",
                "등락률": f"{ctrt:+.2f}%",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
    # 주성엔지니어링 포착 시 자동 락인 기본 체크
    for i, r in df_final.iterrows():
        if "주성엔지니어링" in r["종목명"]:
            df_final.loc[i, "선택"] = True
            break

    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["시장 자금 순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "실전 행동 지침"],
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
    st.info("💡 동기화 대기 중입니다. 위의 버튼을 누르시면 오늘 실시간으로 돈이 쏠리며 상승 중인 대한민국 모든 주도 종목들이 순위대로 노출됩니다.")

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
