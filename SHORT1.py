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
                    raw_ticker = str(item.get("mksc_shrn_iscd", "")).strip()
                    name = str(item.get("hts_kor_isnm", "")).strip()
                    
                    # 숫자 6자리 종목코드 순수 추출
                    match = re.search(r'\d{6}', raw_ticker)
                    if not match: continue
                    ticker = match.group()
                    
                    if ticker and name:
                        # 노이즈 종목 원천 차단
                        noise_keywords = ["우", "스팩", "리츠", "인버스", "레버리지", "KODEX", "TIGER", "KBSTAR", "ACE", "HANARO", "SOL", "선물", "ETN"]
                        if any(k in name for k in noise_keywords): continue
                        
                        dynamic_pool[ticker] = name
                        if len(dynamic_pool) >= 20: break
                return dynamic_pool
        except:
            pass
        return {"005930": "삼성전자", "000660": "SK하이닉스"}

    # 🔥 [핵심 수정] 타겟 종목코드의 실제 현재가를 1대1로 정확하게 매칭하여 파싱
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
        # 빈칸 및 불순물 제거한 순수 코드가 들어가는지 강제 재검증
        target_code = str(ticker).strip()
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": target_code}
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=5)
            if r.status_code == 200:
                res_json = r.json()
                out = res_json.get("output")
                
                if isinstance(out, list) and len(out) > 0: out = out[0]
                elif not out or not isinstance(out, dict):
                    out = res_json.get("output1", {})
                    if isinstance(out, list) and len(out) > 0: out = out[0]
                
                if isinstance(out, dict):
                    def _clean(val):
                        if val is None or str(val).strip() == "": return 0.0
                        # 부호 제거하고 순수 숫자만 추출
                        return float(str(val).strip().replace("-", "").replace("+", ""))
                    
                    # stck_prpr가 해당 종목코드가 가지고 있는 진짜 실제 현재가입니다.
                    close_val = _clean(out.get("stck_prpr"))
                    if close_val == 0: close_val = _clean(out.get("prpr"))
                    
                    if close_val > 0:
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
# 🔄 데이터 매핑 꼬임 방지 전용 스캔 함수
# =================================================================
def run_dynamic_market_scan(api):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with st.spinner("⚡ 100% 실시간 실제 호가 데이터 동기화 중..."):
        master_token = api.get_fresh_access_token()
        if not master_token:
            st.error("🚨 한투 토큰 발급 실패.")
            return
        active_pool = api.get_market_leading_tickers(master_token)
    
    # 꼬임 방지를 위해 세션 데이터 완전 초기화 후 재할당
    st.session_state.active_pool = active_pool
    st.session_state.market_history = {}
    st.session_state.live_pct_map = {}
    
    success_count = 0
    st.markdown("### 🔍 종목별 1:1 리얼타임 호가 매칭 중")
    
    for ticker, name in active_pool.items():
        data, server_msg = api.get_realtime_price(ticker, master_token)
        
        if data:
            success_count += 1
            new_row = pd.DataFrame([{
                "Close": float(data["Close"]), "High": float(data["High"]), "Low": float(data["Low"]), "Volume": float(data["Volume"])
            }], index=[pd.to_datetime(current_time)])
            
            st.session_state.live_pct_map[ticker] = float(data["PrdyCtrt"])
            st.session_state.market_history[ticker] = new_row
        else:
            st.warning(f"⚠️ {name}({ticker}) 데이터 왜곡 차단을 위해 일시 제외: {server_msg}")
        time.sleep(0.35) # 서버 과부하 방지 슬롯
        
    if success_count > 0:
        st.session_state["data_loaded"] = True
        st.toast("🔥 실제 가격 100% 매핑 완료!", icon="⚡")

# =================================================================
# 🖥️ UI 구성
# =================================================================
st.set_page_config(page_title="실시간 거래대금 수급 스캐너 20", layout="wide")
st.title("🎯 AI 장중 거래대금 상위 20선 실시간 동적 스캐너")
st.caption("실제 호가창 현재가 매핑 꼬임 현상 완벽 박멸 버전")

if "market_history" not in st.session_state: st.session_state.market_history = {}
if "live_pct_map" not in st.session_state: st.session_state.live_pct_map = {}
if "active_pool" not in st.session_state: st.session_state.active_pool = {}

api = KoreaInvestmentOfficialAPI()
col_btn1, col_btn2, _ = st.columns([2, 2, 4])

if col_btn1.button("⚡ 현재 종목 수급 동기화", type="primary", use_container_width=True):
    if not st.session_state.active_pool:
        run_dynamic_market_scan(api)
    else:
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

if st.session_state.get("data_loaded", False) and st.session_state.market_history:
    ranking_list = []
    
    # 꼬임 방지를 위해 현재 세션에 살아있는 종목코드로만 매핑 진행
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
        
        st.subheader("🔥 실시간 돈 몰리는 정예 20선 (실제 호가창 기준)")
        
        display_rows = []
        for rank, row in enumerate(ranking_df.itertuples(), 1):
            if row.growth >= 10.0: signal = "🔥 상한가 도전 / 초급등 수급 (매수)"
            elif row.growth > 4.0: signal = "⚡ 거래량 폭발 돌파 (매수)"
            elif row.growth > 0.5: signal = "🟢 수급 우상향 추종 (보유)"
            elif row.growth < -3.0: signal = "🚨 단기 폭락 탈출 (대대피)"
            else: signal = "⚪ 숨고르기 (관망)"
            
            if row.data_count > 1:
                vwap_text = f"{row.vwap:,} 원"
                gap_text = f"{int(row.gap):+,}원"
            else:
                estimated_prev = row.price / (1 + (row.growth / 100))
                est_gap = row.price - estimated_prev
                vwap_text = "누적 계산중"
                gap_text = f"{int(est_gap):+,}원 (당일방향)"
                
            display_rows.append({
                "순위": f"{rank}위", "종목코드": row.code, "종목명": row.name, "실제 현재가": f"{row.price:,} 원",
                "단기 이평선": vwap_text, "당일 등락률": f"{row.growth:+.2f}%",
                "이평선 격차": gap_text, "실시간 단타 시그널": signal
            })
        
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
else:
    st.info("⏳ 시스템 대기 중입니다. 버튼을 눌러 실제 현재가와 동기화된 대장주를 수집하십시오.")
