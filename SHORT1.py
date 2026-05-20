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
st.set_page_config(page_title="플러스 상승 우량주 마스터 스캐너", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 파이프라인 대기 중..."

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
st.title("🎯 코스피 200 × 코스닥 150 플러스 상승 종목 전용 스캐너")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 마이너스 전면 파쇄형 정품 파일 마스터 엔진
# =====================================================================
class HantuPlusEngine:
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

    def fetch_master_tickers_via_file(self):
        tickers = []
        try:
            r_cos = self.session.get("https://new.koreainvestment.com/data/kospi_code.mst.zip", timeout=5.0)
            if r_cos.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(r_cos.content)) as z:
                    with z.open("kospi_code.mst") as f:
                        for line in f:
                            try:
                                line_str = line.decode('cp949')
                                t_code = line_str[0:6]
                                if t_code.isdigit() and (line_str[23:25] == '01' or line_str[23:26] == '200'):
                                    tickers.append(t_code)
                            except: continue
                            
            r_daq = self.session.get("https://new.koreainvestment.com/data/kosdaq_code.mst.zip", timeout=5.0)
            if r_daq.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(r_daq.content)) as z:
                    with z.open("kosdaq_code.mst") as f:
                        for line in f:
                            try:
                                line_str = line.decode('cp949')
                                t_code = line_str[0:6]
                                if t_code.isdigit() and '코스닥150' in line_str:
                                    tickers.append(t_code)
                            except: continue
        except: pass
            
        backup_essential = ["036930", "005930", "000660", "035720", "035420", "005380", "000270", "068270", "005490", "247540", "096770"]
        total_res = list(set(tickers + backup_essential))
        return total_res

    def fetch_market_pool_by_indices(self, token):
        total_tickers = self.fetch_master_tickers_via_file()
        st.session_state.net_log = f"🟢 정품 DB 동기화 완료! 우량주 {len(total_tickers)}개 스캔 중 ({current_time_str} 기준)"
        
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
        for ticker in total_tickers:
            if ticker in rank_map:
                r_data = rank_map[ticker]
                price = r_data["price"]
                name = r_data["name"]
                ctrt = r_data["ctrt"]
                stat = r_data["stat"]
                amt_val = price * r_data["volume"]
                raw_rank = r_data["rank"]
            else:
                if ticker == "036930": name = "주성엔지니어링"
                elif ticker == "005930": name = "삼성전자"
                elif ticker == "000660": name = "SK하이닉스"
                else: name = f"우량종목({ticker})"
                price, ctrt, amt_val, raw_rank, stat = 0, 0.0, 0, 999, "00"

            # 🚫 대표님 필터 1단계: 파생상품/인버스 노이즈 소멸
            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
            
            # 🚫 대표님 필터 2단계: 10,000원 이하 동전주 커트
            if price > 0 and price < 10000: continue
            
            # 🛠️ [핵심 개조] 등락률이 0% 이하(마이너스 및 보합)인 하락 종목은 단타 대상에서 무조건 영구 제외!
            if ctrt <= 0.0: continue
            
            pool.append((raw_rank, ticker, name, amt_val, price, ctrt, stat))
                
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 플러스(+) 상승 우량주 라인업 동기화", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 시스템 캐시 청소 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("하락주 전면 격리 파쇄! 실시간 양봉 주도주 집계 중..."):
        engine = HantuPlusEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool_by_indices(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 플러스 상승 우량주 전용 통합 수급 표
# =====================================================================
st.markdown("### 📊 실시간 양봉(+) 우량주 수급 순위표")

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
                action_tag = "🚀 대한민국 시장 돈을 싹 쓸어담는 핵심 대장 (최우선 공략)"
            elif ctrt >= 10.0:
                display_name = f"💎[우량주도-대장] {stat_prefix}{n}"
                rank_grade = "🔥 1단계: A급 (시세 분출)"
                action_tag = "💎 순위와 무관하게 힘이 폭발하는 지수 내 테마 대장주"
            else:
                display_name = f"{stat_prefix}{n}"
                rank_grade = "⚡ 2단계: B급 (견고한 흐름)"
                action_tag = "🟢 수급 유입 완료 / 1분봉 눌림목 스캘핑"

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
    
    # 주성엔지니어링이 상승 종목 리스트에 포착되면 즉시 자동 체크포커싱
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
    st.info("💡 스캐너 동기화 완료 대기 중. 위의 버튼을 누르시면 당일 빨간불 우량 주도주만 전개됩니다.")

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
