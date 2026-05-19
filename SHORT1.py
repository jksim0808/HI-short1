import streamlit as st
import pandas as pd, numpy as np, requests, logging
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
APP_KEY = st.secrets.get("HANTU_APP_KEY","").strip()
APP_SECRET = st.secrets.get("HANTU_APP_SECRET","").strip()

class KoreaInvestmentOfficialAPI:
    def __init__(self):
        self.base_url="https://openapi.koreainvestment.com:9443"
        self.app_key=APP_KEY; self.app_secret=APP_SECRET
        self.session=requests.Session()
        retry=Retry(total=3,backoff_factor=1,status_forcelist=[500,502,503,504])
        self.session.mount("https://",HTTPAdapter(max_retries=retry))

    def get_access_token(self):
        if "api_access_token" in st.session_state and datetime.now() < st.session_state.get("token_expire_time",datetime.min):
            return st.session_state.api_access_token
        r=self.session.post(
            f"{self.base_url}/oauth2/tokenP",
            json={"grant_type":"client_credentials","appkey":self.app_key,"appsecret":self.app_secret},
            headers={"content-type":"application/json"},
            timeout=10
        )
        j=r.json(); token=j.get("access_token")
        if token:
            st.session_state.api_access_token=token
            exp=j.get("expires_in",86400)
            st.session_state.token_expire_time=datetime.now()+timedelta(seconds=exp-300)
        return token

    def get_realtime_price(self,ticker):
        token=self.get_access_token()
        if not token: return None
        r=self.session.get(
            f"{self.base_url}/uapi/domestic-stock/v1/quoting/inquire-price",
            headers={"authorization":f"Bearer {token}","appkey":self.app_key,"appsecret":self.app_secret,"tr_id":"FHKST01010200"},
            params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":ticker},
            timeout=10
        )
        out=r.json().get("output",{})
        return {
            "Close":float(out.get("stck_prpr",0)),
            "High":float(out.get("stck_hgpr",0)),
            "Low":float(out.get("stck_lwpr",0)),
            "Volume":float(out.get("accl_tr_vol",0) or 0),
            "Source":"🔥 한투 실전망"
        }

def process_quant_signals(df):
    if len(df)<2:
        df["RSI"]=50; df["VWAP"]=df["Close"]; df["타이밍 신호"]="🟢 관망"; return df
    tp=(df.High+df.Low+df.Close)/3
    df["VWAP"]=(tp*df.Volume).cumsum()/df.Volume.replace(0,np.nan).cumsum()
    delta=df.Close.diff()
    gain=delta.clip(lower=0).rolling(14,min_periods=1).mean()
    loss=(-delta.clip(upper=0)).rolling(14,min_periods=1).mean()
    df["RSI"]=(100-100/(1+gain/(loss+1e-9))).fillna(50)
    df["타이밍 신호"]=np.where(df.RSI>82,"🚨 익절/청산","🟢 관망")
    return df

st.title("실전 수급 스캐너 (개선판)")
st.write("기존 코드 기반 안정성 개선 버전")
