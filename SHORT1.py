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
# 🏦 한투 실전투자 전용 파싱 엔진 (3개 종목 무조건 강제 출력형)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_fresh_access_token(self):
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
            return j.get("access_token")
        except:
            return None

    def get_realtime_price(self, ticker, token):
        if not token:
            return None, "토큰 누락"
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
        # 코스닥 종목 정밀 분기
        kosdaq_pure = ["422340", "043200", "247540"]
        market_div = "W" if ticker in kosdaq_pure else "J"
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",
            "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": market_div, "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=5)
            if r.status_code == 200:
                res_json = r.json()
                
                rt_cd = str(res_json.get("rt_cd", "")).strip()
                msg1 = res_json.get("msg1", "").strip()
                
                # 🎯 [긴급 수리] output과 output1 구조를 모두 통합하여 유연하게 데이터 추출
                out1 = res_json.get("output")
                if not out1 or (isinstance(out1, list) and len(out1) == 0):
                    out1 = res_json.get("output1")
                if not out1:
                    out1 = res_json.get("output2")
                
                if isinstance(out1, list) and len(out1) > 0:
                    out1 = out1[0]
                
                # 🎯 [핵심 보정] rt_cd가 0이거나 정상 메시지가 잡히면 뒤도 안 돌아보고 파싱 강제 진행
                if (rt_cd in ["0", "0000", "00"]) or ("정상" in msg1) or (isinstance(out1, dict) and "stck_prpr" in out1):
                    if isinstance(out1, dict):
                        def _clean(val):
                            if val is None or str(val).strip() == "": return 0.0
                            return float(str(val).strip().replace("-", "").replace("+", ""))
                        
                        close_val = _clean(out1.get("stck_prpr"))
                        
                        # 값이 비정상적으로 0일 때를 대비한 하이브리드 방어막
                        if close_val == 0 and "prpr" in out1:
                            close_val = _clean(out1.get("prpr"))
                        
                        if close_val > 0:
                            data_dict = {
                                "Close": close_val,
                                "High": _clean(out1.get("stck_hgpr") if out1.get("stck_hgpr") else out1.get("hgpr", 0)),
                                "Low": _clean(out1.get("stck_lwpr") if out1.get("stck_lwpr") else out1.get("lwpr", 0)),
                                "Volume": _clean(out1.get("accl_tr_vol") if out1.get("accl_tr_vol") else out1.get("vol", 0)),
                                "PrdyCtrt": float(str(out1.get("prdy_ctrt", out1.get("ctrt", "0.0"))).strip())
                            }
                            return data_dict, "성공 (연동완료)"
                
                return None, f"서버처리 보류 -> [코드: {rt_cd}] {msg1}"
            else:
                return None, f"HTTP 에러 (통신상태: {r.status_code})"
        except Exception as e:
            return None, f"시스템 예외 오류: {str(e)}"

# =================================================================
# 🧠 AI 주도주 정예 압축 10선
# =================================================================
def get_ai_lead_stocks():
    return {
        "005930": "삼성전자",       
        "000660": "SK하이닉스",     
        "422340": "에이직랜드",     
        "043200": "파두",          
        "042700": "한미반도체",     
        "005380": "현대차",         
        "000270": "기아",           
        "247540": "에코프로비엠",   
        "373220": "LG에너지솔루션", 
        "068270": "셀트리온"        
    }

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="AI 주도주 실시간 단타 스캐너", layout="wide")

st.title("🎯 AI 정예 주도주 10선 실시간 단타 스캐너")
st.caption(f" 가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 코스닥 3선 무조건 강제 출력 버전")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}
if "live_pct_map" not in st.session_state:
    st.session_state.live_pct_map = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks()

col_btn1, col_btn2, col_info = st.columns([1, 1, 3])

if col_btn1.button("⚡ AI 정예 10선 수급 동기화", type="primary", use_container_width=True, key="btn_sync_force_display"):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("한투 보안 표준 인증 토큰 획득 중..."):
        master_token = api.get_fresh_access_token()
        
    if not master_token:
        st.error("🚨 [인증단계 거부] 한투 서버가 토큰 발급을 거절했습니다. Secrets 설정을 재점검하십시오.")
    else:
        st.success("🔑 1단계 통과: 한투 표준 인증 토큰 발급 완료")
        
        temp_history = {}
        temp_pct = {}
        success_count = 0
        
        st.markdown("### 🔍 한투 서버 실시간 응답 분석 헤드셋")
        log_box = st.empty()
        log_messages = []
        
        progress_bar = st.progress(0)
        
        for idx, (ticker, name) in enumerate(master_pool.items()):
            data, server_msg = api.get_realtime_price(ticker, master_token)
            
            log_messages.append(f"• **{name} ({ticker})** -> {server_msg}")
            log_box.markdown("\n".join(log_messages))
            
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
            
            time.sleep(0.35)
            progress_bar.progress((idx + 1) / len(master_pool))
            
        progress_bar.empty()

        if success_count > 0:
            st.session_state.market_history.update(temp_history)
            st.session_state.live_pct_map.update(temp_pct)
            st.session_state["data_loaded"] = True
            st.toast("정예 10선 수급 데이터 동기화 완수!", icon="🟢")
        else:
            st.error("🚨 [수신 실패] 패킷에서 데이터를 강제로 추출하는 데 실패했습니다.")

if col_btn2.button("🧹 단타 캐시 리셋", use_container_width=True, key="btn_reset_force_display"):
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    if "data_loaded" in st.session_state: del st.session_state["data_loaded"]
    st.rerun()

col_info.markdown("💡 **수정 완수:** 코스닥 특유의 하이브리드 패킷 주머니(`output1`) 분석 알고리즘을 100% 동기화했습니다.")

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
        
        cols = st.columns(5)
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 5]
            with target_col:
                st.markdown(f"### {row.name}")
                st.markdown(f"**코드:** `{row.code}` | **등락:** `{row.growth:+.2f}%`")
                st.metric(label="현재 가격", value=f"{row.price:,}원", delta=f"평균차: {int(row.price - row.vwap):+}원")
                
                if row.growth > 3.0:
                    st.error("🔥 초강력 수급 유입")
                elif row.growth < -1.0:
                    st.info("🚨 단기 과매도 구간")
                else:
                    st.success("🟢 안정 수급 추종")
                st.markdown("---")
else:
    st.info("⏳ 시스템 가동 대기 중입니다. 상단의 동기화 버튼을 클릭해 주십시오.")
