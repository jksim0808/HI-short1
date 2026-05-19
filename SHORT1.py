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

# 시스템 안정망용 주도주 백업 풀 (통신 마비 시 최소 기동 보장)
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("027360", "아주IB투자"), ("021880", "메이슨캐피탈"),
    ("011000", "진원생명과학"), ("900300", "오가닉티코스메틱"), ("142280", "녹십자엠에스"), ("439960", "코스모로보틱스"),
    ("066980", "한성크린텍"), ("203650", "드림시큐리티"), ("066430", "아이로보틱스"), ("307870", "비투엔"),
    ("290690", "소룩스"), ("321370", "센서뷰"), ("086960", "MDS테크"), ("088350", "한화생명"),
    ("003280", "흥아해운"), ("018880", "한온시스템"), ("005490", "POSCO홀딩스"), ("035420", "NAVER"),
    ("005380", "현대차"), ("000270", "기아"), ("068270", "셀트리온")
]

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
            r = requests.post(url, headers=headers, json=data, timeout=3)
            return r.json().get("access_token")
        except:
            return None

    def get_market_leading_tickers(self, token):
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
                pool = []
                for item in output:
                    raw_ticker = str(item.get("mksc_shrn_iscd", "")).strip()
                    name = str(item.get("hts_kor_isnm", "")).strip()
                    match = re.search(r'\d{6}', raw_ticker)
                    if not match: continue
                    ticker = match.group()
                    
                    if ticker and name:
                        noise_keywords = ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KBSTAR", "ACE", "HANARO", "SOL"]
                        if any(k in name for k in noise_keywords): continue
                        pool.append((ticker, name))
                if len(pool) > 5: return pool
        except:
            pass
        return BACKUP_MASTER_POOL

    def get_realtime_price(self, ticker, token):
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHKST01010100", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        try:
            # 타임아웃을 2.5초로 짧게 잡아 한투 서버가 먹통일 때 같이 굳어버리는 현상 전면 방어
            r = requests.get(url, headers=headers, params=params, timeout=2.5)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output")
                if isinstance(out, list) and len(out) > 0: out = out[0]
                elif not out or not isinstance(out, dict):
                    out = res_json.get("output1", {})
                    if isinstance(out, list) and len(out) > 0: out = out[0]
                
                if isinstance(out, dict):
                    stat_code = str(out.get("iscd_stat_cls_code", "00")).strip()
                    is_restricted = stat_code in ["51", "52", "55", "57", "58"]
                    
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out.get("stck_prpr"))
                    if close_val == 0: close_val = _clean(out.get("prpr"))
                    
                    if close_val > 0:
                        raw_ctrt = out.get("prdy_ctrt") if out.get("prdy_ctrt") else out.get("ctrt", "0.0")
                        return {
                            "name": out.get("hts_kor_isnm", "지정종목").strip(),
                            "Close": close_val,
                            "High": _clean(out.get("stck_hgpr") if out.get("stck_hgpr") else out.get("hgpr", 0)),
                            "Low": _clean(out.get("stck_lwpr") if out.get("stck_lwpr") else out.get("lwpr", 0)),
                            "Volume": _clean(out.get("accl_tr_vol") if out.get("accl_tr_vol") else out.get("vol", 0)),
                            "PrdyCtrt": float(str(raw_ctrt).strip()),
                            "is_restricted": is_restricted
                        }
        except:
            pass
        return None

