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
st.set_page_config(page_title="100위권 우량 주도주 마스터 스캐너", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 통신 준비 중..."

# =====================================================================
# ⏳ 타임 제어 연산 [KST 적용]
# =====================================================================
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

# =====================================================================
# 🖥️ 상단 실시간 통신 진단 모니터
# =====================================================================
st.title("🎯 AI 1위~100위 우량 주도주 매칭 마스터 스캐너")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 1위~100위 전수 수집 및 하이브리드 필터링 엔진
# =====================================================================
class HantuMasterEngine:
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

    def fetch_master_volume_rank(self, token):
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
                
                st.session_state.net_log = f"🟢 한투 오피셜 100위권 파이프라인 연동 성공! 리스크 정화 중 ({current_time_str} 기준)"
                
                # 한투 서버가 보내주는 100개 풀을 원본 순위(idx)를 유지한 채 전수 파싱
                for idx, item in enumerate(output):
                    try:
                        raw_rank = idx + 1
                        ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        raw_price = str(item.get("stck_prpr", "0")).replace("-", "").strip()
                        raw_ctrt = str(item.get("prdy_ctrt", "0.0")).strip()
                        raw_volume = str(item.get("acml_vol", "0")).strip()
                        stat_code = str(item.get("iscd_stat_cls_code", "00")).strip()
                        
                        price = float(raw_price) if raw_price.replace('.','',1).isdigit() else 0
                        ctrt = float(raw_ctrt) if raw_ctrt.replace('-','',1).replace('.','',1).isdigit() else 0.0
                        volume = float(raw_volume) if raw_volume.replace('.','',1).isdigit() else 0
                        
                        amt_val = price * volume
                        
                        if ticker.isdigit() and name and name != "None":
                            # 🚫 필터 1단계: 스팩/ETF/ETN/인버스/레버리지 노이즈 무조건 파쇄
                            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                            if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                            
                            # 🚫 필터 2단계: 만원 이하 잡주/동전주 철저 격리 차단 (우량주만 통과)
                            if price < 10000: continue
                            
                            # 원본 랭킹 번호(`raw_rank`)를 들고 메인 리스트 구축
                            pool.append((raw_rank, ticker, name, amt_val, price, ctrt, stat_code))
                    except:
                        continue
        except Exception as e:
            st.session_state.net_log = f"❌ 마스터 데이터 수집 무력화 에러 -> {str(e)}"
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 1위~100위 오피셜 주도주 새로고침 (클린 우량주 버전)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리가 청소되었습니다. 새로고침을 누르세요."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("대한민국 거래대금 100위권 전수 계측 및 테마 필터링 중..."):
        engine = HantuMasterEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_master_volume_rank(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 1위~100위 원본 연동 우량주 종합 수급 표
# =====================================================================
st.markdown("### 📊 실시간 거래대금 100위권 정제 순위표 (원하는 종목의 체크박스를 켜세요)")

display_list = []
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for row in st.session_state.last_pool:
        if isinstance(row, tuple) and len(row) == 7:
            raw_rank, t, n, amt, price, ctrt, stat = row
            
            # 실시간 호가 상태 기호 판독
            stat_prefix = ""
            if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
            elif stat == "52": stat_prefix = "[⚠️유의] "
            elif stat == "51": stat_prefix = "[❌관리] "
            elif stat == "57": stat_prefix = "[🔥경고] "

            # 🛠️ [테마주 마킹 및 3단계 우선순위 매칭 구조]
            if raw_rank <= 20 and ctrt >= 10.0:
                display_name = f"🔥[1순위-최강주도] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (최강 주도주)"
                action_tag = "🚀 대한민국 시장 자금 블랙홀 (최우선 공략)"
            elif raw_rank > 20 and ctrt >= 10.0:
                display_name = f"💎[2순위-주도대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (신상 대장주)"
                action_tag = "💎 순위는 낮지만 힘이 응축된 신상 테마 대장주 (강추)"
            elif ctrt >= 1.0 and ctrt < 10.0:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (후발/단기)"
                action_tag = "🟢 수급 유입 및 추세 유지 / 짧은 스캘핑"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚪ 3단계: C급 (보합이하)"
                action_tag = "🟡 자금 회전용 횡보 구역 (매매 자제)"

            display_list.append({
                "한투 오피셜 순위": f"{raw_rank}위",
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"{int(price):,}원",
                "등락률": f"{ctrt:+.2f}%",
                "실시간 거래대금": f"{int(amt / 100000000):,}억 원",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["한투 오피셜 순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "실시간 거래대금", "실전 행동 지침"],
        height=380
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
    st.info("💡 장중 실시간 수급 동기화 대기 중입니다. 상단 버튼을 눌러 스캐너를 가동해 주세요.")

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
        st.image(naver_minute_chart, caption=f"[{selected_name}] 네이버 실시간 분봉 및 장중 자금 유입 흐름", use_container_width=True)
        
    with tab2:
        naver_day_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/candle/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_day_chart, caption=f"[{selected_name}] 네이버 실시간 일봉 누적 캔들 추세", use_container_width=True)
else:
    st.info("⬆ 상단 순위 리스트에서 원하시는 종목의 [선택] 체크박스를 켜시면 하단에 네이버 오리지널 차트가 표출됩니다.")
