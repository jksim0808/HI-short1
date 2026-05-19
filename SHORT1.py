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
# 🏦 한투 실전투자 전용 파싱 및 실시간 종목 추출 엔진
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
            return r.json().get("access_token")
        except:
            return None

    # 시장 거래대금 상위 20종목 동적 추출
    def get_market_leading_tickers(self, token):
        if not token: return {}
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHPST01710000",
            "custtype": "P"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"
        }
        try:
            r = requests.get(url, headers=headers, params=params, timeout=5)
            if r.status_code == 200:
                output = r.json().get("output", [])
                dynamic_pool = {}
                for item in output:
                    ticker = item.get("mksc_shrn_iscd")
                    name = item.get("hts_kor_isnm")
                    if ticker and name:
                        if "우" in name or "스팩" in name or "리츠" in name: continue
                        dynamic_pool[ticker] = name
                        if len(dynamic_pool) >= 20: break
                return dynamic_pool
        except:
            pass
        return {"005930": "삼성전자", "000660": "SK하이닉스", "042700": "한미반도체", "440110": "파두"}

    # 🔥 [대수술] 어떤 패킷이 들어와도 정밀 타격하는 현재가 파싱 로직
    def get_realtime_price(self, ticker, token):
        if not token: return None, "토큰 누락"
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
                out = res_json.get("output")
                
                # 🛡️ 리스트 구조로 래핑되어 들어오는 경우 첫 번째 원소 강제 파싱
                if isinstance(out, list) and len(out) > 0:
                    out = out[0]
                elif not out or not isinstance(out, dict):
                    # 백업 필드(output1)까지 2중 추적
                    out = res_json.get("output1", {})
                    if isinstance(out, list) and len(out) > 0: out = out[0]
                
                if isinstance(out, dict):
                    # 문자열 공백, 기호(+, -) 완벽 제거 후 float 변환 유틸 함수
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    # 한투 주종목 현재가 키값 매핑 (stck_prpr 또는 prpr)
                    close_val = _clean(out.get("stck_prpr"))
                    if close_val == 0: close_val = _clean(out.get("prpr"))
                    
                    if close_val > 0:
                        # 등락률 파싱 (부호 유지해야 하므로 replace 없이 부동소수점화)
                        raw_ctrt = out.get("prdy_ctrt") if out.get("prdy_ctrt") else out.get("ctrt", "0.0")
                        
                        data_dict = {
                            "Close": close_val,
                            "High": _clean(out.get("stck_hgpr") if out.get("stck_hgpr") else out.get("hgpr", 0)),
                            "Low": _clean(out.get("stck_lwpr") if out.get("stck_lwpr") else out.get("lwpr", 0)),
                            "Volume": _clean(out.get("accl_tr_vol") if out.get("accl_tr_vol") else out.get("vol", 0)),
                            "PrdyCtrt": float(str(raw_ctrt).strip())
                        }
                        return data_dict, "성공"
                return None, "패킷 구조 불일치"
            return None, f"HTTP {r.status_code}"
        except Exception as e:
            return None, f"예외: {str(e)}"

# =================================================================
# 🔄 동적 수급 주도주 추출 및 실시간 데이터 매핑 함수
# =================================================================
def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("⚡ 실시간 거래대금 폭발 주도주 20선 발굴 중..."):
        master_token = api.get_fresh_access_token()
        if not master_token:
            st.error("🚨 한투 서버 토큰 발급 실패. Secrets 설정을 재점검하십시오.")
            return
        active_pool = api.get_market_leading_tickers(master_token)
    
    st.session_state["active_pool"] = active_pool
    temp_history = {}
    temp_pct = {}
    success_count = 0
    
    st.markdown("### 🔍 실시간 수급 체결 분석 레이더")
    log_box = st.empty()
    log_messages = []
    
    progress_bar = st.progress(0)
    total_stocks = len(active_pool)
    
    for idx, (ticker, name) in enumerate(active_pool.items()):
        data, server_msg = api.get_realtime_price(ticker, master_token)
        
        if data:
            log_messages.append(f"🟢 **{name} ({ticker})** -> 현재가 매핑 완료 ({int(data['Close']):,}원 / {data['PrdyCtrt']:+.2f}%)")
            success_count += 1
            new_row = pd.DataFrame([{
                "Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])
            }], index=[pd.to_datetime(current_time)])
            
            temp_pct[ticker] = float(data["PrdyCtrt"])
            
            if ticker not in st.session_state.market_history:
                temp_history[ticker] = new_row
            else:
                temp_history[ticker] = pd.concat([st.session_state.market_history[ticker], new_row]).tail(20)
        else:
            log_messages.append(f"❌ **{name} ({ticker})** -> 실패 ({server_msg})")
            
        log_box.markdown("\n".join(log_messages[-5:]))
        time.sleep(0.35)
        progress_bar.progress((idx + 1) / total_stocks)
        
    progress_bar.empty()

    if success_count > 0:
        st.session_state.market_history = temp_history
        st.session_state.live_pct_map = temp_pct
        st.session_state["data_loaded"] = True
        st.toast("🔥 현재가 실시간 동기화 정밀 연동 완료!", icon="⚡")

