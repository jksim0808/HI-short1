import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time

# =================================================================
# 🔑 [모의투자 계좌 설정]
# =================================================================
APP_KEY = st.secrets.get("HANTU_APP_KEY", "YOUR_APP_KEY")
APP_SECRET = st.secrets.get("HANTU_APP_SECRET", "YOUR_APP_SECRET")
MOCK_FLAG = True  # 👈 모의투자용 고정

class KoreaInvestmentAPI:
    def __init__(self):
        self.base_url = "https://openapivts.koreainvestment.com:29443" if MOCK_FLAG else "https://openapi.koreainvestment.com:9443"
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET

    def get_access_token(self):
        """ 토큰 발급 시도 및 서버 응답 실시간 진단 """
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json"}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            response = requests.post(url, headers=headers, json=data)
            
            # 서버 응답 상태 저장 (디버깅용)
            st.session_state["token_http_status"] = response.status_code
            st.session_state["token_server_msg"] = response.text
            
            if response.status_code == 200:
                token = response.json().get("access_token")
                st.session_state.api_access_token = token
                return token
            return None
        except Exception as e:
            st.session_state["token_server_msg"] = f"접속 불능 에러: {str(e)}"
            return None

    def get_realtime_price(self, ticker):
        """ 현재가 조회 시도 및 서버 응답 실시간 진단 """
        access_token = self.get_access_token()
        if not access_token:
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0, "Status": "토큰 없음"}
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        target_tr_id = "VTST01010200" # 모의투자 전용 TR ID
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": target_tr_id 
        }
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        try:
            response = requests.get(url, headers=headers, params=params)
            st.session_state["price_http_status"] = response.status_code
            st.session_state["price_server_msg"] = response.text
            
            if response.status_code == 200:
                res_data = response.json().get("output", {})
                if res_data and res_data.get("stck_prpr"):
                    current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                    high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                    low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                    volume = float(str(res_data.get("accl_tr_vol", 0)).strip())
                    return {"Close": current_price, "High": high_price, "Low": low_price, "Volume": volume, "Status": "정상"}
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0, "Status": "조회 실패"}
        except Exception as e:
            st.session_state["price_server_msg"] = f"시세조회 내부 에러: {str(e)}"
            return {"Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 1000.0, "Status": "에러 발생"}

# =================================================================
# 대시보드 및 레이더 작동
# =================================================================
st.set_page_config(page_title="실시간 진단 레이더", layout="centered")

st.title("🚨 한투 API 통신 진단 레이더")
st.caption("이 화면에 뜨는 메시지를 보고 원인을 즉시 판별할 수 있습니다.")

# 초기화 세션 생성
if "token_server_msg" not in st.session_state: st.session_state["token_server_msg"] = "대기 중"
if "price_server_msg" not in st.session_state: st.session_state["price_server_msg"] = "대기 중"

# 📡 실시간 진단 상태판 생성
with st.expander("🔌 [필독] 한투 서버 응답 데이터 실시간 디버깅창", expanded=True):
    st.markdown("### 1. 토큰(인증) 서버 응답")
    st.code(f"HTTP 상태코드: {st.session_state.get('token_http_status', 'N/A')}\n내용: {st.session_state['token_server_msg']}")
    
    st.markdown("### 2. 현재가 조회 서버 응답")
    st.code(f"HTTP 상태코드: {st.session_state.get('price_http_status', 'N/A')}\n내용: {st.session_state['price_server_msg']}")

st.markdown("---")

# 단일 종목 테스트 가동 (가장 대중적인 삼성전자로 테스트)
test_ticker = "005930"
api = KoreaInvestmentAPI()

if st.button("🔄 한국투자증권 실시간 신호 강제 1회 테스트", use_container_width=True):
    st.write("🔄 한투 서버에 접속 시도 중...")
    res = api.get_realtime_price(test_ticker)
    st.success(f"결과 리턴 완료! -> 수신된 현재가: {res['Close']:,}원 (거래량: {res['Volume']:,})")
    st.rerun()
