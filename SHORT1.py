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

# 시스템 안심 기동용 백업 마스터 풀 (종목명 매핑 사전 포함)
BACKUP_MASTER_POOL = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005380", "현대차"), ("000270", "기아"),
    ("068270", "셀트리온"), ("035420", "NAVER"), ("005490", "POSCO홀딩스"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("027360", "아주IB투자"), ("021880", "메이슨캐피탈"),
    ("011000", "진원생명과학"), ("900300", "오가닉티코스메틱"), ("142280", "녹십자엠에스"), ("439960", "코스모로보틱스"),
    ("066980", "한성크린텍"), ("203650", "드림시큐리티"), ("066430", "아이로보틱스"), ("307870", "비투엔")
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
                    name = str(item.get("hts_kor_isnm", item.get("data_name", ""))).strip()
                    match = re.search(r'\d{6}', raw_ticker)
                    if not match: continue
                    ticker = match.group()
                    
                    if ticker and name and name != "None":
                        noise_keywords = ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KBSTAR", "ACE", "HANARO", "SOL"]
                        if any(k in name for k in noise_keywords): continue
                        pool.append((ticker, name))
                if len(pool) > 0: return pool
        except:
            pass
        return BACKUP_MASTER_POOL

    def get_realtime_price(self, ticker, token, default_name="지정종목"):
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
            "appkey": self.app_key, "appsecret": self.app_secret, "tr_id": "FHKST01010100", "custtype": "P"
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).strip()}
        try:
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
                    
                    hts_name = str(out.get("hts_kor_isnm", "")).strip()
                    final_name = hts_name if (hts_name and hts_name != "None" and hts_name != "지정종목") else default_name
                    
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    close_val = _clean(out.get("stck_prpr"))
                    if close_val == 0: close_val = _clean(out.get("prpr"))
                    
                    if close_val > 0:
                        raw_ctrt = out.get("prdy_ctrt") if out.get("prdy_ctrt") else out.get("ctrt", "0.0")
                        return {
                            "name": final_name,
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

def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    master_token = api.get_fresh_access_token()
    if not master_token:
        st.error("🚨 한국투자증권 Access Token 발급에 실패했습니다.")
        return

    raw_pool = api.get_market_leading_tickers(master_token)
    custom_pool = st.session_state.get("custom_tickers", {})
    
    st.session_state.master_name_map = {}
    for t, n in BACKUP_MASTER_POOL: st.session_state.master_name_map[t] = n
    for t, n in raw_pool: st.session_state.master_name_map[t] = n
    for t, n in custom_pool.items(): st.session_state.master_name_map[t] = n

    st.session_state.active_pool = {}
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    
    # 1. 수동 등록 관심종목 우선 배치
    for ticker, name in custom_pool.items():
        resolved_name = st.session_state.master_name_map.get(ticker, name)
        data = api.get_realtime_price(ticker, master_token, default_name=resolved_name)
        if data:
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = f"⭐ {data['name']}"
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
        time.sleep(0.25)

    # 2. 거래대금 상위 대장주 실시간 바인딩
    for ticker, name in raw_pool:
        if ticker in st.session_state.active_pool: continue
        if len(st.session_state.active_pool) >= 20: break
        
        resolved_name = st.session_state.master_name_map.get(ticker, name)
        data = api.get_realtime_price(ticker, master_token, default_name=resolved_name)
        if data:
            if data["is_restricted"]: continue  # 사이드카 및 과열종목 진입 차단
                
            new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
            st.session_state.active_pool[ticker] = data['name']
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
        time.sleep(0.25)
        
    # 하한선 20위 보장 풀 가동
    if len(st.session_state.active_pool) < 20:
        for ticker, name in BACKUP_MASTER_POOL:
            if ticker in st.session_state.active_pool: continue
            if len(st.session_state.active_pool) >= 20: break
            
            resolved_name = st.session_state.master_name_map.get(ticker, name)
            data = api.get_realtime_price(ticker, master_token, default_name=resolved_name)
            if data:
                new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                st.session_state.active_pool[ticker] = data['name']
                st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                st.session_state.market_history[ticker] = new_row
            time.sleep(0.25)

    st.session_state["data_loaded"] = True

# =================================================================
# 🖥️ UI 대시보드 구성
# =================================================================
st.set_page_config(page_title="실시간 멀티 수급 주도주 스캐너", layout="wide")

# -----------------------------------------------------------------
# 📝 [추가] 상단 스캐너 운영 매커니즘 설명 가이드 박스
# -----------------------------------------------------------------
st.title("🎯 AI 장중 거래대금 상위 20선 실시간 동적 스캐너")

with st.container(border=True):
    st.subheader("💡 수급 주도주 스캐너 운영 및 분석 기준")
    col_guide1, col_guide2 = st.columns(2)
    
    with col_guide1:
        st.markdown("""
        **📌 20개 종목 선정 및 필터링 기준**
        * **거래대금 상위 정렬:** 시장에서 당일 돈이 가장 몰린 거래대금 상위 순방향 대장주들을 한투 API를 통해 실시간 수집합니다.
        * **시장 노이즈 원천 제거:** 단타 매매 시 혼선을 주는 '우선주(우)', '스팩주', '리츠', 'ETF/ETN 상품(KODEX, TIGER 등)'을 전면 필터링하여 순수 개별 급등주만 남깁니다.
        * **위험/제한 종목 자동 차단:** 장중 **매수 사이드카 발동**, 단기과열, 매매정지 상태인 종목은 수급이 꼬일 수 있으므로 탐색 풀에서 자동 제외합니다.
        * **고정 20선 무조건 보장:** 제외된 종목으로 인해 리스트가 짤리지 않도록 백업 우량주 풀에서 실시간 연동해 항상 20선을 유지합니다.
        """)
        
    with col_guide2:
        st.markdown("""
        **📈 실시간 단타 분석 및 시그널 기준**
        * **당일 등락률 순 정렬:** 실시간 수급 세기를 한눈에 보기 위해 현재가 기준 내림차순(최고 등락률 순)으로 초 단위 재정렬합니다.
        * **단기 이평선(VWAP 계열):** 장중 누적된 체결 호가들의 실시간 평균 가격(이평선)을 계산해 현재 수급의 허수를 판별합니다.
        * **이평선 격차:** 현재가가 단기 이평선보다 얼마나 높은지 계산해 돌파 여부와 추격매수 위험도를 실시간 계측합니다.
        * **단타 시그널 가이드:**
          * `🔥 10% 이상`: 상한가 도전 및 초급등 (강력한 수급 유입)
          * `⚡ 4% ~ 10%`: 거래량 폭발 돌파 시점 (단타 타겟)
          * `🟢 0.5% ~ 4%`: 안정적 우상향 추종 (안정 권역)
        """)

st.markdown("---")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}
if "custom_tickers" not in st.session_state: st.session_state.custom_tickers = {}
if "master_name_map" not in st.session_state: st.session_state.master_name_map = {}

