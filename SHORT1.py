# =====================================================================
# test_scanner.py
# 단위 테스트 — unittest.mock 기반 (실제 API 호출 없음)
# =====================================================================
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import time
from datetime import datetime, timezone, timedelta

# ---- 테스트 대상 모듈에서 import ----
# app.py 와 같은 디렉토리에 있다고 가정
import importlib, sys, types

# Streamlit mock (import 시 st.* 호출 방지)
st_mock = MagicMock()
st_mock.secrets = MagicMock()
st_mock.secrets.get = MagicMock(return_value="")
sys.modules["streamlit"] = st_mock

# plotly mock
for mod in ["plotly", "plotly.graph_objects", "plotly.subplots"]:
    sys.modules.setdefault(mod, MagicMock())

from app import (
    safe_float, extract_six_digits, is_noise_name,
    KoreaInvestmentOfficialAPI, RetrySession,
    BACKUP_MASTER_POOL, RESTRICTED_STAT
)


# =====================================================================
# safe_float 테스트
# =====================================================================
class TestSafeFloat(unittest.TestCase):

    def test_basic_float(self):
        self.assertAlmostEqual(safe_float("1234.56"), 1234.56)

    def test_comma_separated(self):
        self.assertAlmostEqual(safe_float("1,234,567"), 1234567.0)

    def test_plus_sign(self):
        self.assertAlmostEqual(safe_float("+5.23"), 5.23)

    def test_negative_sign(self):
        # 음수 부호 제거 후 양수로 반환 (현재 구현 기준)
        self.assertAlmostEqual(safe_float("-3.14"), 3.14)

    def test_percent(self):
        self.assertAlmostEqual(safe_float("12.5%"), 12.5)

    def test_none(self):
        self.assertEqual(safe_float(None), 0.0)

    def test_empty(self):
        self.assertEqual(safe_float(""), 0.0)

    def test_garbage(self):
        self.assertEqual(safe_float("N/A"), 0.0)

    def test_default_value(self):
        self.assertEqual(safe_float(None, default=-1.0), -1.0)

    def test_integer(self):
        self.assertAlmostEqual(safe_float(42), 42.0)

    def test_zero_string(self):
        self.assertAlmostEqual(safe_float("0"), 0.0)

    def test_scientific_notation(self):
        self.assertAlmostEqual(safe_float("1.5e3"), 1500.0)


# =====================================================================
# extract_six_digits 테스트
# =====================================================================
class TestExtractSixDigits(unittest.TestCase):

    def test_pure_six_digits(self):
        self.assertEqual(extract_six_digits("005930"), "005930")

    def test_with_prefix_suffix(self):
        self.assertEqual(extract_six_digits("KR005930KR"), "005930")

    def test_none_input(self):
        self.assertIsNone(extract_six_digits(None))

    def test_empty_string(self):
        self.assertIsNone(extract_six_digits(""))

    def test_five_digits(self):
        self.assertIsNone(extract_six_digits("05930"))

    def test_seven_digits(self):
        # 7자리 연속은 6자리 경계가 없으므로 None
        self.assertIsNone(extract_six_digits("0059301"))

    def test_space_separated(self):
        self.assertEqual(extract_six_digits("code 005930 end"), "005930")


# =====================================================================
# is_noise_name 테스트
# =====================================================================
class TestIsNoiseName(unittest.TestCase):

    def test_kodex(self):
        self.assertTrue(is_noise_name("KODEX200"))

    def test_tiger(self):
        self.assertTrue(is_noise_name("TIGER 반도체"))

    def test_spac(self):
        self.assertTrue(is_noise_name("삼성스팩7호"))

    def test_normal_stock(self):
        self.assertFalse(is_noise_name("삼성전자"))

    def test_reit(self):
        self.assertTrue(is_noise_name("맥쿼리인프라리츠"))

    def test_empty(self):
        self.assertFalse(is_noise_name(""))

    def test_none(self):
        self.assertFalse(is_noise_name(None))

    def test_lowercase_etf(self):
        self.assertTrue(is_noise_name("kodex 레버리지"))


