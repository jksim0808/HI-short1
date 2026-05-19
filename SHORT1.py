# =================================================================
# 🏦 한투 실전/모의 자동 감지 및 교차 통신 엔진 (404 에러 완벽 방어)
# =================================================================
class KoreaInvestmentOfficialAPI:
    def __init__(self):
        # 404 에러 방지: 실전(9443) 주소를 기본으로 하되, 실패 시 모의(29443)로 자동 전환
        self.prod_url = "https://openapi.koreainvestment.com:9443"
        self.vps_url = "https://openapivts.koreainvestment.com:29443"
        self.base_url = self.prod_url # 기본값은 실전
        
        self.app_key = APP_KEY
        self.app_secret = APP_SECRET
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.session = requests.Session()

    def get_access_token(self):
        if "api_access_token" in st.session_state and st.session_state.api_access_token:
            if "token_expire_time" in st.session_state and datetime.now() < st.session_state.token_expire_time:
                return st.session_state.api_access_token
        
        # 1차 시도: 실전 서버로 인증 요청
        try:
            url = f"{self.base_url}/oauth2/tokenP"
            headers = {"content-type": "application/json", "User-Agent": self.user_agent}
            data = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
            
            response = self.session.post(url, headers=headers, json=data, timeout=5.0)
            
            # 만약 실전 주소에서 404가 나면 즉시 모의투자(vps) 주소로 영구 스위칭합니다.
            if response.status_code == 404 and self.base_url == self.prod_url:
                logger.warning("🌐 실전 서버 404 감지: 모의투자(vps) 서버로 자동 전환합니다.")
                self.base_url = self.vps_url
                url = f"{self.base_url}/oauth2/tokenP"
                response = self.session.post(url, headers=headers, json=data, timeout=5.0)

            if response.status_code != 200:
                st.session_state.last_api_error = f"🚨 [인증 실패] 계좌 설정 및 키 타입을 확인하세요. (HTTP {response.status_code})"
                return None
                
            res_json = response.json()
            token = res_json.get("access_token")
            if token:
                st.session_state.api_access_token = token
                st.session_state.token_expire_time = datetime.now() + timedelta(hours=11)
                return token
            
            st.session_state.last_api_error = f"🚨 [인증 거부] 서버 메시지: {res_json.get('msg1')}"
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [인증 시스템 예외] {str(e)}"
            return None

    def get_realtime_price(self, ticker):
        access_token = self.get_access_token()
        if not access_token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010200" if self.base_url == self.prod_url else "VTKST01010200", # 서버에 맞는 TR_ID 자동 매핑
            "custtype": "P",           
            "User-Agent": self.user_agent
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", 
            "FID_INPUT_ISCD": str(ticker).strip()
        }
        
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=5.0)
            
            if response.status_code != 200:
                st.session_state.last_api_error = f"🚨 [시세 호출 실패] 한투 응답 에러 (HTTP {response.status_code})"
                return None
                
            res_json = response.json()
            if res_json.get("rt_cd", "0") != "0":
                st.session_state.last_api_error = f"🚨 [조회 거절] {get_stock_name(ticker)}: {res_json.get('msg1')}"
                return None
                
            res_data = res_json.get("output", {})
            if res_data and res_data.get("stck_prpr"):
                current_price = float(str(res_data.get("stck_prpr")).strip().replace("-", "").replace("+", ""))
                high_price = float(str(res_data.get("stck_hgpr", current_price)).strip().replace("-", "").replace("+", ""))
                low_price = float(str(res_data.get("stck_lwpr", current_price)).strip().replace("-", "").replace("+", ""))
                
                raw_vol = str(res_data.get("accl_tr_vol", "1.0")).strip()
                volume = float(raw_vol) if raw_vol and raw_vol != "0" else 1.0
                
                # 어떤 망으로 연결되었는지 대시보드에 친절히 표시
                source_name = "한투 실전망 가동" if self.base_url == self.prod_url else "한투 모의투자망 가동"
                return {
                    "Close": current_price, "High": high_price, "Low": low_price,
                    "Volume": volume, "Source": source_name
                }
            return None
        except Exception as e:
            st.session_state.last_api_error = f"💥 [시세 예외 오류] {str(e)}"
            return None