api = KoreaInvestmentOfficialAPI()

if not st.session_state.active_pool:
    run_dynamic_market_scan(api)

# -----------------------------------------------------------------
# ➕ 관심 종목 입력 박스
# -----------------------------------------------------------------
with st.expander("➕ 관심 종목 직접 추가 (설정된 필터 조건과 무관하게 무조건 리스트 최우선 강제 진입)", expanded=True):
    col_input, col_add_btn, col_clear_btn = st.columns([4, 2, 2])
    
    with col_input:
        input_code = st.text_input("종목코드 6자리 (예: 삼성전자 005930 / SK하이닉스 000660)", max_chars=6, key="final_guide_input_key").strip()
        
    with col_add_btn:
        st.write("")
        if st.button("➕ 종목 즉시 추가", type="secondary", use_container_width=True):
            if len(input_code) == 6 and input_code.isdigit():
                token = api.get_fresh_access_token()
                if token:
                    data = api.get_realtime_price(input_code, token, default_name="조회종목")
                    if data:
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.session_state.custom_tickers[input_code] = data['name']
                        st.session_state.active_pool[input_code] = f"⭐ {data['name']}"
                        st.session_state.live_pct_map[input_code] = float(data["PrdyCtrt"])
                        st.session_state.master_name_map[input_code] = data['name']
                        
                        new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                        st.session_state.market_history[input_code] = new_row
                        
                        st.session_state["data_loaded"] = True
                        st.toast(f"🔥 [{data['name']}] 종목이 리스트에 즉시 반영되었습니다.")
                        time.sleep(0.2)
                        st.rerun()
                    else:
                        st.error("종목 정보를 가져오지 못했습니다. 코드를 재확인하십시오.")
            else:
                st.warning("정확한 숫자 6자리 코드를 입력하십시오.")
                
    with col_clear_btn:
        st.write("")
        if st.button("❌ 추가 종목 전체 삭제", use_container_width=True):
            st.session_state.custom_tickers = {}
            run_dynamic_market_scan(api)
            st.toast("추가 관심 리스트 리셋 완료")
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
            name_backup = st.session_state.master_name_map.get(ticker, st.session_state.active_pool[ticker].replace("⭐ ", ""))
            data = api.get_realtime_price(ticker, master_token, default_name=name_backup)
            if data:
                new_row = pd.DataFrame([{"Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])}], index=[pd.to_datetime(current_time)])
                st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
                st.session_state.market_history[ticker] = pd.concat([st.session_state.market_history.get(ticker, pd.DataFrame()), new_row]).tail(20)
            time.sleep(0.25)
        st.session_state["data_loaded"] = True
        st.rerun()

if col_btn2.button("🧹 리셋 + 실시간 주도주 새로 발굴", use_container_width=True):
    run_dynamic_market_scan(api)
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------
# 🖥️ 고정 20선 실시간 대시보드 테이블 뷰어
# -----------------------------------------------------------------
if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    for ticker, name in st.session_state.active_pool.items():
        df = st.session_state.market_history.get(ticker)
        if df is None or df.empty: continue
        
        latest = df.iloc[-1]
        growth_rate = float(st.session_state.live_pct_map.get(ticker, 0.0))
        vwap_val = float(df["Close"].mean())
        
        clean_name = st.session_state.master_name_map.get(ticker, name)
        if "⭐" in name and "⭐" not in clean_name:
            clean_name = f"⭐ {clean_name}"
        
        ranking_list.append({
            "code": str(ticker), "name": str(clean_name), "price": int(latest["Close"]),
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
    st.info("⏳ 시장 실시간 데이터를 20선 그리드에 맞추어 재정렬 중입니다.")
