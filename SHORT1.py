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

# 한투 통신 실패 시 작동할 안전 보장용 대한민국 대표 주도주 20선 마스터 딕셔너리
FALLBACK_20_POOL = {
    "005930": "삼성전자", "027360": "아주IB투자", "021880": "메이슨캐피탈", "011000": "진원생명과학",
    "900300": "오가닉티코스메틱", "142280": "녹십자엠에스", "439960": "코스모로보틱스", "066980": "한성크린텍",
    "203650": "드림시큐리티", "066430": "아이로보틱스", "307870": "비투엔", "290690": "소룩스",
    "321370": "센서뷰", "086960": "MDS테크", "088350": "한화생명", "003280": "흥아해운",
    "018880": "한온시스템", "000660": "SK하이닉스", "005490": "POSCO홀딩스", "035420": "NAVER"
}

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

    # 거래대금 상위 종목 풀 추출 (20개 이상 확실히 확보하도록 바인딩)
    def get_market_leading_tickers(self, token):
        if not token: return FALLBACK_20_POOL
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
                        if len(dynamic_pool) >= 35: break
                return dynamic_pool if len(dynamic_pool) >= 15 else FALLBACK_20_POOL
        except:
            pass
        return FALLBACK_20_POOL

    # 종목명 및 상태 마스터 단건 조회 (수동 추가 종목 유효성 확인용)
    def get_stock_master_name(self, ticker, token):
        if not token: return "관심종목"
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHKST01010100", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=3)
            if r.status_code == 200:
                out = r.json().get("output", {})
                if isinstance(out, list) and len(out) > 0: out = out[0]
                name = out.get("hts_kor_isnm", "").strip() if isinstance(out, dict) else ""
                return name if name else "지정종목"
        except:
            pass
        return "지정종목"

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
# 🔄 시장 데이터 및 관심 종목 20선 압축 스캔 엔진
# =================================================================
def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if not master_token:
        st.error("🚨 한투 토큰 발급에 실패했습니다. API Key와 Secret을 확인하십시오.")
        return

    raw_pool = api.get_market_leading_tickers(master_token)
    custom_pool = st.session_state.get("custom_tickers", {})
    
    st.session_state.active_pool = {}
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    
    # 1. 수동 등록한 관심 종목 최우선 배치
    for ticker, name in custom_pool.items():
        data, _ = api.get_realtime_price(ticker, master_token)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = f"⭐ {name}"
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
            time.sleep(0.1)

    # 2. 총 20개 종목이 채워질 때까지 실시간 상위 거래대금 대장주 순차 매핑
    for ticker, name in raw_pool.items():
        if ticker in st.session_state.active_pool: continue
        if len(st.session_state.active_pool) >= 20: break  # 정확하게 20개 라인 보장
        
        data, _ = api.get_realtime_price(ticker, master_token)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = name
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
            time.sleep(0.1)
        
    st.session_state["data_loaded"] = True

# =================================================================
# UI 구조 및 데이터 세션 초기 설정
# =================================================================
st.set_page_config(page_title="실시간 주도주 수급 스캐너 20", layout="wide")
st.title("🎯 AI 장중 거래대금 상위 20선 실시간 동적 스캐너")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}
if "custom_tickers" not in st.session_state: st.session_state.custom_tickers = {}

api = KoreaInvestmentOfficialAPI()

# 기본 구동 내역이 전혀 없을 때 20선 즉시 자동 빌드
if not st.session_state.active_pool:
    run_dynamic_market_scan(api)

# -----------------------------------------------------------------
# ➕ 관심 종목 추가 제어 레이아웃
# -----------------------------------------------------------------
with st.expander("➕ 관심 종목 직접 추가 / 관리 상자", expanded=True):
    col_input, col_add_btn, col_clear_btn = st.columns([4, 2, 2])
    
    with col_input:
        input_code = st.text_input("종목코드 6자리 입력 (예: SK하이닉스 000660 / 삼성전자 005930)", max_chars=6, key="manual_ticker_key").strip()
        
    with col_add_btn:
        st.write("") 
        if st.button("➕ 종목 추가", type="secondary", use_container_width=True):
            if len(input_code) == 6 and input_code.isdigit():
                token = api.get_fresh_access_token()
                if token:
                    real_name = api.get_stock_master_name(input_code, token)
                    data, msg = api.get_realtime_price(input_code, token)
                    
                    if data:
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        # 메모리에 단건 실시간 데이터 강제 동기화 바인딩
                        st.session_state.custom_tickers[input_code] = real_name
                        st.session_state.active_pool[input_code] = f"⭐ {real_name}"
                        st.session_state.live_pct_map[input_code] = float(data["PrdyCtrt"])
                        
                        new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                        st.session_state.market_history[input_code] = new_row
                        st.session_state["data_loaded"] = True
                        st.toast(f"🔥 [{real_name}] 종목이 대시보드 리스트에 즉시 연동되었습니다!")
                        st.rerun()
                    else:
                        st.error(f"추가 실패: {msg} (코드를 재확인하시거나 과열 정지 상태인지 파악 필요)")
            else:
                st.warning("정확한 숫자 6자리 코드를 입력하십시오.")
                
    with col_clear_btn:
        st.write("")
        if st.button("❌ 추가 종목 전체 삭제", use_container_width=True):
            st.session_state.custom_tickers = {}
            run_dynamic_market_scan(api)
            st.toast("추가 풀 초기화 완료")
            st.rerun()

# -----------------------------------------------------------------
# 동기화 및 리셋 컨트롤 패널
# -----------------------------------------------------------------
col_btn1, col_btn2, _ = st.columns([2, 2, 4])

if col_btn1.button("⚡ 현재 종목 수급 동기화", type="primary", use_container_width=True):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if master_token:
        for ticker in list(st.session_state.active_pool.keys()):
            data, _ = api.get_realtime_price(ticker, master_token)
            if data:
                new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history.get(ticker, pd.DataFrame()), new_row]).tail(20)
        st.session_state["data_loaded"] = True
        st.rerun()

if col_btn2.button("🧹 리셋 + 실시간 주도주 새로 발굴", use_container_width=True):
    run_dynamic_market_scan(api)
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 🖥️ 고정 20선 데이터 표출 뷰어
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
        # 무조건 전 종목 당일 등락률 순 정렬 표기
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
    st.info("⏳ 호가 데이터 추출 중입니다. 잠시만 기다려주십시오.")
