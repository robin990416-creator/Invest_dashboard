import streamlit as st
import requests
import json
import pandas as pd
import time
import pyupbit

st.set_page_config(page_title="통합 투자 대시보드", layout="wide")
st.title("🚀 내 모든 투자 현황")

# ==========================================
# [설정] Secrets 로드
# ==========================================
try:
    IS_MOCK = st.secrets["kis"]["IS_MOCK"]
    URL_BASE = "https://openapivts.koreainvestment.com:29443" if IS_MOCK else "https://openapi.koreainvestment.com:9443"
    APP_KEY = st.secrets["kis"]["APP_KEY"]
    APP_SECRET = st.secrets["kis"]["APP_SECRET"]
    CANO = st.secrets["kis"]["CANO"]
    ACNT_PRDT_CD = "01"
    
    UPBIT_ACCESS = st.secrets["upbit"]["ACCESS_KEY"]
    UPBIT_SECRET = st.secrets["upbit"]["SECRET_KEY"]
except Exception as e:
    st.error(f"⚠️ 설정 로드 실패: {e}")
    st.stop()

# ==========================================
# [핵심 수정] 토큰 캐싱 (30분간 저장)
# ==========================================
@st.cache_data(ttl=1800)  # <-- 이 부분이 핵심! (1800초 = 30분 동안 재사용)
def get_cached_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            return res.json()["access_token"]
        else:
            return None
    except:
        return None

# ==========================================
# [API 함수] 주식 (캐시된 토큰 사용)
# ==========================================
def get_stock_balance(token, market="KR"):
    if not token: return [], 0, 0
    
    headers = {
        "content-type": "application/json", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "VTTC8434R" if (IS_MOCK and market=="KR") else ("TTTC8434R" if market=="KR" else ("VTTS3012R" if IS_MOCK else "TTTS3012R")),
        "custtype": "P"
    }
    
    data = []
    total_asset = 0.0
    total_profit = 0.0

    try:
        if market == "KR":
            params = {
                "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "",
                "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
            }
            res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params)
            
            if res.status_code == 200:
                out1 = res.json().get('output1', [])
                out2 = res.json().get('output2', [])
                for row in out1:
                    if int(row['hldg_qty']) > 0:
                        data.append({
                            "종목명": row['prdt_name'], "수량": int(row['hldg_qty']),
                            "현재가": float(row['prpr']), "평단가": float(row['pchs_avg_pric']),
                            "수익률(%)": float(row['evlu_pfls_rt']), "평가손익": int(row['evlu_pfls_amt'])
                        })
                if out2:
                    total_asset = float(out2[0]['tot_evlu_amt'])
                    total_profit = float(out2[0]['evlu_pfls_smtl_amt'])

        elif market == "US":
            exchanges = ["NAS", "NYS", "AMS"]
            for exch in exchanges:
                params = {
                    "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": exch,
                    "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""
                }
                res = requests.get(f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance", headers=headers, params=params)
                if res.status_code == 200:
                    out1 = res.json().get('output1', [])
                    for row in out1:
                        qty = float(row['ovrs_cblc_qty'])
                        if qty > 0:
                            profit = float(row['frcr_evlu_pfls_amt'])
                            buy = float(row['frcr_pchs_amt1'])
                            roi = (profit/buy*100) if buy > 0 else 0
                            data.append({
                                "종목명": row['ovrs_item_name'], "수량": qty,
                                "현재가($)": float(row['ovrs_now_pric1']), "평단가($)": float(row['ovrs_pchs_avg_pric']),
                                "수익률(%)": roi, "평가손익($)": profit
                            })
    except: pass
    return data, total_asset, total_profit

# ==========================================
# [API 함수] 코인
# ==========================================
def get_crypto_balance():
    try:
        upbit = pyupbit.Upbit(UPBIT_ACCESS, UPBIT_SECRET)
        # 에러 체크를 위해 try-except 안에서 호출
        balances = upbit.get_balances()
        
        # IP 에러 체크
        if isinstance(balances, dict) and 'error' in balances:
            return [], 0, 0, balances['error']['message']
            
        data = []
        total_krw = 0.0
        tickers = []
        
        for b in balances:
            if b['currency'] == 'KRW': total_krw += float(b['balance'])
            else: tickers.append(f"KRW-{b['currency']}")
        
        curr_prices = pyupbit.get_current_price(tickers) if tickers else {}
        total_asset = total_krw
        total_buy = 0.0
        
        for b in balances:
            if b['currency'] == 'KRW': continue
            ticker = f"KRW-{b['currency']}"
            qty = float(b['balance'])
            avg = float(b['avg_buy_price'])
            curr = curr_prices.get(ticker, avg)
            
            buy_amt = qty * avg
            eval_amt = qty * curr
            profit = eval_amt - buy_amt
            roi = (profit/buy_amt*100) if buy_amt > 0 else 0
            
            total_asset += eval_amt
            total_buy += buy_amt
            data.append({
                "코인명": b['currency'], "수량": qty, "현재가": curr,
                "평단가": avg, "수익률(%)": roi, "평가손익": profit
            })
            
        return data, total_asset, total_asset - (total_buy + total_krw), None
    except Exception as e:
        return [], 0, 0, str(e)

# ==========================================
# [Main UI]
# ==========================================
if st.button("🔄 새로고침"):
    st.cache_data.clear() # 강제 새로고침 시 캐시 삭제
    st.rerun()

token = get_cached_token() # 캐시된 토큰 사용

if not token:
    st.warning("⏳ 토큰 발급 대기 중... (잠시 후 새로고침하세요)")

tab1, tab2, tab3 = st.tabs(["🇰🇷 국장", "🇺🇸 미장", "🪙 코인"])

with tab1:
    if token:
        d, a, p = get_stock_balance(token, "KR")
        c1, c2 = st.columns(2)
        c1.metric("총 자산", f"{a:,.0f}원")
        c2.metric("손익", f"{p:,.0f}원", delta=f"{p:,.0f}")
        if d: st.dataframe(pd.DataFrame(d).style.format({"현재가":"{:,.0f}","수익률(%)":"{:+.2f}","평가손익":"{:,.0f}"}).map(lambda x: f"color:{'red' if x>0 else 'blue'}", subset=['수익률(%)','평가손익']), use_container_width=True)

with tab2:
    if token:
        d, a, p = get_stock_balance(token, "US")
        if d: st.dataframe(pd.DataFrame(d).style.format({"현재가($)":"{:,.2f}","수익률(%)":"{:+.2f}","평가손익($)":"{:,.2f}"}).map(lambda x: f"color:{'red' if x>0 else 'blue'}", subset=['수익률(%)','평가손익($)']), use_container_width=True)

with tab3:
    d, a, p, err = get_crypto_balance()
    if err:
        st.error(f"⚠️ 업비트 오류
