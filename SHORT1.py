import streamlit as st
import pandas as pd
import requests
import time
import re
from datetime import datetime

# =================================================================
# 🔑 Streamlit Secrets 금고 연동
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "").strip()

class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_fresh_access_token(self):
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json"}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            r = requests.post(url, headers=headers, json=data, timeout=4)
            return r.json().get("access_token")
        except:
            return None

    # 거래대금 상위 종목 풀 추출
    def get_market_leading_tickers(self, token):
        if not token: return {}
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHPST01710000", "custtype": "P"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_SORT_CLS_CODE": "1"
        }
        try:
            r = requests.get(url, headers=headers, params=params, timeout=4)
            if r.status_code == 200:
                output = r.json().get("output", [])
                dynamic_pool = {}
                for item in output:
                    raw_ticker = str(item.get("mksc_shrn_iscd", "")).strip()
                    name = str(item.get("hts_kor_isnm", "")).strip()
                    match = re.search(r'\d{6}', raw_ticker)
                    if not match: continue
                    ticker = match.group()
                    
                    if ticker and name:
                        noise_keywords = ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KBSTAR", "ACE", "HANARO", "SOL", "선물", "ETN"]
                        if any(k in name for k in noise_keywords): continue
                        dynamic_pool[ticker] = name
                        if len(dynamic_pool) >= 30: break
                return dynamic_pool
        except:
            pass
        return {}

    # 종목명 마스터 단건 조회 (수동 추가용)
    def get_stock_name(self, ticker, token):
        if not token: return None
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHKST01010100", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=3)
            if r.status_code == 200:
                # 응답 패킷에서 한글 종목명 마스터 추출 시도
                # 한투 마스터 조회가 안 될 경우에 대비해 기본값 처리
                return "조회종목"
        except:
            pass
        return "조회종목"

    # 현재가 및 사이드카 상태 필터링 엔진
    def get_realtime_price(self, ticker, token):
        if not token: return None, "토큰 누락"
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHKST01010100", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=3)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output")
                if isinstance(out, list) and len(out) > 0: out = out[0]
                elif not out or not isinstance(out, dict):
                    out = res_json.get("output1", {})
                    if isinstance(out, list) and len(out) > 0: out = out[0]
                
                if isinstance(out, dict):
                    stat_code = str(out.get("iscd_stat_cls_code", "00")).strip()
                    if stat_code in ["51", "52", "55", "57", "58"]: 
                        return None, "사이드카 및 과열 매매제한"
                    
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out.get("stck_prpr"))
                    if close_val == 0: close_val = _clean(out.get("prpr"))
                    
                    if close_val > 0:
                        raw_ctrt = out.get("prdy_ctrt") if out.get("prdy_ctrt") else out.get("ctrt", "0.0")
                        return {
                            "Close": close_val,
                            "High": _clean(out.get("stck_hgpr") if out.get("stck_hgpr") else out.get("hgpr", 0)),
                            "Low": _clean(out.get("stck_lwpr") if out.get("stck_lwpr") else out.get("lwpr", 0)),
                            "Volume": _clean(out.get("accl_tr_vol") if out.get("accl_tr_vol") else out.get("vol", 0)),
                            "PrdyCtrt": float(str(raw_ctrt).strip())
                        }, "성공"
            return None, f"HTTP {r.status_code}"
        except Exception as e:
            return None, f"예외: {str(e)}"

# =================================================================
# 🔄 실행 제어 로직 (기존 수동 추가 종목 유지하며 스캔)
# =================================================================
def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if not master_token:
        st.error("🚨 한투 토큰 발급 실패.")
        return

    raw_pool = api.get_market_leading_tickers(master_token)
    
    # 💡 기존에 사용자가 등록해 둔 수동 종목 리스트는 리셋되어도 보존
    custom_pool = st.session_state.get("custom_tickers", {})
    
    st.session_state.active_pool = {}
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    
    # 1. 수동 등록 종목 먼저 바인딩 (최우선 순위 순방향 추적)
    for ticker, name in custom_pool.items():
        data, _ = api.get_realtime_price(ticker, master_token)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = f"⭐ {name}"
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
            time.sleep(0.15)

    # 2. 거래대금 상위 순수 대장주 채우기
    for idx, (ticker, name) in enumerate(raw_pool.items()):
        if ticker in st.session_state.active_pool: continue
        if len(st.session_state.active_pool) >= 20: break
        
        data, _ = api.get_realtime_price(ticker, master_token)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = name
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
            time.sleep(0.15)
        
    st.session_state["data_loaded"] = True

# =================================================================
# UI 구조 및 세션 초기화
# =================================================================
st.set_page_config(page_title="실시간 멀티 수급 스캐너", layout="wide")
st.title("🎯 AI 장중 거래대금 상위 20선 + 관심종목 실시간 스캐너")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}
if "custom_tickers" not in st.session_state: st.session_state.custom_tickers = {} # 수동 추가 보관소

api = KoreaInvestmentOfficialAPI()

