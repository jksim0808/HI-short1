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
# 🏦 한투 실전투자 전용 파싱 엔진
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
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",
            "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=5)
            if r.status_code == 200:
                res_json = r.json()
                out1 = res_json.get("output")
                
                if isinstance(out1, list) and len(out1) > 0:
                    out1 = out1[0]
                elif not out1 or not isinstance(out1, dict):
                    out1 = res_json.get("output1", {})
                    if isinstance(out1, list) and len(out1) > 0:
                        out1 = out1[0]
                
                if isinstance(out1, dict) and ("stck_prpr" in out1 or "prpr" in out1):
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out1.get("stck_prpr"))
                    if close_val == 0:
                        close_val = _clean(out1.get("prpr"))
                    
                    if close_val > 0:
                        data_dict = {
                            "Close": close_val,
                            "High": _clean(out1.get("stck_hgpr") if out1.get("stck_hgpr") else out1.get("hgpr", 0)),
                            "Low": _clean(out1.get("stck_lwpr") if out1.get("stck_lwpr") else out1.get("lwpr", 0)),
                            "Volume": _clean(out1.get("accl_tr_vol") if out1.get("accl_tr_vol") else out1.get("vol", 0)),
                            "PrdyCtrt": float(str(out1.get("prdy_ctrt" if out1.get("prdy_ctrt") else "ctrt", "0.0")).strip())
                        }
                        return data_dict, "성공"
                
                return None, "패킷 공백"
            else:
                return None, f"HTTP {r.status_code}"
        except Exception as e:
            return None, f"예외: {str(e)}"

# =================================================================
# 🧠 AI 주도주 대량 거래 수급 정예 20선
# =================================================================
def get_ai_lead_stocks_20():
    return {
        "005930": "삼성전자", "000660": "SK하이닉스", "042700": "한미반도체", "422340": "에이직랜드", "440110": "파두",          
        "316140": "우리기술투자", "108320": "실리콘투", "005380": "현대차", "000270": "기아", "064350": "현대로템",       
        "012450": "한화에어로스페이스", "465650": "두산로보틱스", "454910": "레인보우로보틱스", "247540": "에코프로비엠",   
        "373220": "LG에너지솔루션", "005490": "POSCO홀딩스", "051910": "LG화학", "068270": "셀트리온",       
        "207940": "삼성바이오로직스", "112610": "씨젠"
    }

# =================================================================
# 🔄 핵심 동기화 로직 전용 함수 (중복 제거 및 리셋 연동용)
# =================================================================
def run_master_sync(api, master_pool):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("한투 보안 표준 인증 토큰 획득 및 20선 수급 계측 중..."):
        master_token = api.get_fresh_access_token()
        
    if not master_token:
        st.error("🚨 한투 서버 토큰 발급 실패. Secrets 설정을 재점검하십시오.")
        return
        
    temp_history = {}
    temp_pct = {}
    success_count = 0
    
    st.markdown("### 🔍 실시간 계측 레이더 현황")
    log_box = st.empty()
    log_messages = []
    
    progress_bar = st.progress(0)
    total_stocks = len(master_pool)
    
    for idx, (ticker, name) in enumerate(master_pool.items()):
        data, server_msg = api.get_realtime_price(ticker, master_token)
        
        if data:
            log_messages.append(f"🟢 **{name} ({ticker})** -> 현재가: {int(data['Close']):,}원 완료")
        else:
            log_messages.append(f"❌ **{name} ({ticker})** -> 실패 ({server_msg})")
            
        log_box.markdown("\n".join(log_messages[-5:]))
        
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
        
        time.sleep(0.33)
        progress_bar.progress((idx + 1) / total_stocks)
        
    progress_bar.empty()

    if success_count > 0:
        st.session_state.market_history.update(temp_history)
        st.session_state.live_pct_map.update(temp_pct)
        st.session_state["data_loaded"] = True
        st.toast(f"총 {success_count}개 종목 실시간 수급 동기화 성공!", icon="🔥")

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="AI 주도주 실시간 단타 스캐너 20", layout="wide")

st.title("🎯 AI 정예 주도주 20선 실시간 멀티 스캐너")
st.caption(f"가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 리셋 시 AI 자동 재스캔 고도화 버전")

if "market_history" not in st.session_state:
    st.session_state.market_history = {}
if "live_pct_map" not in st.session_state:
    st.session_state.live_pct_map = {}

api = KoreaInvestmentOfficialAPI()
master_pool = get_ai_lead_stocks_20()

col_btn1, col_btn2, col_info = st.columns([1.5, 1.5, 4])

