# 30번 라인 근처 토큰 발급 함수 수정
async def fetch_token_async(client):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    data = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        r = await client.post(url, json=data, timeout=3.0)
        res_json = r.json()
        if "access_token" in res_json:
            return res_json.get("access_token")
        else:
            # 한투가 거절한 진짜 이유를 세션에 임시 저장
            st.session_state["token_err_msg"] = res_json.get("error_description", "앱키 또는 시크릿 키 불일치")
            return None
    except Exception as e:
        st.session_state["token_err_msg"] = f"한투 서버 통신 시간초과 (네트워크 지연): {str(e)}"
        return None

# 105번 라인 근처 update_all_prices_safe 함수 내 토큰 검증부 수정
        token = await fetch_token_async(client)
        if not token:
            err_detail = st.session_state.get("token_err_msg", "알 수 없는 인증 오류")
            st.error(f"❌ 한투 Access Token 발급 실패 원인: [ {err_detail} ]")
            st.warning("💡 조치 방법: Streamlit Secrets에 입력된 APP_KEY와 SECRET 앞뒤에 공백이나 줄바꿈이 없는지 꼭 확인해 주세요.")
            return
