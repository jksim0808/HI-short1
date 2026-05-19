import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

# =================================================================
# 🏦 한투 실전투자 전용 파싱 엔진 (10선 트래픽 최적화 모델)
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
        if not token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        
        # 압축 10선 코스닥 종목 타겟팅 (에이직랜드, 파두, 한미반도체, 에코프로비엠)
        kosdaq_tickers = ["422340", "043200", "042700", "247540"]
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
# 🧠 AI 주도주 정예 압축 10선 (반도체/NPU/로보틱스/미래모빌리티 핵심주)
# =================================================================
def get_ai_lead_stocks():
    return {
        "005930": "삼성전자",       # 레거시 반도체 및 파운드리 축
        "000660": "SK하이닉스",     # HBM 주도권 대형주
        "422340": "에이직랜드",     # AI 반도체 디자인하우스 핵심 (NPU 연동)
        "043200": "파두",          # 차세대 SSD 컨트롤러 및 AI 데이터센터 수혜
        "042700": "한미반도체",     # HBM 필수 공정 TC 본더 독점주
        "005380": "현대차",         # PBV 및 미래형 미래 모빌리티 대장주
        "000270": "기아",           # PBV(PV5) 플랫폼 다변화 주도주
        "247540": "에코프로비엠",   # 2차전지/소재 대표 수급주
        "373220": "LG에너지솔루션", # 배터리/스마트팩토리 인프라
        "068270": "셀트리온"        # 바이오/대형 수급 분산 방어주
    }

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="AI 주도주 실시간 단타 스캐너", layout="wide")

st.title("🎯 AI 정예 주도주 10선 실시간 단타 스캐너 (⚡ 고속 압축판)")
st.caption(f" 가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 10대 정예 종목 고속 스캔 엔진")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}
if "live_pct_map" not in st.session_state:
    st.session_state.live_pct_map = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks()

col_btn1, col_btn2, col_info = st.columns([1, 1, 3])

if col_btn1.button("⚡ AI 정예 10선 수급 동기화", type="primary", use_container_width=True, key="btn_sync_compressed"):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("한투 보안 표준 인증 토큰 획득 중..."):
        master_token = api.get_fresh_access_token()
        
    if not master_token:
        st.error("🚨 한투 서버가 인증 토큰 발급을 거부했습니다. Streamlit Secrets 설정을 재점검하십시오.")
    else:
        temp_history = {}
        temp_pct = {}
        success_count = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, (ticker, name) in enumerate(master_pool.items()):
            status_text.text(f"🔄 고속 패킷 수신 중: {name} ({ticker})")
            
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
            
            # 🎯 종목 축소로 딜레이를 0.35초로 최적화 단축하여 3초 만에 전체 스캔 완료
            time.sleep(0.35)
            progress_bar.progress((idx + 1) / len(master_pool))
            
        progress_bar.empty()
        status_text.empty()

        if success_count > 0:
            st.session_state.market_history.update(temp_history)
            st.session_state.live_pct_map.update(temp_pct)
            st.session_state["data_loaded"] = True
            st.success(f"🟢 동기화 완료! 정예 10선 중 {success_count}개 종목 원본 수신 성공.")
        else:
            st.error("🚨 한투 서버가 패킷 반환을 거부했습니다. 장중 시간 여부 및 계좌 상태를 확인해 주십시오.")

if col_btn2.button("🧹 단타 캐시 리셋", use_container_width=True, key="btn_reset_compressed"):
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    if "data_loaded" in st.session_state: del st.session_state["data_loaded"]
    st.rerun()

col_info.markdown("💡 **운용 전략:** 종목이 10개로 정제되어 데이터 연산 부하가 절반으로 감소했습니다. 단타 타점 회전율이 대폭 상승합니다.")

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
        
        st.subheader("🔥 AI 선정 정예 주도주 순위 Top 10")
        
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
        st.subheader("🎯 압축 10선 실시간 수급 보드")
        
        # 10개 종목에 딱 맞게 2줄(구조 최적화) 배열 구성
        cols = st.columns(5)
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 5]
            with target_col:
                sig_text = "🔥 매수추천" if row.growth > 3.0 else "🟢 관망유지"
                st.markdown(f"### {row.name}")
                st.markdown(f"**코드:** `{row.code}` | **등락:** `{row.growth:+.2f}%`")
                st.metric(label="현재 가격", value=f"{row.price:,}원", delta=f"평균차: {int(row.price - row.vwap):+}원")
                st.caption(f"⚡ 시그널: `{sig_text}`")
                st.markdown("---")
else:
    st.info("⏳ 정예 10선 시스템 대기 중입니다. 상단의 동기화 버튼을 클릭해 주십시오.")
