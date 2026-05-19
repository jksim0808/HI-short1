import streamlit as st
import pandas as pd
import numpy as np
import requests
import time  # 🎯 트래픽 제한 방어용 시간 제어 모듈 도입
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한투 실전투자 전용 파싱 엔진 (초당 호출 제한 우회 수신기)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_fresh_access_token(self):
        """ 한투 실전 서버 직통 토큰 발급 """
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json"}
            data = {
                "grant_type": "client_credentials", 
                "appkey": self.app_key, 
                "appsecret": self.app_secret
            }
            r = requests.post(url, headers=headers, json=data, timeout=5)
            j = r.json()
            token = j.get("access_token")
            if token:
                return token
        except:
            pass
        return None

    def get_realtime_price(self, ticker, token):
        """ ⚡ 토큰을 매번 발급받지 않고 하나로 재사용하여 트래픽 대폭 절감 """
        if not token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        
        # 주도주 20선 시장 분기
        kosdaq_tickers = ["422340", "043200", "086520", "247540", "068270", "035420", "035720", "000990", "042700", "322890", "108320", "213420", "054780", "018250", "028300"]
        market_div = "Y" if ticker in kosdaq_tickers else "J"
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200", 
            "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": market_div, "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=5)
            if r.status_code == 200:
                res_json = r.json()
                out1 = res_json.get("output1")
                
                if not out1:
                    return None
                    
                if isinstance(out1, list) and len(out1) > 0:
                    out1 = out1[0]
                
                if isinstance(out1, dict) and "stck_prpr" in out1:
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out1.get("stck_prpr"))
                    
                    if close_val > 0:
                        return {
                            "Close": close_val,
                            "High": _clean(out1.get("stck_hgpr")),
                            "Low": _clean(out1.get("stck_lwpr")),
                            "Volume": _clean(out1.get("accl_tr_vol")),
                            "PrdyCtrt": float(str(out1.get("prdy_ctrt", "0.0")).strip())
                        }
        except:
            pass
        return None

# =================================================================
# 🧠 AI 당일 주도주 대상 종목 (정확히 20개 매핑)
# =================================================================
def get_ai_lead_stocks():
    return {
        "005930": "삼성전자", "000660": "SK하이닉스", "422340": "에이직랜드", "043200": "파두",
        "005380": "현대차", "000270": "기아", "086520": "에코프로", "247540": "에코프로비엠", 
        "373220": "LG에너지솔루션", "068270": "셀트리온", "035420": "NAVER", "035720": "카카오", 
        "000990": "DB하이텍", "042700": "한미반도체", "322890": "피엔에이치테크", "108320": "실리콘투", 
        "213420": "덕산네오룩스", "054780": "키이스트", "018250": "에프에스티", "028300": "HLB"
    }

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="AI 주도주 실시간 단타 스캐너", layout="wide")

st.title("🎯 AI 주도주 20선 실시간 단타 스캐너 (⏳ 트래픽 제한 제어판)")
st.caption(f" 가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 초당 2회 안전 분하 호출 모드")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}
if "live_pct_map" not in st.session_state:
    st.session_state.live_pct_map = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks()

col_btn1, col_btn2, col_info = st.columns([1, 1, 3])

