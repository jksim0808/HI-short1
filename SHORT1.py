import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한투 실전투자 전용 파싱 엔진 (가상 데이터 완전 제거 / 토큰 강제 갱신)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        # 🎯 오직 한투 실전투자 운영 서버 주소만 사용
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    def get_fresh_access_token(self):
        """ 🎯 [핵심 수정] 캐시된 토큰을 쓰지 않고, 호출할 때마다 한투 서버에서 새 토큰을 즉시 강제 발급 """
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json; charset=UTF-8", "User-Agent": self.user_agent}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            
            r = requests.post(url, headers=headers, json=data, timeout=5)
            j = r.json()
            token = j.get("access_token")
            if token:
                return token
        except:
            pass
        return None

    def get_realtime_price(self, ticker):
        # 1. 매 호출마다 무조건 싱싱한 토큰 수령
        token = self.get_fresh_access_token()
        if not token:
            return None  # 가상 데이터 반환 없이 통신 실패 처리
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        
        # 코스닥 및 주요 종목 구분용 딕셔너리 정밀 세팅
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
            r = requests.get(url, headers=headers, params=params, timeout=4)
            if r.status_code == 200:
                res_json = r.json()
                out1 = res_json.get("output1", {})
                
                if isinstance(out1, list) and len(out1) > 0: 
                    out1 = out1[0]
                
                if isinstance(out1, dict) and "stck_prpr" in out1:
                    def _clean(val):
                        if not val: return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out1.get("stck_prpr"))
                    
                    # 🎯 오직 실전 한투 원본 데이터 세트만 딕셔너리로 빌드
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
        return None  # 통신 끊기면 가상 가짜값 없이 철저히 정지

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

st.title("🎯 AI 주도주 20선 실시간 단타 스캐너 (🔒 실전서버 100% 직통판)")
st.caption(f" 가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 한투 원본 패킷 강제 수신 시스템")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}
if "live_pct_map" not in st.session_state:
    st.session_state.live_pct_map = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks()

col_btn1, col_btn2, col_info = st.columns([1, 1, 3])

if col_btn1.button("⚡ AI 실시간 주도주 수급 동기화", type="primary", use_container_width=True, key="btn_sync_pure_real"):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    temp_history = {}
    temp_pct = {}
    success_count = 0
    
    for ticker, name in master_pool.items():
        data = api.get_realtime_price(ticker)
        
        # 🎯 가상 데이터 우회 없이, 오직 한투 정식 데이터만 허용
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

    # 🎯 20개 종목 중 실제 한투 데이터가 단 1개라도 받아졌을 때만 갱신 작동
    if success_count > 0:
        st.session_state.market_history.update(temp_history)
        st.session_state.live_pct_map.update(temp_pct)
        st.session_state["data_loaded"] = True
    else:
        st.error("🚨 [인증 실패] 한투 서버가 실시간 토큰 발급을 거부했습니다. Streamlit Secrets에 저장된 AppKey와 Secret 값에 공백이 있는지 반드시 확인이 필요합니다.")

if col_btn2.button("🧹 단타 캐시 리셋", use_container_width=True, key="btn_reset_pure_real"):
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    if "data_loaded" in st.session_state: del st.session_state["data_loaded"]
    st.rerun()

col_info.markdown("⚠️ **경고:** 본 시스템은 가상 데이터를 완벽 차단했습니다. 한투 실전 API 통신이 성공해야만 화면이 갱신됩니다.")

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
    st.info("⚡ 한투 실전 서버 접속 준비 완료. 상단의 **'⚡ AI 실시간 주도주 수급 동기화'** 버튼을 클릭하시면 100% 원본 데이터 연동이 시작됩니다.")
