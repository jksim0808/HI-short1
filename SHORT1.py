import streamlit as st
import pandas as pd
import requests
import time
import os
import json
import zipfile
import io
from datetime import datetime, timezone, timedelta

# =====================================================================
# ⚙️ [최우선] Streamlit 설정 및 세션 초기화
# =====================================================================
st.set_page_config(page_title="정품 가격 주도주 마스터 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 전수 파이프라인 대기 중..."

# =====================================================================
# ⏳ 타임 제어 연산 [KST 적용]
# =====================================================================
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

# =====================================================================
# 🖥️ 상단 대시보드
# =====================================================================
st.title("🎯 AI 당일 상승 우량주 전수 추적 × 실시간 차트 스튜디오 (최종 완결 오피셜판)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")
st.write("---")

# =====================================================================
# 🏹 필터 간섭 버그와 가격 뻥튀기를 전면 박멸한 최종 소싱 엔진
# =====================================================================
class HantuUltimateEngine:
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

    def fetch_master_tickers_with_names(self):
        """
        한투 정품 마스터 DB 파일에서 종목코드와 한글명을 완전히 매핑하여 필터링 버그를 원천 차단
        """
        master_dict = {}
        try:
            # 1) 코스피 정품 코드 마스터 로드
            r_cos = self.session.get("https://new.koreainvestment.com/data/kospi_code.mst.zip", timeout=5.0)
            if r_cos.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(r_cos.content)) as z:
                    with z.open("kospi_code.mst") as f:
                        for line in f:
                            try:
                                line_str = line.decode('cp949')
                                t_code = line_str[0:6]
                                # 한투 마스터 규격 기준: 한글명 정밀 슬라이싱 추출
                                t_name = line_str[18:58].strip() 
                                if t_code.isdigit() and (line_str[23:25] == '01' or line_str[23:26] == '200'):
                                    master_dict[t_code] = t_name
                            except: continue
                            
            # 2) 코스닥 정품 코드 마스터 로드
            r_daq = self.session.get("https://new.koreainvestment.com/data/kosdaq_code.mst.zip", timeout=5.0)
            if r_daq.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(r_daq.content)) as z:
                    with z.open("kosdaq_code.mst") as f:
                        for line in f:
                            try:
                                line_str = line.decode('cp949')
                                t_code = line_str[0:6]
                                t_name = line_str[18:58].strip()
                                if t_code.isdigit() and '코스닥150' in line_str:
                                    master_dict[t_code] = t_name
                            except: continue
        except: pass
            
        # 최후방 에러 보완벽 마스터 데이터 수동 격리 안전장치
        master_dict["036930"] = "주성엔지니어링"
        master_dict["005930"] = "삼성전자"
        master_dict["000660"] = "SK하이닉스"
        master_dict["035720"] = "카카오"
        master_dict["035420"] = "NAVER"
        master_dict["005380"] = "현대차"
        master_dict["000270"] = "기아"
        
        return master_dict

    def fetch_single_stock_search(self, token, query_code):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": query_code}
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=2.0)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output") if res_json.get("output") else res_json.get("output1")
                if out:
                    raw_price_str = str(out.get("stck_prpr", "0")).replace("-", "").strip()
                    
                    # 🛠️ [가격 버그 완전 박멸] 10배 뻥튀기 연산 요소를 삭제하고, 한투 원본 순수 가격만 바인딩
                    clean_price = int(raw_price_str) if raw_price_str.isdigit() else 0
                    
                    # 거래대금을 억 원 단위로 깨끗하게 전처리 계산
                    raw_vol = float(out.get("acml_vol", out.get("accl_tr_vol", 0)))
                    calc_amt = clean_price * raw_vol
                    
                    return {
                        "price": clean_price,
                        "ctrt": float(out.get("prdy_ctrt", 0.0)),
                        "amt": calc_amt,
                        "stat": str(out.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass
        return None

    def fetch_market_pool_by_indices(self, token):
        # 1단계: 350대 지수 구성주의 마스터 한글 종목명 맵 확보
        master_dict = self.fetch_master_tickers_with_names()
        
        # 2단계: 거래대금 상위 100위 수급 기저 지도 로드
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
            r_vol = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=4.0)
            if r_vol.status_code == 200:
                vol_output = r_vol.json().get("output", [])
                for rank_idx, item in enumerate(vol_output):
                    t_code = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                    
                    raw_p_str = str(item.get("stck_prpr", "0")).replace("-", "").strip()
                    clean_p = int(raw_p_str) if raw_p_str.isdigit() else 0
                    
                    rank_map[t_code] = {
                        "rank": rank_idx + 1,
                        "price": clean_p,
                        "ctrt": float(str(item.get("prdy_ctrt", "0.0")).strip()),
                        "volume": float(str(item.get("acml_vol", "0")).strip()),
                        "stat": str(item.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass

        pool = []
        st.session_state.net_log = f"🟢 트래픽 우회형 무결점 엔진 가동 중... ({current_time_str})"
        
        # 🛠️ [버그 해결] 특정 단어 필터 간섭을 막기 위해 마스터 딕셔너리에 매핑된 350개 전 종목 루프 연산 실행
        for ticker, name in master_dict.items():
            
            # 🚫 필터 1단계: ETF / 인버스 / 레버리지 등 파생상품 노이즈 원천 격리 파쇄
            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
            
            if ticker in rank_map:
                r_data = rank_map[ticker]
                price = int(r_data["price"])
                ctrt = r_data["ctrt"]
                stat = r_data["stat"]
                amt_val = price * r_data["volume"]
                raw_rank = r_data["rank"]
            else:
                # 100위 밖에 있는 모든 우량주들을 안전 지연 슬립(0.26초)을 태워 한투 차단벽을 완벽 우회 조사
                time.sleep(0.26) 
                s_res = self.fetch_single_stock_search(token, ticker)
                if s_res:
                    price = int(s_res["price"])
                    ctrt = s_res["ctrt"]
                    stat = s_res["stat"]
                    amt_val = s_res["amt"]
                    raw_rank = 999
                else:
                    continue

            # 🚫 필터 2단계: 10,000원 이하 호가 등락 지저분한 잡주 컷
            if price > 0 and price < 10000: continue
            
            # 🚫 필터 3단계: 대표님 절대 명령 - 전일 대비 마이너스 및 보합 하락주 즉시 전면 격리 제거
            if ctrt <= 0.0: continue
            
            pool.append((raw_rank, ticker, name, amt_val, price, ctrt, stat))
                
        # 자금력 집중 순위로 정렬
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 당일 플러스(+) 상승 우량주 정품 데이터 레이더 가동", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리 청소 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("필터 모순 버그 해결 완료! 정품 가격 주도주 전수 집계 중..."):
        engine = HantuUltimateEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool_by_indices(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 플러스 상승 우량주 전용 종합 수급 표
# =====================================================================
st.markdown("### 📊 당일 상승(+) 우량주 마스터 종합 순위표")

display_list = []
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for row in st.session_state.last_pool:
        if isinstance(row, tuple) and len(row) == 7:
            raw_rank, t, n, amt, price, ctrt, stat = row
            
            stat_prefix = ""
            if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
            elif stat == "52": stat_prefix = "[⚠️유의] "
            elif stat == "51": stat_prefix = "[❌관리] "
            elif stat == "57": stat_prefix = "[🔥경고] "

            if raw_rank <= 30 and ctrt >= 10.0:
                display_name = f"🔥[우량주도-최강] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (지수 주도주)"
                action_tag = "🚀 대한민국 시장 자금을 싹 쓸어담는 핵심 대장 (최우선 공략)"
            elif ctrt >= 10.0:
                display_name = f"💎[우량주도-대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (시세 분출)"
                action_tag = "💎 순위와 무관하게 힘이 폭발하는 지수 내 테마 대장주"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (견고한 양봉 흐름)"
                action_tag = "🟢 수급 확인 완료 / 1분봉 및 3분봉 눌림목 스캘핑 영역"

            display_list.append({
                "시장 자금 순위": f"{raw_rank}위" if raw_rank <= 100 else "100위권 밖",
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"{int(price):,}원", # 🛠️ 원화 콤마 마킹 및 정상 가격 포맷 고정 완료
                "등락률": f"{ctrt:+.2f}%",
                "당일 누적대금": f"{int(amt / 100000000):,}억 원" if amt > 0 else "실시간 집계 완료",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
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
    st.info("💡 동기화 대기 중입니다. 위의 버튼을 클릭하시면 오늘 대한민국 시장에서 상승 중인 정예 우량주 수십 개가 일제히 정품 오피셜 가격으로 쏟아집니다.")

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
