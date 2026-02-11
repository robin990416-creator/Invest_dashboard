import streamlit as st
import requests
import json
import pandas as pd
import time

st.set_page_config(page_title="주식 투자 대시보드", layout="wide", page_icon="📈")
st.title("📈 내 주식 투자 현황 (국장 + 미장)")

# ==========================================
# [설정] Secrets 로드
# ==========================================
try:
    # secrets.toml 파일에 [kis] 섹션이 있어야 합니다.
    IS_MOCK = st.secrets["kis"]["IS_MOCK"]
    URL_BASE = "https://openapivts.koreainvestment.com:29443" if IS_MOCK else "https://openapi.koreainvestment.com:9443"
    APP_KEY = st.secrets["kis"]["APP_KEY"]
    APP_SECRET = st.secrets["kis"]["APP_SECRET"]
    CANO = st.secrets["kis"]["CANO"]
    ACNT_PRDT_CD = "01"
except Exception as e:
    st.error(f"⚠️ 설정 로드 실패: Secrets 설정을 확인해주세요.\n에러 내용: {e}")
    st.stop()

# ==========================================
# [핵심] 토큰 발급 및 캐싱 (30분 유지 -> 403 에러 해결)
# ==========================================
@st.cache_data(ttl=1800) 
def get_cached_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            return res.json()["access_token"]
        else:
            st.error(f"❌ 토큰 발급 실패 ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        st.error(f"❌ 토큰 요청 중 에러 발생: {e}")
        return None

# ==========================================
# [API] 잔고 조회 함수
# ==========================================
# ==========================================
# [수정됨] 500 에러 상세 메시지 출력 기능 추가
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
            
            # [수정] 200 OK가 아니면 에러 내용 원본을 출력
            if res.status_code != 200:
                st.error(f"❌ 국장 조회 실패 (Status: {res.status_code})")
                st.code(res.text)  # <--- 여기가 에러 원인을 보여줍니다!
                return [], 0, 0
                
            json_data = res.json()
            # API 내부 로직 에러 체크
            if json_data.get('rt_cd') != '0':
                 st.error(f"❌ API 로직 에러: {json_data.get('msg1')}")
                 st.code(json_data)

            out1 = json_data.get('output1', [])
            out2 = json_data.get('output2', [])
            
            for row in out1:
                qty = int(row['hldg_qty'])
                if qty > 0:
                    data.append({
                        "종목명": row['prdt_name'], "수량": qty,
                        "현재가": float(row['prpr']), "평단가": float(row['pchs_avg_pric']),
                        "수익률(%)": float(row['evlu_pfls_rt']), "평가손익": int(row['evlu_pfls_amt'])
                    })
            if out2:
                total_asset = float(out2[0]['tot_evlu_amt'])
                total_profit = float(out2[0]['evlu_pfls_smtl_amt'])

        elif market == "US":
             # (미장 코드는 기존과 동일, 생략)
             pass 

    except Exception as e:
        st.error(f"⚠️ 데이터 처리 오류: {e}")
        
    return data, total_asset, total_profit

# ==========================================
# [UI] 화면 구성
# ==========================================
if st.button("🔄 새로고침 (캐시 초기화)"):
    st.cache_data.clear()
    st.rerun()

# 토큰 가져오기 (캐시됨)
token = get_cached_token()

if not token:
    st.warning("⏳ 토큰 발급 중... 잠시만 기다려주세요.")
    st.stop()

tab1, tab2 = st.tabs(["🇰🇷 국내 주식 (KR)", "🇺🇸 미국 주식 (US)"])

# 1. 국장 탭
with tab1:
    d, a, p = get_stock_balance(token, "KR")
    
    # 상단 요약 카드
    col1, col2 = st.columns(2)
    col1.metric("총 평가 자산", f"{a:,.0f} 원")
    col2.metric("총 평가 손익", f"{p:,.0f} 원", delta=f"{p:,.0f} 원", delta_color="normal")
    
    st.divider()
    
    if d:
        df = pd.DataFrame(d)
        st.dataframe(
            df.style.format({
                "현재가": "{:,.0f}", "평단가": "{:,.0f}", 
                "수익률(%)": "{:+.2f}", "평가손익": "{:,.0f}"
            }).map(lambda x: f"color: {'red' if x > 0 else 'blue'}", subset=['수익률(%)', '평가손익']),
            use_container_width=True,
            height=500
        )
    else:
        st.info("💡 보유 중인 국내 주식이 없습니다.")

# 2. 미장 탭
with tab2:
    d, a, p = get_stock_balance(token, "US")
    
    if d:
        df = pd.DataFrame(d)
        # 미장 총합 계산 (단순 합산)
        total_us_profit = df['평가손익($)'].sum()
        
        st.metric("미국 주식 총 손익 ($)", f"{total_us_profit:,.2f}", delta=f"{total_us_profit:,.2f}")
        st.divider()
        
        st.dataframe(
            df.style.format({
                "현재가($)": "{:,.2f}", "평단가($)": "{:,.2f}", 
                "수익률(%)": "{:+.2f}", "평가손익($)": "{:,.2f}"
            }).map(lambda x: f"color: {'red' if x > 0 else 'blue'}", subset=['수익률(%)', '평가손익($)']),
            use_container_width=True,
            height=500
        )
    else:
        st.info("💡 보유 중인 미국 주식이 없습니다.")
