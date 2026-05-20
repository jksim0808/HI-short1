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
st.set_page_config(page_title="단타 주도주 전수 마스터 스캐너", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 실시간 파이프라인 대기 중..."

# =====================================================================
# ⏳ 타임 제어 연산 [KST 적용]
# =====================================================================
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

# =====================================================================
# 🖥️ 상단 대시보드 및 실시간 진단 모니터
# =====================================================================
st.title("🎯 AI 단타 주도주 × 네이버 실시간 차트 마스터 스캐너 (전수 추적 완결판)")

st.markdown("""
> 💡 **실전 단타 4대 판독 오피셜 공식**
> 1. **거래대금**: 당일 누적 최소 500억 이상 유입 및 분당 뭉칫돈 스캔
> 2. **상승탄력**: 시가 갭 +15% 이상 갭부담 종목 제외, 당일 등락률 +10% 이상 집중
> 3. **분봉타점**: 장대양봉 추격 금지 ➔ 거래량 급감하는 '첫 번째 음봉 눌림목' 공략
> 4. **테마/명분**: 업종별 커플링(동조화) 확인 및 특징주 뉴스 결합 종목 우선
""")

st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")
st.write("---")

# =====================================================================
# 🏹 API 차단을 무력화하고 전수 조사를 강제하는 주도주 매칭 엔진
# =====================================================================
class HantuPlusEnginePerfect:
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
            # 1) 코스피 200 구성 종목 다운로드 및 추출
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
                            
            # 2) 코스닥 150 구성 종목 다운로드 및 추출
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
            
        backup_essential = ["036930", "005930", "000660", "035720", "035420", "005380", "000270"]
        total_res = list(set(tickers + backup_essential))
        return total_res

    def fetch_single_stock_search(self, token, query_code):
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": query_code}
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=2.5)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output") if res_json.get("output") else res_json.get("output1")
                if out:
                    raw_p = str(out.get("stck_prpr", 0)).replace("-", "").strip()
                    # 실시간 한글 종목명 마스터에서 실시간 매핑용 한글명도 함께 추출
                    return {
                        "name": str(out.get("hts_kor_isnm", "")).strip(),
                        "price": float(raw_p) if raw_p.replace('.','',1).isdigit() else 0,
                        "ctrt": float(out.get("prdy_ctrt", 0.0)),
                        "volume": float(out.get("acml_vol", out.get("accl_tr_vol", 0))),
                        "stat": str(out.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass
        return None

    def fetch_market_pool_by_indices(self, token):
        # 🛠️ [개조 핵심] 압축 서브풀을 전면 철폐하고 지수 구성 종목 전체를 풀 세팅
        total_tickers = self.fetch_master_tickers_via_file()
        st.session_state.net_log = f"🟢 양대지수 정예 마스터 전수 락인 성공! {len(total_tickers)}개 전수 검사 중 ({current_time_str})"
        
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
        
        # 🛠️ 압축 조건 필터를 완전히 걷어내고 350개 전체 구성 종목을 대상으로 1대1 무결점 실시간 계측 회로 전개
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
                # 거래대금 100위권 밖에 숨어있는 주성엔지니어링 등을 위해 실시간 단독 조회 파이프를 전수 가동
                s_res = self.fetch_single_stock_search(token, ticker)
                if s_res:
                    price = s_res["price"]
                    ctrt = s_res["ctrt"]
                    stat = s_res["stat"]
                    amt_val = price * s_res["volume"]
                    raw_rank = 999
                    
                    # 한투 서버 오피셜 한글명이 있으면 매핑하고 없으면 수동 보완책 적용
                    if s_res["name"]:
                        name = s_res["name"]
                    else:
                        if ticker == "036930": name = "주성엔지니어링"
                        elif ticker == "005930": name = "삼성전자"
                        elif ticker == "000660": name = "SK하이닉스"
                        else: name = f"우량종목({ticker})"
                else:
                    continue

            # 🚫 필터 1단계: ETF / 인버스 등 파생상품 소음 완전 제거
            if any(k in name for k in ["스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KOSEF"]): continue
            
            # 🚫 필터 2단계: 10,000원 이하 가벼운 잡주/동전주 자동 격리
            if price > 0 and price < 10000: continue
            
            # 🚫 필터 3단계: 🛠️ 대표님 고정 명령 - 마이너스(-) 및 보합 하락 종목은 그 자리에서 즉시 완전 증발 처리!
            if ctrt <= 0.0: continue
            
            pool.append((raw_rank, ticker, name, amt_val, price, ctrt, stat))
                
        # 자금 유입 활성 순위로 정렬 (100위권 안 주도주가 위로 먼저 올라오고, 숨어있는 양봉 알짜주가 아래 배치됨)
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 플러스(+) 상승 우량 주도주 전수 추적 가동 (주성·대장주 100% 락인)", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 시스템 캐시 청소 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("350개 우량 지수 구성원 실시간 전수 조회 중... 하락주는 자동 파쇄됩니다."):
        engine = HantuPlusEnginePerfect()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_market_pool_by_indices(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 플러스 상승 우량주 전용 통합 수급 표
# =====================================================================
st.markdown("### 📊 실시간 양봉(+) 우량주 통합 수급 순위표")

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
                "당일 누적대금": f"{int(amt / 100000000):,}억 원" if amt > 0 else "실시간 계측 완료",
                "실전 행동 지침": action_tag
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    
    # 주성엔지니어링이 양봉 종목 리스트에 포착되면 첫 화면에서 즉시 체크박스 락인 활성화
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
    st.info("💡 오늘 양대지수 보통주 중 플러스(+) 상승 중인 종목이 없거나 동기화 대기 중입니다. 상단 버튼을 눌러 스캐너를 가동하세요.")

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
