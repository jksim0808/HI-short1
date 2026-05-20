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
st.set_page_config(page_title="한투 거래대금 원본 상위 50 분석기 Pro", layout="wide")

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
st.title("📊 한투 오피셜 거래대금 상위 50 순수 원본 분석기")
st.warning(f"📡 **실시간 라인 진단 모니터:** {st.session_state.net_log}")

st.write("---")

# =====================================================================
# 🏹 필터 제로! 순수 원본 데이터 소싱 엔진
# =====================================================================
class HantuRawEngine:
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

    def fetch_raw_volume_rank(self, token):
        pool = []
        url_vol = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/volume-rank"
        
        headers_vol = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": "FHPST01710000", "custtype": "P"
        }
        # FID_SORT_CLS_CODE : 3 (거래대금 순위 상위)
        params_vol = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "3"
        }
        try:
            r = self.session.get(url_vol, headers=headers_vol, params=params_vol, timeout=5.0)
            if r.status_code == 200:
                res_data = r.json()
                output = res_data.get("output", [])
                
                st.session_state.net_log = f"🟢 한투 원본 데이터 무필터 다이렉트 수신 성공! ({current_time_str} 기준)"
                
                # 상위 50개만 정확하게 슬라이싱 처리
                for item in output[:50]:
                    try:
                        ticker = str(item.get("mksc_shrn_iscd", "")).strip()[-6:]
                        name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                        
                        raw_price = str(item.get("stck_prpr", "0")).replace("-", "").strip()
                        raw_ctrt = str(item.get("prdy_ctrt", "0.0")).strip()
                        raw_volume = str(item.get("acml_vol", "0")).strip()
                        stat_code = str(item.get("iscd_stat_cls_code", "00")).strip()
                        
                        price = float(raw_price) if raw_price.replace('.','',1).isdigit() else 0
                        ctrt = float(raw_ctrt) if raw_ctrt.replace('-','',1).replace('.','',1).isdigit() else 0.0
                        volume = float(raw_volume) if raw_volume.replace('.','',1).isdigit() else 0
                        
                        # 거래대금 연산 (현재가 * 누적거래량)
                        amt_val = price * volume
                        
                        pool.append((ticker, name, amt_val, price, ctrt, stat_code))
                    except:
                        continue
        except Exception as e:
            st.session_state.net_log = f"❌ 데이터 분석 파이프라인 유실 -> {str(e)}"
        return pool

# =====================================================================
# 🖥️ 데이터 수집 제어 버튼
# =====================================================================
cc1, cc2 = st.columns([4, 1])
with cc1:
    btn_fetch = st.button("🔄 실시간 거래대금 상위 50위 원본 패켓 분석 실행", type="primary", use_container_width=True)
with cc2:
    btn_clear = st.button("⚠️ 캐시 강제 초기화", type="secondary", use_container_width=True)

if btn_clear:
    if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    st.session_state.last_pool = []
    st.session_state.net_log = "♻️ 캐시 메모리 완전 소독 완료."
    st.rerun()

if btn_fetch:
    st.session_state.last_pool = []
    with st.spinner("한투 서버 원본 로우(Raw) 데이터 무제한 소싱 중..."):
        engine = HantuRawEngine()
        token = engine.get_token()
        if token:
            st.session_state.last_pool = engine.fetch_raw_volume_rank(token)
            st.rerun()

# =====================================================================
# 📊 [상단 구역] 1위~50위 무필터 순수 출력 격자판
# =====================================================================
st.markdown("### 📊 대한민국 주식시장 실시간 거래대금 랭킹 TOP 50 (날것 그대로)")

display_list = []
if isinstance(st.session_state.last_pool, list) and len(st.session_state.last_pool) > 0:
    for idx, row in enumerate(st.session_state.last_pool):
        if isinstance(row, tuple) and len(row) == 6:
            t, n, amt, price, ctrt, stat = row
            
            # 오피셜 상태 표시용
            stat_desc = "정상"
            if stat in ["58", "59"]: stat_desc = "🚨VI발동"
            elif stat == "52": stat_desc = "⚠️투자유의"
            elif stat == "51": stat_desc = "❌관리종목"
            elif stat == "53": stat_desc = "🔒거래정지"
            elif stat == "57": stat_desc = "🔥투자경고"

            display_list.append({
                "종목코드": t,
                "종목명": n,
                "현재가": f"{int(price):,}원",
                "등락률": f"{ctrt:+.2f}%",
                "실시간 누적 거래대금": f"{int(amt / 100000000):,}억 원",
                "한투 오피셜 상태": stat_desc
            })

df_final = pd.DataFrame(display_list)

selected_ticker = None
selected_name = None

if not df_final.empty:
    df_final.insert(0, "선택", False)
    df_final.insert(1, "오피셜 순위", [f"{i+1}위" for i in range(len(df_final))])
    
    edited_df = st.data_editor(
        df_final,
        use_container_width=True,
        hide_index=True,
        column_config={"선택": st.column_config.CheckboxColumn(required=True)},
        disabled=["오피셜 순위", "종목코드", "종목명", "현재가", "등락률", "실시간 누적 거래대금", "한투 오피셜 상태"],
        height=400
    )
    
    selected_rows = edited_df[edited_df["선택"] == True]
    if not selected_rows.empty:
        selected_ticker = selected_rows.iloc[0]["종목코드"]
        selected_name = selected_rows.iloc[0]["종목명"]
    else:
        selected_ticker = df_final.iloc[0]["종목코드"]
        selected_name = df_final.iloc[0]["종목명"]
else:
    st.info("💡 분석 대기 상태입니다. 위의 버튼을 누르면 한투 원본 데이터 50위 격자판이 즉시 전개됩니다.")

st.write("---")

# =====================================================================
# 📈 [하단 구역] 네이버 실시간 차트 스튜디오
# =====================================================================
st.markdown("### 📈 네이버 페이 증권 실시간 오리지널 차트 연동")

if selected_ticker:
    st.success(f"🔍 현재 분석 차트: **{selected_name} ({selected_ticker})**")
    
    tab1, tab2 = st.tabs(["⚡ 실시간 당일 분봉 차트", "📅 일봉 캔들 차트"])
    time_seed = int(time.time())
    
    with tab1:
        naver_minute_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/area/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_minute_chart, caption=f"[{selected_name}] 분봉 흐름 및 당일 자금 거래량 매칭", use_container_width=True)
        
    with tab2:
        naver_day_chart = f"https://ssl.pstatic.net/imgfinance/chart/item/candle/day/{selected_ticker}.png?v={time_seed}"
        st.image(naver_day_chart, caption=f"[{selected_name}] 일봉 캔들 추세 라인", use_container_width=True)