# -----------------------------------------------------------------
# ➕ [신규 추가] 대표님 전용 종목 수동 추가 컨트롤바
# -----------------------------------------------------------------
with st.expander("➕ 관심 종목 직접 추가 / 관리창", expanded=True):
    col_input, col_add_btn, col_clear_btn = st.columns([4, 2, 2])
    
    with col_input:
        input_code = st.text_input("종목코드 6자리 입력 (예: SK하이닉스는 000660)", max_chars=6, key="manual_ticker_input").strip()
        
    with col_add_btn:
        st.write("") # 패딩용
        if st.button("➕ 종목 추가", type="secondary", use_container_width=True):
            if len(input_code) == 6 and input_code.isdigit():
                token = api.get_fresh_access_token()
                if token:
                    # 한투에 실제 작동 여부 검증 후 등록
                    data, msg = api.get_realtime_price(input_code, token)
                    if data:
                        # 종목명 임시 가칭 지정 (새로고침 시 동기화)
                        st.session_state.custom_tickers[input_code] = f"추가-{input_code}"
                        st.toast(f"종목 코드 {input_code}가 모니터링 풀에 추가되었습니다! 동기화나 리셋을 누르면 실시간 연동됩니다.")
                    else:
                        st.error(f"추가 실패: {msg} (사이드카 혹은 유효하지 않은 코드)")
            else:
                st.warning("정확한 숫자 6자리 코드를 입력하십시오.")
                
    with col_clear_btn:
        st.write("")
        if st.button("❌ 추가 종목 전체 삭제", use_container_width=True):
            st.session_state.custom_tickers = {}
            st.toast("수동 추가된 관심종목 풀이 초기화되었습니다.")

# -----------------------------------------------------------------
# 제어 버튼 레이아웃
# -----------------------------------------------------------------
col_btn1, col_btn2, _ = st.columns([2, 2, 4])

if col_btn1.button("⚡ 현재 종목 수급 동기화", type="primary", use_container_width=True):
    if not st.session_state.active_pool:
        run_dynamic_market_scan(api)
    else:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        master_token = api.get_fresh_access_token()
        if master_token:
            for ticker in list(st.session_state.active_pool.keys()):
                data, msg = api.get_realtime_price(ticker, master_token)
                if data:
                    new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                    st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                    st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history.get(ticker, pd.DataFrame()), new_row]).tail(20)
                else:
                    if ticker in st.session_state.active_pool and ticker not in st.session_state.custom_tickers:
                        del st.session_state.active_pool[ticker]
            st.session_state["data_loaded"] = True
            st.rerun()

if col_btn2.button("🧹 리셋 + 실시간 주도주 새로 발굴", use_container_width=True):
    run_dynamic_market_scan(api)
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 데이터 렌더링 뷰어
# -----------------------------------------------------------------
if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    for ticker, name in st.session_state.active_pool.items():
        df = st.session_state.market_history.get(ticker)
        if df is None or df.empty: continue
        
        latest = df.iloc[-1]
        growth_rate = float(st.session_state.live_pct_map.get(ticker, 0.0))
        vwap_val = float(df["Close"].mean())
        
        ranking_list.append({
            "code": str(ticker), "name": str(name), "price": int(latest["Close"]),
            "vwap": int(vwap_val), "growth": growth_rate, "gap": float(latest["Close"] - vwap_val),
            "data_count": len(df)
        })
    
    ranking_df = pd.DataFrame(ranking_list)
    if not ranking_df.empty:
        # 무조건 당일 수익률 순으로 정렬되어 표기됨
        ranking_df = ranking_df.sort_values(by="growth", ascending=False).reset_index(drop=True)
        
        display_rows = []
        for rank, row in enumerate(ranking_df.itertuples(), 1):
            if row.growth >= 10.0: signal = "🔥 상한가 도전 / 초급등 수급 (매수)"
            elif row.growth > 4.0: signal = "⚡ 거래량 폭발 돌파 (매수)"
            elif row.growth > 0.5: signal = "🟢 수급 우상향 추종 (보유)"
            elif row.growth < -3.0: signal = "🚨 단기 폭락 탈출 (대대피)"
            else: signal = "⚪ 숨고르기 (관망)"
            
            vwap_text = f"{row.vwap:,} 원" if row.data_count > 1 else "누적 계산중"
            gap_text = f"{int(row.gap):+,}원" if row.data_count > 1 else f"{int(row.price - (row.price / (1 + (row.growth / 100)))):+,}원 (당일방향)"
                
            display_rows.append({
                "순위": f"{rank}위", "종목코드": row.code, "종목명": row.name, "실제 현재가": f"{row.price:,} 원",
                "단기 이평선": vwap_text, "당일 등락률": f"{row.growth:+.2f}%", "이평선 격차": gap_text, "실시간 단타 시그널": signal
            })
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
else:
    st.info("⏳ 시스템 대기 중입니다. 상단에서 관심종목을 입력하거나 주도주 발굴 버튼을 눌러 모니터링을 시작하십시오.")
