# ==============================================================================
# 🧩 英文重組練習旗艦版 V1.7.2
# ==============================================================================
import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "1.7.2"

st.set_page_config(page_title=f"英文重組旗艦版 V{VERSION}", layout="centered")

# --- 1. 連線 Google Sheets ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CSS 樣式 ---
st.markdown(f"""
    <style>
    @keyframes marquee {{ 0% {{ transform: translateX(100%); }} 100% {{ transform: translateX(-100%); }} }}
    .marquee-container {{ background: #333; color: #00ff00; padding: 5px 0; overflow: hidden; white-space: nowrap; }}
    .marquee-text {{ display: inline-block; animation: marquee 20s linear infinite; font-size: 16px; }}
    .hint-box {{ background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; }}
    </style>
""", unsafe_allow_html=True)

# --- 3. 核心功能函數 ---

@st.cache_data(ttl=10)
def load_all_data():
    try:
        # 強制將所有欄位讀取為字串，避免 1111 變成 1111.0
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        return df_q, df_s
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return None, None

def log_event(action_type, detail="", result="-", duration=0):
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qid = st.session_state.get('current_qid', "N/A")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": qid, "動作": action_type,
            "內容": detail, "結果": result, "費時": duration
        }])
        # 讀取現有 logs 並合併
        old_logs = conn.read(worksheet="logs", ttl=0)
        updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
        conn.update(worksheet="logs", data=updated_logs)
    except: pass

# --- 4. 登入邏輯 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🧩 學生學習系統登入")
    
    col1, col2 = st.columns([1, 4])
    col1.markdown("### EA")
    input_id = col2.text_input("帳號 (4位數字)", max_chars=4)
    input_pw = st.text_input("密碼 (4位數字)", type="password", max_chars=4)
    
    if st.button("確認登入", type="primary", use_container_width=True):
        df_q, df_s = load_all_data()
        if df_s is not None:
            # 清洗資料：轉字串、去空白、去小數點 (針對 Excel 轉入的數字)
            df_s['帳號_clean'] = df_s['帳號'].astype(str).str.split('.').str[0].str.strip()
            df_s['密碼_clean'] = df_s['密碼'].astype(str).str.split('.').str[0].str.strip()
            
            user = df_s[df_s['帳號_clean'] == str(input_id).strip()]
            
            if not user.empty:
                if str(user.iloc[0]['密碼_clean']) == str(input_pw).strip():
                    st.session_state.logged_in = True
                    st.session_state.user_id = f"EA{input_id}"
                    st.session_state.user_name = user.iloc[0]['姓名']
                    st.session_state.group_id = user.iloc[0]['分組']
                    st.rerun()
                else:
                    st.error("密碼錯誤")
            else:
                st.error("找不到帳號，請檢查學生名單")
    st.stop()

# --- 5. 正式練習畫面 ---
# (跑馬燈顯示)
try:
    logs = conn.read(worksheet="logs", ttl=5)
    recent = logs[logs['結果'] == '✅'].tail(3)
    marquee_text = " | ".join([f"🔥 {r['姓名']}({r['分組']}) 答對了 {r['題目ID']}!" for _, r in recent.iterrows()])
    if marquee_text:
        st.markdown(f'<div class="marquee-container"><div class="marquee-text">{marquee_text}</div></div>', unsafe_allow_html=True)
except: pass

df_q, _ = load_all_data()

# 側邊欄
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    st.write(f"帳號: {st.session_state.user_id}")
    st.write(f"分組: {st.session_state.group_id}")
    if st.button("🚪 登出"):
        st.session_state.logged_in = False
        st.rerun()

# 練習邏輯 (延續 V1.6.7)
if 'q_idx' not in st.session_state:
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.start_time = datetime.now()

if df_q is not None:
    lessons = sorted(df_q['課編號'].unique().tolist())
    sel_l = st.selectbox("選擇課次", lessons)
    quiz_list = df_q[df_q['課編號'] == sel_l].to_dict('records')

    if quiz_list:
        q = quiz_list[st.session_state.q_idx]
        st.session_state.current_qid = f"{q.get('年度','0')}_{q.get('冊編號','0')}_{q.get('課編號','0')}_{q.get('句編號','0')}"
        
        st.markdown(f'<div class="hint-box">題號 {st.session_state.q_idx + 1} &nbsp;&nbsp; {q["中文"]}</div>', unsafe_allow_html=True)
        
        # 顯示區
        st.markdown(f'<div style="background:#fff; padding:20px; border-radius:10px; border:1px solid #ddd; min-height:80px; font-size:22px; margin-bottom:15px; text-align:center;">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)

        # 功能鍵
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("退回"):
            if st.session_state.ans:
                st.session_state.ans.pop(); st.session_state.used_history.pop()
                log_event("按鍵:退回")
                st.rerun()
        if c2.button("重填"):
            st.session_state.ans, st.session_state.used_history = [], []
            log_event("按鍵:重填")
            st.rerun()
        if c3.button("上一題", disabled=(st.session_state.q_idx == 0)):
            st.session_state.q_idx -= 1
            st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
            log_event("導覽:上一題")
            st.rerun()
        if c4.button("下一題", disabled=(st.session_state.q_idx + 1 >= len(quiz_list))):
            st.session_state.q_idx += 1
            st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
            log_event("導覽:下一題")
            st.rerun()

        # 單字按鈕
        tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']))
        if not st.session_state.shuf:
            st.session_state.shuf = tokens.copy()
            random.shuffle(st.session_state.shuf)

        st.write("---")
        btn_cols = st.columns(2)
        for idx, token in enumerate(st.session_state.shuf):
            if idx not in st.session_state.used_history:
                with btn_cols[idx % 2]:
                    if st.button(token, key=f"t_{idx}", use_container_width=True):
                        st.session_state.ans.append(token)
                        st.session_state.used_history.append(idx)
                        st.rerun()

        # 檢查答案
        if len(st.session_state.ans) == len(tokens):
            if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                duration = (datetime.now() - st.session_state.start_time).seconds
                is_ok = "".join(st.session_state.ans).lower() == str(q['英文']).replace(" ", "").lower()
                log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌", duration=duration)
                if is_ok: st.success("Correct!"); st.balloons()
                else: st.error(f"錯誤！答案是: {q['英文']}")
                st.session_state.start_time = datetime.now()

st.caption(f"Ver {VERSION}")