# =================================================================
# 🖥️ UI 및 메인 대시보드 화면 구성
# =================================================================
st.set_page_config(page_title="실시간 거래대금 수급 스캐너 20", layout="wide")

st.title("🎯 AI 시장 거래대금 상위 주도주 20선 동적 실시간 스캐너")
st.caption(f"가동 시점: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 현재가 왜곡 보정 및 실시간 엔진 완결판")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}

api = KoreaInvestmentOfficialAPI()
col_btn1, col_btn2, col_info = st.columns([1.5, 1.5, 4])

# 1. 수급 업데이트 버튼
if col_btn1.button("⚡ 현재 종목 수급 동기화", type="primary", use_container_width=True):
    if not st.session_state.active_pool:
        run_dynamic_market_scan(api)
    else:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with st.spinner("현재가 리프레시 중..."):
            master_token = api.get_fresh_access_token()
            if master_token:
                for ticker in st.session_state.active_pool.keys():
                    data, _ = api.get_realtime_price(ticker, master_token)
                    if data:
                        new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                        st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                        st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history.get(ticker, pd.DataFrame()), new_row]).tail(20)
                st.session_state["data_loaded"] = True
                st.rerun()

# 2. 캐시 리셋 + 신규 주도주 고속 크롤링
if col_btn2.button("🧹 리셋 + 실시간 주도주 새로 발굴", use_container_width=True):
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    st.session_state.active_pool = {}
    if "data_loaded" in st.session_state: del st.session_state["data_loaded"]
    run_dynamic_market_scan(api)
    st.rerun()

st.markdown("---")

# =================================================================
# ⚙️ 주도주 연산 가동 및 다차원 분석 매트릭스 렌더링
# =================================================================
if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    current_pool = st.session_state.active_pool
    
    for ticker, df in st.session_state.market_history.items():
        if df.empty: continue
        latest = df.iloc[-1]
        growth_rate = float(st.session_state.live_pct_map.get(ticker, 0.0))
        vwap_val = float(df["Close"].mean())
        
        ranking_list.append({
            "code": str(ticker), "name": str(current_pool.get(ticker, "알수없음")), "price": int(latest["Close"]),
            "vwap": int(vwap_val), "growth": growth_rate, "gap": float(latest["Close"] - vwap_val)
        })
    
    ranking_df = pd.DataFrame(ranking_list)
    
    if not ranking_df.empty:
        ranking_df = ranking_df.sort_values(by="growth", ascending=False).reset_index(drop=True)
        
        st.subheader("📊 거래대금 상위 실시간 주도주 트렌드")
        up_stocks = len(ranking_df[ranking_df["growth"] > 0])
        down_stocks = len(ranking_df[ranking_df["growth"] < 0])
        
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        metric_col1.metric("🔥 실시간 상승 종목수", f"{up_stocks} 개", f"하락 {down_stocks}개 대비 우위")
        metric_col2.metric("📈 20선 수급 대장주", f"{ranking_df.iloc[0]['name']}", f"{ranking_df.iloc[0]['growth']:+.2f}%")
        metric_col3.metric("📉 20선 최하위 종목", f"{ranking_df.iloc[-1]['name']}", f"{ranking_df.iloc[-1]['growth']:+.2f}%")
        
        st.markdown("---")
        st.subheader("🔥 실시간 돈 몰리는 정예 20선 (정밀 현재가 기준 순위)")
        
        display_rows = []
        for rank, row in enumerate(ranking_df.itertuples(), 1):
            if row.growth > 4.0 and row.gap > 0:
                signal = "⚡ 초강력 돌파 (매수)"
            elif row.growth > 0.5:
                signal = "🟢 수급 추종 (보유)"
            elif row.growth < -2.0:
                signal = "🚨 단기 청산 (대피)"
            else:
                signal = "⚪ 숨고르기 (관망)"
                
            display_rows.append({
                "순위": f"{rank}위", "종목코드": row.code, "종목명": row.name, "현재가": f"{row.price:,} 원",
                "단기 이평선": f"{row.vwap:,} 원", "당일 등락률": f"{row.growth:+.2f}%",
                "이평선 격차": f"{int(row.gap):+,}원", "실시간 단타 시그널": signal
            })
        
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("🎯 실시간 거래대금 상위 전광판")
        
        cols = st.columns(4)
        for idx, row in enumerate(ranking_df.itertuples()):
            target_col = cols[idx % 4]
            with target_col:
                st.markdown(f"#### {row.name} `({row.code})`")
                st.metric(label=f"등락률: {row.growth:+.2f}%", value=f"{row.price:,}원", delta=f"이평차: {int(row.gap):+}원")
                
                if row.growth > 4.0:
                    st.error("⚡ 대량 거래 유입")
                elif row.growth < -2.0:
                    st.info("🚨 과매도 반등 대기")
                else:
                    st.success("⚖️ 균형 수급 유지")
                st.markdown("---")
else:
    st.info("⏳ 시스템 대기 중입니다. 버튼을 눌러 실시간 당일 대장주 20개를 수집하십시오.")
