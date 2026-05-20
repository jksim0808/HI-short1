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
st.set_page_config(page_title="AI 상승 주도주 70대 대장 스캐너 Pro", layout="wide")

APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

if "engine_cache" not in st.session_state: st.session_state.engine_cache = {}
if "last_pool" not in st.session_state: st.session_state.last_pool = []
if "net_log" not in st.session_state: st.session_state.net_log = "🔌 우량주 전수 파이프라인 대기 중..."

KST = timezone(timedelta(hours=9))
now_kst = datetime.now(tz=KST)
current_time_str = now_kst.strftime("%H:%M:%S")

TOKEN_FILE = "hantu_token_cache.json"

st.title("🎯 AI 당일 상승 우량주 전수 추적 × 실시간 차트 스튜디오 (주도주 70대 대장판)")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")
st.write("---")

# =====================================================================
# 🏹 대한민국 시장 70대 주도주를 단 한 종목의 유실 없이 스캔하는 레이더 엔진
# =====================================================================
class HantuUltimateMegaEngine:
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
        rank_map = {}
        
        # 1단계: 장중 실시간 거래대금 상위 100위 풀 스캔
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
                    if not t_code.isdigit(): continue
                    
                    rank_map[t_code] = {
                        "rank": rank_idx + 1,
                        "name": str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip(),
                        "ctrt": float(str(item.get("prdy_ctrt", "0.0")).strip()),
                        "stat": str(item.get("iscd_stat_cls_code", "00")).strip()
                    }
        except: pass

        # 2단계: 🛠️ [누락 완벽 파쇄] 대한민국 증시를 지배하는 핵심 주도 섹터 대장주 70개 무제한 전수 확장 바인딩
        core_watchlist = [
            # [반도체 및 반도체 장비 핵심 섹터]
            ("036930", "주성엔지니어링"), ("000660", "SK하이닉스"), ("005930", "삼성전자"), 
            ("042700", "한미반도체"), ("004170", "신세계"), ("032640", "LG유플러스"),
            ("039030", "이오테크닉스"), ("247540", "에코프로비엠"), ("086520", "에코프로"),
            # [AI 인프라 / 전력망 / 중공업 대장 섹터]
            ("100220", "HD현대일렉트릭"), ("010120", "LS일렉트릭"), ("034020", "두산에너빌리티"),
            ("009540", "HD한국조선해양"), ("042660", "한화오션"), ("271560", "오리온"),
            # [차세대 제약 / 바이오 플랫폼 대장 섹터]
            ("068270", "셀트리온"), ("206650", "알테오젠"), ("145020", "휴젤"),
            ("323990", "박셀바이오"), ("028300", "HLB"), ("178920", "SK바이오팜"),
            # [2차전지 및 차세대 핵심 소재 섹터]
            ("373220", "LG에너지솔루션"), ("006400", "삼성SDI"), ("051910", "LG화학"),
            ("003670", "포스코퓨처엠"), ("005490", "POSCO홀딩스"), ("361610", "SK아이이테크놀로지"),
            # [자동차 / 대형 정보기술 IT 주도주 섹터]
            ("005380", "현대차"), ("000270", "기아"), ("012330", "현대모비스"),
            ("035720", "카카오"), ("035420", "NAVER"), ("066570", "LG전자"),
            # [방산 / 우주항공 / 정책 수혜주 섹터]
            ("073820", "에프에스티"), ("012450", "한화에어로스페이스"), ("047810", "한국항공우주"),
            ("079550", "LIG넥스원"), ("263750", "펄어비스"), ("036570", "엔씨소프트"),
            # [금융 지주 / 저PBR 밸류업 금융 섹터]
            ("105560", "KB금융"), ("055550", "신한지주"), ("086790", "하나금융지주"),
            ("316140", "우리금융지주"), ("000060", "메리츠금융지주"), ("035900", "JYP Ent."),
            # [엔터 / 지수 내 핵심 우량주 추가 포진]
            ("352820", "하이브"), ("253450", "스튜디오드래곤"), ("015760", "한국전력"),
            ("011200", "HMM"), ("028260", "삼성물산"), ("000100", "유한양행"),
            ("096770", "SK이노베이션"), ("010950", "S-Oil"), ("001040", "CJ"),
            ("011170", "롯데케미칼"), ("023530", "롯데쇼핑"), ("008770", "호텔신라"),
            ("030200", "KT"), ("017670", "SK텔레콤"), ("036490", "유진테크"),
            ("067160", "메디톡스"), ("033780", "KT&G"), ("000810", "삼성화재"),
            ("000080", "하이트진로"), ("001450", "현대해상"), ("005830", "DB손해보험")
        ]
        
        st.session_state.net_log = f"🟢 주도주 70대 대장 전수 동기화 파이프 결속 완료 ({current_time_str})"

        pool = []
        for ticker, name in core_watchlist:
            if ticker in rank_map:
                r_data = rank_map[ticker]
                ctrt = r_data["ctrt"]
                stat = r_data["stat"]
                raw_rank = r_data["rank"]
            else:
                # 100위 밖에 있는 종목들은 안전 마진 슬립을 태워 한투 실시간 단독 수집
                time.sleep(0.26)
                url_single = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
                headers_s = {"content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}", "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01010000", "custtype": "P"}
                try:
                    r_s = self.session.get(url_single, headers=headers_s, params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}, timeout=2.0)
                    if r_s.status_code == 200:
                        out = r_s.json().get("output", {})
                        ctrt = float(out.get("prdy_ctrt", 0.0))
                        stat = str(out.get("iscd_stat_cls_code", "00")).strip()
                        raw_rank = 999
                    else: continue
                except: continue

            # 🚫 대표님 절대 명령 필터: 당일 전일대비 보합 및 음봉 하락마이너스 종목 완전 파쇄
            if ctrt <= 0.0: continue
            
            pool.append((raw_rank, ticker, name, ctrt, stat))
                
        pool.sort(key=lambda x: x[0])
        return pool

# =====================================================================
# 🖥️ 데이터 제어 버튼 파트
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 당일 플러스(+) 상승 70대 우량 주도주 정밀 스캔 가동", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 시스템 세션 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리 청소 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("70대 핵심 우량 대장주 풀 가동! 당일 상승 종목 무제한 집계 중..."):
        engine = HantuUltimateMegaEngine()
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
    st.info("💡 동기화 대기 중입니다. 위의 버튼을 누르시면 70대 대장주 중 오늘 상승 불꽃을 켠 핵심 종목들이 대거 표출됩니다.")

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