# =================================================================
# 🔄 동적 안심 20선 스캔 엔진 (슬립 딜레이 튜닝 버전)
# =================================================================
def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if not master_token:
        st.error("🚨 한국투자증권 Access Token 인증에 실패했습니다.")
        return

    raw_pool = api.get_market_leading_tickers(master_token)
    custom_pool = st.session_state.get("custom_tickers", {})
    
    st.session_state.active_pool = {}
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    
    # 1. 수동 등록 관심종목 우선 배치
    for ticker in list(custom_pool.keys()):
        data = api.get_realtime_price(ticker, master_token)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = f"⭐ {data['name']}"
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
        # ⏱️ 한투 API 초당 초과 요청 에러 방지를 위해 딜레이를 0.25초로 상향 조정
        time.sleep(0.25)

    # 2. 정확히 20개가 빌 때까지 주도주 확보 (사이드카 제외)
    for ticker, name in raw_pool:
        if ticker in st.session_state.active_pool: continue
        if len(st.session_state.active_pool) >= 20: break
        
        data = api.get_realtime_price(ticker, master_token)
        if data:
            if data["is_restricted"]:
                continue
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = data['name']
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
        time.sleep(0.25)
        
    # 데이터 유실로 20선이 안 무너지도록 예비 마스터 풀 가동 보장
    if len(st.session_state.active_pool) < 20:
        for ticker, name in BACKUP_MASTER_POOL:
            if ticker in st.session_state.active_pool: continue
            if len(st.session_state.active_pool) >= 20: break
            data = api.get_realtime_price(ticker, master_token)
            if data:
                new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                st.session_state.active_pool[ticker] = data['name']
                st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                st.session_state.market_history[ticker] = new_row
            time.sleep(0.25)

    st.session_state["data_loaded"] = True

# =================================================================
# UI 정의 및 세션 처리
# =================================================================
st.set_page_config(page_title="실시간 멀티 수급 주도주 스캐너", layout="wide")
st.title("🎯 AI 장중 거래대금 상위 20선 실시간 동적 스캐너")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}
if "custom_tickers" not in st.session_state: st.session_state.custom_tickers = {}

api = KoreaInvestmentOfficialAPI()

if not st.session_state.active_pool:
    run_dynamic_market_scan(api)

# -----------------------------------------------------------------
# ➕ 관심 종목 입력창
# -----------------------------------------------------------------
with st.expander("➕ 관심 종목 직접 추가 (무조건 즉시 반영)", expanded=True):
    col_input, col_add_btn, col_clear_btn = st.columns([4, 2, 2])
    
    with col_input:
        input_code = st.text_input("종목코드 6자리 (예: 삼성전자 005930 / SK하이닉스 000660)", max_chars=6, key="safe_ticker_input_box").strip()
        
    with col_add_btn:
        st.write("")
        if st.button("➕ 종목 즉시 추가", type="secondary", use_container_width=True):
            if len(input_code) == 6 and input_code.isdigit():
                token = api.get_fresh_access_token()
                if token:
                    data = api.get_realtime_price(input_code, token)
                    if data:
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.session_state.custom_tickers[input_code] = data['name']
                        st.session_state.active_pool[input_code] = f"⭐ {data['name']}"
                        st.session_state.live_pct_map[input_code] = float(data["PrdyCtrt"])
                        
                        new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                        st.session_state.market_history[input_code] = new_row
                        
                        st.session_state["data_loaded"] = True
                        st.toast(f"🔥 [{data['name']}] 종목이 리스트에 즉시 주입되었습니다.")
                        time.sleep(0.2)
                        st.rerun()
                    else:
                        st.error("종목 정보를 가져오지 못했습니다. 올바른 코드인지 확인하십시오.")
            else:
                st.warning("정확한 숫자 6자리 코드를 입력하십시오.")
                
    with col_clear_btn:
        st.write("")
        if st.button("❌ 추가 종목 전체 삭제", use_container_width=True):
            st.session_state.custom_tickers = {}
            run_dynamic_market_scan(api)
            st.toast("추가 리스트 초기화 완료")
            st.rerun()

# -----------------------------------------------------------------
# 컨트롤 패널
# -----------------------------------------------------------------
col_btn1, col_btn2, _ = st.columns([2, 2, 4])

if col_btn1.button("⚡ 현재 종목 수급 동기화", type="primary", use_container_width=True):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if master_token:
        for ticker in list(st.session_state.active_pool.keys()):
            data = api.get_realtime_price(ticker, master_token)
            if data:
                new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history.get(ticker, pd.DataFrame()), new_row]).tail(20)
            time.sleep(0.25) # 동기화 시에도 안전하게 0.25초 갭 배치
        st.session_state["data_loaded"] = True
        st.rerun()

if col_btn2.button("🧹 리셋 + 실시간 주도주 새로 발굴", use_container_width=True):
    run_dynamic_market_scan(api)
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 🖥️ 완결 대시보드 테이블 출력
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
    st.info("⏳ 호가 서버 안전 연결망을 조율 중입니다. 즉시 모니터링 테이블이 구성됩니다.")
