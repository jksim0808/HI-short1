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
st.set_page_config(page_title="국대 우량주 지수 전수 마스터 스캐너", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 통신 라인 대기 중..."

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
st.title("🎯 코스피 200 × 코스닥 150 전수 수급 마스터 스캐너")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 코스피200 / 코스닥150 결합형 대장주 추적 엔진
# =====================================================================
class HantuIndexMasterEngine:
    def __init__(self):
        self.session = requests.Session()
        
    def get_token(self):
        if not APP_KEY or not APP_SECRET:
            st.session_state.net_log = "❌ Secrets 키 설정 오류! 앱 키가 비어있습니다."
            return None

        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

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
                    expires_at = (datetime.utcnow() + timedelta(hours=5)).isoformat()
                    with open(TOKEN_FILE, "w") as f:
                        json.dump({"token": token, "expires_at": expires_at}, f)
                    return token
            else:
                st.session_state.net_log = f"❌ 토큰 발급 실패 ({r.status_code})"
        except Exception as e:
            st.session_state.net_log = f"❌ 인증 연결 실패 -> {str(e)}"
        return None

    def fetch_index_components(self, token, iscd_code):
        """
        한투 주식지수구성종목 API 호출
        0001: 코스피 200, 2001: 코스닥 150
        """
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-category-master"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01100000", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd_code}
        
        tickers = []
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=6.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                for item in output:
                    t_code = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    if t_code.isdigit():
                        tickers.append(t_code)
        except: pass
        return tickers

    def fetch_market_pool_by_indices(self, token):
        # 1단계: 코스피 200 (0001) 및 코스닥 150 (2001) 정예 마스터 종목 코드 전수 싱크
        kospi200_tickers = self.fetch_index_components(token, "0001")
        kosdaq150_tickers = self.fetch_index_components(token, "2001")
        
        total_tickers = list(set(kospi200_tickers + kosdaq150_tickers))
        
        if not total_tickers:
            st.session_state.net_log = "⚠️ 한국거래소 지수 파이프라인 동기화 지연 -> 재시도 필요"
            return []
            
        st.session_state.net_log = f"🟢 양대지수 정예 {len(total_tickers)}개 종목 락인 완료! 실시간 수급 계측 중..."
        
        # 2단계: 거래대금 상위 순위 뼈대를 매칭하기 위해 volume-rank 호출하여 랭킹 마스터 데이터 확보
        rank_map = {}
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "3"
        }
        
        try:
            r_vol = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=5.0)
            if r_vol.status_code == 200:
                vol_output = r_vol.json().get("output", [])
                for rank_idx, item in enumerate(vol_output):
                    t_code = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    rank_map[t_code] = {
                        "rank": rank_idx + 1,
                        "name": str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip(),
                        "price": float(str(item.get("stck_prpr", "0")).replace("-", "").strip()),
                        "ctrt": float(str(item.get("prdy_ctrt", "0.0")).strip()),
                        "volume": float(str(item.get("acml_vol", "0")).strip()),
                        "stat": str(item.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass

        pool = []
        # 3단계: 지수 구성 종목 중에서 자금이 도는 종목들을 순위 맵에서 매핑 및 정제
        for ticker in total_tickers:
            if ticker in rank_map:
                r_data = rank_map[ticker]
                price = r_data["price"]
                name = r_data["name"]
                ctrt = r_data["ctrt"]
                stat = r_data["stat"]
                amt_val = price * r_data["volume"]
                raw_rank = r_data["rank"]
                
                # 🚫 대표님 필터 1단계: 파생상품/인버스/리츠 노이즈 자동 소멸
                if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                
                # 🚫 대표님 필터 2단계: 10,000원 이하 동전주/잡주 격리 커트
                if price < 10000: continue
                
                # 주성엔지니어링 등 조건 통과한 핵심 우량주들만 안전 적재
                pool.append((raw_rank, ticker, name, amt_val, price, ctrt, stat))
                
        # 수급 활성도가 높은 순(거래대금 순위가 높은 순)으로 최종 칼정렬
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 양대 지수(코스피200·코스닥150) 우량 주도주 전수 동기화", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 시스템 캐시 메모리가 소독되었습니다."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("대한민국 국가대표 우량주 350개 전수 계측 시스템 기동 중..."):
        engine = HantuIndexMasterEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool_by_indices(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 양대 지수 연동형 우량주 전용 통합 수급 표
# =====================================================================
st.markdown("### 📊 실시간 350대 우량주 수급 순위표 (원하는 종목의 체크박스를 선택하세요)")

display_list = []
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for row in st.session_state.last_pool:
        if isinstance(row, tuple) and len(row) == 7:
            raw_rank, t, n, amt, price, ctrt, stat = row
            
            # 실시간 VI 및 호가 정지 상태 기호 판독
            stat_prefix = ""
            if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
            elif stat == "52": stat_prefix = "[⚠️유의] "
            elif stat == "51": stat_prefix = "[❌관리] "
            elif stat == "57": stat_prefix = "[🔥경고] "

            # 🛠️ 지수 전수 조사 전용 주도테마 마킹 알고리즘
            if raw_rank <= 30 and ctrt >= 10.0:
                display_name = f"🔥[우량주도-최강] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (지수 주도주)"
                action_tag = "🚀 대한민국 시장 돈을 싹 쓸어담는 핵심 대장 (최우선 공략)"
            elif ctrt >= 10.0:
                display_name = f"💎[우량주도-대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (시세 분출)"
                action_tag = "💎 순위와 무관하게 힘이 폭발하는 지수 내 테마 대장주"
            elif ctrt >= 1.0 and ctrt < 10.0:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (견고한 흐름)"
                action_tag = "🟢 수급 유입 완료 / 1분봉 눌림목 스캘핑"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚪ 3단계: C급 (숨고르기)"
                action_tag = "🟡 대금 유입 대기 / 지지선 횡보 관망 구역"

            display_list.append({
                "시장 자금 순위": f"{raw_rank}위" if raw_rank <= 100 else "100위권 밖",
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"{int(price):,}원",
                "등락률": f"{ctrt:+.2f}%",
                "당일 누적대금": f"{int(amt / 100000000):,}억 원",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
    # 대표 주성엔지니어링이 리스트에 포착되었을 경우 최적의 시각적 락인을 위해 기본 포커싱 유도
    for i, r in df_final.iterrows():
        if "주성엔지니어링" in r["종목명"]:
            df_final.loc[i, "선택"] = True
            break

    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["시장 자금 순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "당일 누적대금", "실전 행동 지침"],
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
    st.info("💡 우량주 통합 스캐너 가동 준비 완료. 위의 동기화 버튼을 클릭하시면 350대 정예 라인업이 전개됩니다.")

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