# =====================================================================
# RetrySession 테스트
# =====================================================================
class TestRetrySession(unittest.TestCase):

    def setUp(self):
        self.retry = RetrySession()

    @patch("requests.Session.request")
    def test_success_on_first_attempt(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.return_value = mock_resp
        resp = self.retry.get("http://test.com/api")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_req.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch("requests.Session.request")
    def test_retry_on_429(self, mock_req, mock_sleep):
        fail_resp = MagicMock(); fail_resp.status_code = 429
        ok_resp   = MagicMock(); ok_resp.status_code   = 200
        mock_req.side_effect = [fail_resp, ok_resp]
        resp = self.retry.get("http://test.com/api")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_req.call_count, 2)
        mock_sleep.assert_called()

    @patch("time.sleep", return_value=None)
    @patch("requests.Session.request")
    def test_max_retries_exceeded(self, mock_req, mock_sleep):
        fail_resp = MagicMock(); fail_resp.status_code = 503
        mock_req.return_value = fail_resp
        resp = self.retry.get("http://test.com/api")
        self.assertIsNone(resp)

    @patch("requests.Session.request", side_effect=__import__("requests").ConnectionError("fail"))
    def test_connection_error_returns_none(self, mock_req):
        resp = self.retry.get("http://test.com/api")
        self.assertIsNone(resp)

    @patch("time.sleep", return_value=None)
    @patch("requests.Session.request", side_effect=__import__("requests").Timeout)
    def test_timeout_returns_none_after_retries(self, mock_req, mock_sleep):
        resp = self.retry.get("http://test.com/api")
        self.assertIsNone(resp)