# 1. 일반 동기화 버튼
if col_btn1.button("⚡ AI 정예 20선 수급 동기화", type="primary", use_container_width=True, key="btn_sync_main"):
    run_master_sync(api, master_pool)

# 2. ⚡ 대개조: 리셋과 동시에 AI 자동 스캔 연동 버튼
if col_btn2.button("🧹 캐시 리셋 + AI 즉시 자동스캔", use_container_width=True, key="btn_reset_and_run"):
    # 즉각적인 메모리 초기화
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    if "data_loaded" in st.session_state: 
        del st.session_state["data_loaded"]
    
    # 정화 직후 끊김 없이 바로 한투 20선 API 호출 프로세스 시동
    st.write("🧹 메모리 버퍼 완전 초기화 완수. 즉시 수급 재계측을 시작합니다...")
    run_master_sync(api, master_pool)
    st.rerun()

col_info.markdown("💡 **알림:** 오른쪽 `🧹 캐시 리셋...` 버튼을 누르면 과거 누적 데이터가 깨끗이 청소된 후 **즉시 새로운 실시간 패킷 분석이 실행**됩니다.")

st.markdown("---")

# =================================================================
# ⚙️ 주도주 연산 가동 및 다차원 분석 매트릭스 렌더링
# =================================================================
if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    
    for ticker, df in st.session_state.market_history.items():
        if df.empty: continue
        latest = df.iloc[-1]
        
        growth_rate = float(st.session_state.live_pct_map.get(ticker, 0.0))
        vwap_val = float(df["Close"].mean())
        
        ranking_list.append({
            "code": str(ticker), "name": str(master_pool.get(ticker)), "price": int(latest["Close"]),
            "vwap": int(vwap_val), "growth": growth_rate, "gap": float(latest["Close"] - vwap_val)
        })
    
    ranking_df = pd.DataFrame(ranking_list)
    
    if not ranking_df.empty:
        ranking_df = ranking_df.sort_values(by="growth", ascending=False).reset_index(drop=True)
        
        st.subheader("📊 20대 주도주 당일 단타 매트릭스")
        up_stocks = len(ranking_df[ranking_df["growth"] > 0])
        down_stocks = len(ranking_df[ranking_df["growth"] < 0])
        
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        metric_col1.metric("🔥 상승 우위 종목수", f"{up_stocks} 개", f"+{up_stocks - down_stocks} 개 격차")
        metric_col2.metric("📈 20선 최고 등락 종목", f"{ranking_df.iloc[0]['name']}", f"{ranking_df.iloc[0]['growth']:+.2f}%")
        metric_col3.metric("📉 20선 최저 등락 종목", f"{ranking_df.iloc[-1]['name']}", f"{ranking_df.iloc[-1]['growth']:+.2f}%")
        
        st.markdown("---")
        st.subheader("🔥 AI 선정 정예 주도주 실시간 순위 Top 20")
        
        display_rows = []
        for rank, row in enumerate(ranking_df.itertuples(), 1):
            if row.growth > 3.5 and row.gap > 0:
                signal = "⚡ 초강력 돌파 (매수)"
            elif row.growth > 0.5:
                signal = "🟢 수급 추종 (보유)"
            elif row.growth < -2.0:
                signal = "🚨 과매도 탈출 (청산)"
            else:
                signal = "⚪ 숨고르기 (관망)"
                
            display_rows.append({
                "순위": f"{rank}위", "종목코드": row.code, "종목명": row.name, "현재가": f"{row.price:,} 원",
                "단기 이평선(VWAP)": f"{row.vwap:,} 원", "당일 등락률": f"{row.growth:+.2f}%",
                "이평선 대비 격차": f"{int(row.gap):+,}원", "실시간 단타 시그널": signal
            })
        
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("🎯 20선 실시간 멀티 수급 보드")
        
        cols = st.columns(4)
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 4]
            with target_col:
                st.markdown(f"#### {row.name} `({row.code})`")
                st.metric(label=f"등락률: {row.growth:+.2f}%", value=f"{row.price:,}원", delta=f"이평차: {int(row.gap):+}원")
                
                if row.growth > 3.5:
                    st.error("⚡ 대량 거래 유입")
                elif row.growth < -2.0:
                    st.info("🚨 과매도 낙폭과대")
                else:
                    st.success("⚖️ 균형 수급 유지")
                st.markdown("---")
else:
    st.info("⏳ 시스템 가동 대기 중입니다. 버튼을 클릭해 스캔을 가동하십시오.")
