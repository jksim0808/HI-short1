def get_fresh_access_token(self, force_refresh=False):
        now = datetime.now(tz=timezone.utc)
        if not force_refresh and self._token_cache["token"] and self._token_cache["expires_at"] > now:
            return self._token_cache["token"]

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        payload = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        resp = self.session.post(url, json=payload, timeout=3.0)
        
        if resp is not None:
            data = resp.json()
            if resp.status_code == 200:
                token = data.get("access_token")
                expired_at_str = data.get("token_expired_at")
                if expired_at_str:
                    try:
                        exp_dt = datetime.strptime(expired_at_str.strip(), "%Y-%m-%d %H:%M:%S")
                        expires_at = exp_dt.replace(tzinfo=timezone.utc)
                    except:
                        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(data.get("expires_in", 86400)))
                else:
                    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=int(data.get("expires_in", 86400)))
                
                self._token_cache = {"token": token, "expires_at": expires_at}
                return token
            else:
                # 🎯 [핵심 디버깅 추가] 한투 서버가 거절한 진짜 이유를 Streamlit 화면에 경고창으로 표시
                err_code = data.get("error_code", "알 수 없음")
                err_msg = data.get("error_description", "앱키 또는 시크릿 키 불일치")
                st.error(f"❌ 한투 반환 에러 [{err_code}]: {err_msg}")
        else:
            st.error("❌ 한투 인증 서버 응답 타임아웃 (네트워크 연결 끊김)")
        return None
