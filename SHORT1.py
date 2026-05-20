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
st.set_page_config(page_title="관심종목 수동검색 탑재형 수급 스캐너 Pro", layout="wide")

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
st.title("🎯 AI 오전 3단계 스캐너 × 네이버 차트 (관심종목 수동검색 탑재판)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 10,000원 필터링 및 단독 종목 쿼리 하이브리드 엔진
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
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "3"
        }
        try:
            r = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                st.session_state.net_log = f"🟢 우량주 파이프라인 연동 성공! 10,000원 이하 종목 영구 격리 중 ({current_time_str} 기준)"
                
                for item in output:
                    try:
                        ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        raw_price = item.get("stck_prpr", "0")
                        raw_ctrt = item.get("prdy_ctrt", "0.0")
                        raw_volume = item.get("acml_vol", "0")
                        stat_code = str(item.get("iscd_stat_cls_code", "00")).strip()
                        
                        price = float(raw_price) if str(raw_price).replace('.','',1).isdigit() else 0
                        ctrt = float(raw_ctrt) if str(raw_ctrt).replace('-','',1).replace('.','',1).isdigit() else 0.0
                        volume = float(raw_volume) if str(raw_volume).replace('.','',1).isdigit() else 0
                        
                        amt_val = price * volume
                        
                        if ticker.isdigit() and name and name != "None":
                            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
                            if name.endswith("우") or any(name.endswith(f"우{s}") for s in ["B", "C", " 우선주", "1", "2", "3"]): continue
                            
                            # 순위표 제한 조건: 현재가 10,000원 미만은 탈락
                            if price < 10000: continue
                            
                            pool.append((ticker, name, amt_val, price, ctrt, stat_code))
                    except:
                        continue
        except Exception as e:
            st.session_state.net_log = f"❌ 수급 데이터 통신 유실 에러 -> {str(e)}"
        return pool

    # 🛠️ [수동 검색 전용 단독 수급 파싱 API 엔진 신설]
    def fetch_single_stock_search(self, token, query_code):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": query_code}
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=3.0)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output") if res_json.get("output") else res_json.get("output1")
                if res_json.get("rt_cd") == "0" and out:
                    return {
                        "price": float(out.get("stck_prpr", 0)),
                        "ctrt": float(out.get("prdy_ctrt", 0.0)),
                        "volume": float(out.get("acml_vol", out.get("accl_tr_vol", 0))),
                        "stat": str(out.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass
        return None

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 우량 주도주 새로 불러오기 (10,000원 이상 전용)", type="primary", use_container_width=True)
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
    with st.spinner("10,000원 이상 수급 노다지 종목 스캔 중..."):
        engine = HantuGoldenEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool(token)
            st.rerun()

# =====================================================================
# 🛠️ [신설] 대표님 관심종목 수동 입력 검색창 섹션
# =====================================================================
st.markdown("### 🔍 대표님 관심종목 수동 추적 레이더")
search_query = st.text_input(
    "👉 분석하고 싶으신 종목코드 6자리 숫자를 입력하고 엔터(Enter)를 누르세요. (예: 삼성전자 005930, SK하이닉스 000660)",
    value="",
    max_chars=6
).strip()

manual_stock_data = None
if search_query and search_query.isdigit() and len(search_query) == 6:
    engine = HantuGoldenEngine()
    token = engine.get_token()
    if token:
        s_res = engine.fetch_single_stock_search(token, search_query)
        if s_res:
            manual_stock_data = {
                "code": search_query,
                "price": s_res["price"],
                "ctrt": s_res["ctrt"],
                "amt": s_res["price"] * s_res["volume"],
                "stat": s_res["stat"]
            }

# =====================================================================
# 📊 [상단 구역] 우량주 수급 테이블 배치
# =====================================================================
st.write("---")
st.markdown("### 📊 실시간 우량주 수급 순위표")

display_list = []

# 1) 수동 입력 검색 데이터가 있다면 최상단에 강제로 0순위로 꽂아주기
if manual_stock_data:
    t = manual_stock_data["code"]
    price = manual_stock_data["price"]
    ctrt = manual_stock_data["ctrt"]
    amt = manual_stock_data["amt"]
    stat = manual_stock_data["stat"]
    
    stat_prefix = ""
    if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
    elif stat == "52": stat_prefix = "[⚠️유의] "
    elif stat == "51": stat_prefix = "[❌관리] "
    elif stat == "57": stat_prefix = "[🔥경고] "

    display_list.append({
        "종목코드": t,
        "종목명": f"🎯[대표님 수동지정] {stat_prefix}관심종목({t})",
        "수급 등급 분류": "⭐ 대표님 타깃 종목",
        "현재가": f"{int(price):,}원",
        "등락률": f"{ctrt:+.2f}%",
        "추정 거래대금": f"{int(amt / 100000000):,}억 원",
        "실전 행동 지침": "🔍 수동 락인 완동! 하단 네이버 차트를 즉시 실시간 분석하세요."
    })

# 2) 한국투자증권 엔진 실시간 10,000원 이상 수급 데이터 바인딩
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for idx, row in enumerate(st.session_state.last_pool):
        if isinstance(row, tuple) and len(row) == 6:
            t, n, amt, price, ctrt, stat = row
            current_rank = idx + 1
            
            stat_prefix = ""
            if stat in ["58", "59"]: stat_prefix = "[🚨VI발동] "
            elif stat == "52": stat_prefix = "[⚠️유의] "
            elif stat == "51": stat_prefix = "[❌관리] "
            elif stat == "57": stat_prefix = "[🔥경고] "

            if current_rank <= 20 and ctrt >= 10.0:
                display_name = f"🔥[1순위-최강주도] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (최강 최우선)"
                action_tag = "🚀 시장 돈 싹 쓸어 담는 대장주 (돌파/눌림)"
            elif current_rank > 20 and ctrt >= 10.0:
                display_name = f"💎[2순위-신상대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (신선도 최고)"
                action_tag = "💎 세력이 막 돈 집어넣기 시작한 신상 (강추)"
            elif ctrt >= 1.0 and ctrt < 10.0:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (후발/단기)"
                action_tag = "🟢 수급 확인 완료 / 짧은 스캘핑 타깃"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚪ 3단계: C급 (보합이하)"
                action_tag = "🟡 돈만 들어오고 주가 정체 (매매 보류)"

            display_list.append({
                "종목코드": t,
                "종목명": display_name,
                "수급 등급 분류": rank_grade,
                "현재가": f"{int(price):,}원",
                "등락률": f"{ctrt:+.2f}%",
                "추정 거래대금": f"{int(amt / 100000000):,}억 원",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    df_final.insert(1, "순위", [f"{i+1}위" for i in range(len(df_final))])
    
    # 만약 수동 지정 종목이 들어왔다면 선택 체크박스를 자동으로 활성화 상태로 유도
    if manual_stock_data:
        df_final.loc[0, "선택"] = True

    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["순위", "종목코드", "종목명", "수급 등급 분류", "현재가", "등락률", "추정 거래대금", "실전 행동 지침"],
        height=350
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
    st.info("💡 실시간 주도주 스캐닝 대기 중입니다. 상단 검색창에 코드를 치거나 불러오기 버튼을 누르세요.")

st.write("---")

# =====================================================================
# 📈 [하단 구역] 네이버 실시간 차트 스튜디오
# =====================================================================
st.markdown("### 📈 네이버 증권 실시간 오리지널 차트 패널")

if selected_ticker:
    st.success(f"🔍 현재 네이버 실시간 차트 연동 완료: **{selected_name} ({selected_ticker})**")
    
    tab1, tab2 = st.tabs(["⚡ 단타 필수: 실시간 당일 분봉 차트", "📅 추세 확인: 일봉 차트"])
    time_seed = int(time.time())
    
    with tab1:
        naver_minute_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/area/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_minute_chart, caption=f"[{selected_name}] 네이버 금융 실시간 분봉 및 누적 거래량 흐름", use_container_width=True)
        
    with tab2:
        naver_day_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/candle/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_day_chart, caption=f"[{selected_name}] 네이버 금융 실시간 일봉 캔들 흐름", use_container_width=True)
else:
    st.info("⬆  상단 순위 리스트에서 원하시는 종목의 [선택] 체크박스를 켜시면 하단에 네이버 오리지널 차트가 표출됩니다.")