if col_btn1.button("⚡ AI 실시간 주도주 수급 동기화", type="primary", use_container_width=True, key="btn_sync_safe"):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 🎯 [트래픽 최적화] 루프 돌기 전 토큰을 딱 1번만 발행하여 한투 카톡 폭탄 및 차단 방지
    with st.spinner("한투 보안 표준 인증 토큰 획득 중..."):
        master_token = api.get_fresh_access_token()
        
    if not master_token:
        st.error("🚨 한투 서버가 인증 토큰 발급 자체를 거부했습니다. Secrets 키 값의 최종 매핑을 재점검해야 합니다.")
    else:
        temp_history = {}
        temp_pct = {}
        success_count = 0
        
        # 프로그레스바 시각화로 진행 상황 표기
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, (ticker, name) in enumerate(master_pool.items()):
            status_text.text(f"🔄 한투 수급 데이터 정밀 동기화 중: {name} ({ticker})")
            
            # 시세 조회 실행
            data = api.get_realtime_price(ticker, master_token)
            
            if data and data["Close"] > 0:
                success_count += 1
                new_row = pd.DataFrame([{
                    "Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])
                }], index=[pd.to_datetime(current_time)])
                
                temp_pct[ticker] = float(data["PrdyCtrt"])
                
                if ticker not in st.session_state.market_history:
                    temp_history[ticker] = new_row
                else:
                    temp_history[ticker] = pd.concat([st.session_state.market_history[ticker], new_row]).tail(20)
            
            # 🎯 [중요] 초당 호출 제한(TPS) 우회를 위한 0.4초 안심 버퍼 슬립 타임 추가
            time.sleep(0.4)
            progress_bar.progress((idx + 1) / len(master_pool))
            
        progress_bar.empty()
        status_text.empty()

        if success_count > 0:
            st.session_state.market_history.update(temp_history)
            st.session_state.live_pct_map.update(temp_pct)
            st.session_state["data_loaded"] = True
            st.success(f"🟢 동기화 완료! 총 {success_count}개 종목의 실전 데이터가 정상 탑재되었습니다.")
        else:
            st.error("🚨 [패킷 차단 지속] 인증은 완벽하나 종목 데이터 파싱이 차단되었습니다. 거래소 장외 시간이거나 한투 API 계정의 데이터 피드 승인이 일시 유보 상태일 수 있습니다.")

if col_btn2.button("🧹 단타 캐시 리셋", use_container_width=True, key="btn_reset_safe"):
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    if "data_loaded" in st.session_state: del st.session_state["data_loaded"]
    st.rerun()

col_info.markdown("💡 **수급 연동 기술 안내:** 한투의 초당 2건 제한 규격(TPS)을 준수하기 위해 종목별 0.4초 레이턴시 버퍼가 적용 중입니다.")

st.markdown("---")

# =================================================================
# ⚙️ 주도주 랭킹 연산 및 화면 렌더링 프레임워크
# =================================================================
if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    
    for ticker, df in st.session_state.market_history.items():
        if df.empty: continue
        latest = df.iloc[-1]
        
        growth_rate = float(st.session_state.live_pct_map.get(ticker, 0.0))
        vwap_val = float(df["Close"].mean())
        
        ranking_list.append({
            "code": str(ticker),
            "name": str(master_pool.get(ticker)),
            "price": int(latest["Close"]),
            "vwap": int(vwap_val),
            "growth": growth_rate
        })
    
    ranking_df = pd.DataFrame(ranking_list)
    
    if not ranking_df.empty:
        ranking_df = ranking_df.sort_values(by="growth", ascending=False).reset_index(drop=True)
        
        st.subheader("🔥 AI 선정 실시간 단타 주도주 순위 Top 20")
        
        display_rows = []
        for rank, row in enumerate(ranking_df.itertuples(), 1):
            display_rows.append({
                "순위": f"{rank}위",
                "종목코드": row.code,
                "종목명": row.name,
                "현재가": f"{row.price:,} 원",
                "수급평균선": f"{row.vwap:,} 원",
                "당일 등락률": f"{row.growth:+.2f}%",
                "단타 시그널": "🔥 초강력 매수" if row.growth > 3.0 else ("🚨 매도 청산" if row.growth < -1.0 else "🟢 관망 진입")
            })
        
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("🎯 종목별 실시간 수급 레이더 (바둑판 모니터)")
        
        cols = st.columns(4)
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 4]
            with target_col:
                sig_text = "🔥 매수추천" if row.growth > 3.0 else "🟢 관망유지"
                st.markdown(f"### {row.name}")
                st.markdown(f"**코드:** `{row.code}` | **등락:** `{row.growth:+.2f}%`")
                st.metric(label="현재 가격", value=f"{row.price:,}원", delta=f"평균차: {int(row.price - row.vwap):+}원")
                st.caption(f"⚡ 시그널: `{sig_text}`")
                st.markdown("---")
else:
    st.info("⏳ 데이터 트래픽 우회 파이프라인 대기 중. 상단의 동기화 버튼을 클릭해 주십시오.")