# =====================================================================
# KoreaInvestmentOfficialAPI — 토큰 캐시 테스트
# =====================================================================
class TestTokenCache(unittest.TestCase):

    def _make_api(self) -> KoreaInvestmentOfficialAPI:
        api = KoreaInvestmentOfficialAPI(app_key="TEST_KEY", app_secret="TEST_SECRET")
        return api

    def _mock_token_response(self, token="MOCK_TOKEN", expires_in=86400, expired_at=None):
        resp = MagicMock()
        resp.status_code = 200
        payload = {"access_token": token, "token_type": "Bearer", "expires_in": expires_in}
        if expired_at:
            payload["token_expired_at"] = expired_at
        resp.json.return_value = payload
        return resp

    @patch.object(RetrySession, "post")
    def test_token_issued_on_first_call(self, mock_post):
        mock_post.return_value = self._mock_token_response()
        api = self._make_api()
        token = api.get_fresh_access_token()
        self.assertEqual(token, "MOCK_TOKEN")
        self.assertEqual(mock_post.call_count, 1)

    @patch.object(RetrySession, "post")
    def test_token_cached_on_second_call(self, mock_post):
        mock_post.return_value = self._mock_token_response()
        api = self._make_api()
        api.get_fresh_access_token()
        api.get_fresh_access_token()  # 두번째 호출 — 캐시 사용
        self.assertEqual(mock_post.call_count, 1)

    @patch.object(RetrySession, "post")
    def test_expired_token_triggers_refresh(self, mock_post):
        mock_post.return_value = self._mock_token_response()
        api = self._make_api()
        api.get_fresh_access_token()
        # 만료 시각을 과거로 조작
        api._token_cache["expires_at"] = datetime.now(tz=timezone.utc) - timedelta(seconds=100)
        api.get_fresh_access_token()  # 재발급 트리거
        self.assertEqual(mock_post.call_count, 2)

    @patch.object(RetrySession, "post")
    def test_force_refresh_ignores_cache(self, mock_post):
        mock_post.return_value = self._mock_token_response()
        api = self._make_api()
        api.get_fresh_access_token()
        api.get_fresh_access_token(force_refresh=True)  # 강제 갱신
        self.assertEqual(mock_post.call_count, 2)

    @patch.object(RetrySession, "post")
    def test_token_expired_at_string_parsed(self, mock_post):
        future = (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        mock_post.return_value = self._mock_token_response(expired_at=future)
        api = self._make_api()
        api.get_fresh_access_token()
        self.assertIsNotNone(api._token_cache["expires_at"])

    @patch.object(RetrySession, "post", return_value=None)
    def test_token_returns_none_on_network_failure(self, _):
        api = self._make_api()
        result = api.get_fresh_access_token()
        self.assertIsNone(result)

    @patch.object(RetrySession, "post")
    def test_token_returns_none_on_http_error(self, mock_post):
        err_resp = MagicMock(); err_resp.status_code = 401; err_resp.text = "Unauthorized"
        mock_post.return_value = err_resp
        api = self._make_api()
        result = api.get_fresh_access_token()
        self.assertIsNone(result)


# =====================================================================
# KoreaInvestmentOfficialAPI — get_market_leading_tickers 테스트
# =====================================================================
class TestGetMarketLeadingTickers(unittest.TestCase):

    def _make_api(self):
        return KoreaInvestmentOfficialAPI(app_key="K", app_secret="S")

    def _make_item(self, ticker, name):
        return {"mksc_shrn_iscd": ticker, "hts_kor_isnm": name}

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_normal_response(self, mock_get):
        mock_get.return_value = {"output": [
            self._make_item("005930", "삼성전자"),
            self._make_item("000660", "SK하이닉스")
        ]}
        api   = self._make_api()
        pool  = api.get_market_leading_tickers("TOKEN")
        codes = [t for t, _ in pool]
        self.assertIn("005930", codes)
        self.assertIn("000660", codes)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_noise_filtered(self, mock_get):
        mock_get.return_value = {"output": [
            self._make_item("069500", "KODEX200"),
            self._make_item("005930", "삼성전자")
        ]}
        api  = self._make_api()
        pool = api.get_market_leading_tickers("TOKEN")
        codes = [t for t, _ in pool]
        self.assertNotIn("069500", codes)
        self.assertIn("005930", codes)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get", return_value=None)
    def test_fallback_to_backup_on_api_fail(self, _):
        api  = self._make_api()
        pool = api.get_market_leading_tickers("TOKEN")
        self.assertEqual(pool, BACKUP_MASTER_POOL)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_empty_output_fallback(self, mock_get):
        mock_get.return_value = {"output": []}
        api  = self._make_api()
        pool = api.get_market_leading_tickers("TOKEN")
        self.assertEqual(pool, BACKUP_MASTER_POOL)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_dict_output_normalized(self, mock_get):
        # output이 dict인 경우 리스트로 정규화
        mock_get.return_value = {"output": self._make_item("005930", "삼성전자")}
        api  = self._make_api()
        pool = api.get_market_leading_tickers("TOKEN")
        codes = [t for t, _ in pool]
        self.assertIn("005930", codes)


# =====================================================================
# KoreaInvestmentOfficialAPI — get_realtime_price 테스트
# =====================================================================
class TestGetRealtimePrice(unittest.TestCase):

    def _make_api(self):
        return KoreaInvestmentOfficialAPI(app_key="K", app_secret="S")

    def _normal_output(self, ticker="005930", name="삼성전자", price="72000", ctrt="1.50", stat="00"):
        return {
            "output": {
                "hts_kor_isnm":       name,
                "stck_prpr":          price,
                "stck_hgpr":          "73000",
                "stck_lwpr":          "71000",
                "accl_tr_vol":        "1234567",
                "prdy_ctrt":          ctrt,
                "iscd_stat_cls_code": stat
            }
        }

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_normal_price_parsed(self, mock_get):
        mock_get.return_value = self._normal_output()
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data["Close"],    72000.0)
        self.assertAlmostEqual(data["High"],     73000.0)
        self.assertAlmostEqual(data["Low"],      71000.0)
        self.assertAlmostEqual(data["PrdyCtrt"], 1.50)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_restricted_stock_detected(self, mock_get):
        mock_get.return_value = self._normal_output(stat="51")
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertTrue(data["is_restricted"])

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_zero_price_returns_none(self, mock_get):
        mock_get.return_value = self._normal_output(price="0")
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertIsNone(data)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get", return_value=None)
    def test_api_fail_returns_none(self, _):
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertIsNone(data)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_comma_in_price_handled(self, mock_get):
        mock_get.return_value = self._normal_output(price="72,000")
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data["Close"], 72000.0)

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_default_name_used_when_hts_empty(self, mock_get):
        out = self._normal_output()
        out["output"]["hts_kor_isnm"] = ""
        mock_get.return_value = out
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN", default_name="기본종목명")
        self.assertEqual(data["name"], "기본종목명")

    @patch.object(KoreaInvestmentOfficialAPI, "_api_get")
    def test_output1_fallback(self, mock_get):
        # output 없이 output1에 데이터가 있는 경우
        mock_get.return_value = {
            "output1": {
                "hts_kor_isnm": "삼성전자", "stck_prpr": "72000",
                "stck_hgpr": "73000",       "stck_lwpr": "71000",
                "accl_tr_vol": "1000000",   "prdy_ctrt": "1.50",
                "iscd_stat_cls_code": "00"
            }
        }
        api  = self._make_api()
        data = api.get_realtime_price("005930", "TOKEN")
        self.assertIsNotNone(data)

    def test_no_token_returns_none(self):
        api  = self._make_api()
        data = api.get_realtime_price("005930", token="")
        self.assertIsNone(data)


# =====================================================================
# 엔트리포인트
# =====================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
