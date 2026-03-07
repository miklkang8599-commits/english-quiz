# ==============================================================================
# 🧩 英文重組練習旗艦版 V1.7.4 (效能流暢優化版)
# ==============================================================================
import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "1.7.4"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# --- 1. 連線設定 (優化讀取快取) ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CSS 樣式 ---
st.markdown(f"""
    <style>
    @keyframes marquee {{ 0% {{ transform: translateX(100%); }} 100% {{ transform: translateX(-100%); }} }}
    .marquee-container {{ background: #333; color: #00ff00; padding: 5px 0; overflow: hidden; white-space: nowrap; margin-bottom:10px; border-radius:5px; }}
    .marquee-text {{ display: inline-block; animation: marquee 20s linear infinite; font-size: 16px; }}
    .hint-box {{ background-color: #f8f9fa; padding: 15px 20px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 15px; }}
    .q-meta {{ color: #1e88e5; font-size: 16px; font-weight: bold; }}
    .answer-display {{ background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 80px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: center; font-size: 22px; margin-bottom: 15px; }}
    </style>
""", unsafe_allow_html=True)

# --- 3. 核心功能優化 ---

@st.cache_data(ttl=300) # 題目與名單 5 分鐘才更新一次，極速提升效能
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        return df_q, df_s
    except: return None, None

@st.cache_data(ttl=60) # 跑馬燈與足跡 1 分鐘更新一次
def load_logs_data():
    try:
        return conn.read(worksheet="logs")
    except: return None

def log_event(action_type, detail="", result="-", duration=0):
    """精簡化寫入，減少連線頻率"""
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qid = st.session_state.get('current_qid', "N/A")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": qid, "動作": action_type,
            "內容": detail, "結果": result, "費時": duration
        }])
        # 僅在正式作答或登入時執行昂貴的寫入動作
        if action_type in ["作答", "登入", "登出"]:
            old_logs = conn.read(worksheet="logs", ttl=0)
            updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.cache_data.clear() # 寫入後才清除快取
    except: pass

def reset_quiz_state():
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.start_time = datetime.now()
    st.session_state.finished = False

# --- 4. 登入邏輯 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🧩 學生學習系統")
    col1, col2 = st.columns([1, 4])
    col1.markdown("### EA")
    input_id = col2.text_input("帳號 (4位數字)", max_chars=4)
    input_pw = st.text_input("密碼 (4位數字)", type="password", max_chars=4)
    if st.button("確認登入", type="primary", use_container_width=True):
        _, df_s = load_static_data()
        if df_s is not None:
            df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.strip()
            df_s['密碼_c'] = df_s['密碼'].astype(str).str.split('.').str[0].str.strip()
            user = df_s[df_s['帳號_c'] == str(input_id).strip()]
            if not user.empty and str(user.iloc[0]['密碼_c']) == str(input_pw).strip():
                st.session_state.logged_in = True
                st.session_state.user_id = f"EA{input_id}"
                st.session_state.user_name = user.iloc[0]['姓名']
                st.session_state.group_id = user.iloc[0]['分組']
                log_event("登入")
                reset_quiz_state()
                st.rerun()
            else: st.error("帳號或密碼錯誤")
    st.stop()

# --- 5. 練習畫面 ---
# 跑馬燈 (使用快取資料)
logs_df = load_logs_data()
if logs_df is not None:
    recent = logs_df[logs_df['結果'] == '✅'].tail(3)
    m_text = " | ".join([f"🔥 {r['姓名']}({r['分組']}) 答對 {r['題目ID']}!" for _, r in recent.iterrows()])
    if m_text: st.markdown(f'<div class="marquee-container"><div class="marquee-text">{m_text}</div></div>', unsafe_allow_html=True)

df_q, _ = load_static_data()

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.button("🚪 登出系統"):
        log_event("登出"); st.session_state.logged_in = False; st.rerun()
    st.divider()
    if logs_df is not None:
        with st.expander("📊 同組動態"):
            st.table(logs_df[logs_df['分組']==st.session_state.group_id].tail(5)[['姓名','動作','結果']])

if df_q is not None:
    with st.expander("⚙️ 範圍與題數設定", expanded=True):
        c1, c2 = st.columns(2)
        sel_y = c1.selectbox("年度", sorted(df_q['年度'].unique()))
        sel_b = c2.selectbox("冊別", sorted(df_q[df_q['年度']==sel_y]['冊編號'].unique()))
        c3, c4 = st.columns(2)
        sel_u = c3.selectbox("單元", sorted(df_q[(df_q['年度']==sel_y)&(df_q['冊編號']==sel_b)]['單元'].unique()))
        sel_l = c4.selectbox("課次", sorted(df_q[(df_q['年度']==sel_y)&(df_q['冊編號']==sel_b)&(df_q['單元']==sel_u)]['課編號'].unique()))
        
        base_df = df_q[(df_q['年度']==sel_y)&(df_q['冊編號']==sel_b)&(df_q['單元']==sel_u)&(df_q['課編號']==sel_l)].sort_values('句編號')
        
        if not base_df.empty:
            start_id = st.number_input("起始句編號", int(base_df['句編號'].min()), int(base_df['句編號'].max()))
            valid_quiz = base_df[base_df['句編號'] >= start_id]
            max_a = len(valid_quiz)
            if 'num_q_val' not in st.session_state: st.session_state.num_q_val = 10
            
            cm, cv, cp = st.columns([1, 2, 1])
            if cm.button("➖") and st.session_state.num_q_val > 1: st.session_state.num_q_val -= 1
            with cv: st.markdown(f"<h4 style='text-align: center;'>題數: {st.session_state.num_q_val}</h4>", unsafe_allow_html=True)
            if cp.button("➕") and st.session_state.num_q_val < max_a: st.session_state.num_q_val += 1
            
            quiz_list = valid_quiz.head(min(st.session_state.num_q_val, max_a)).to_dict('records')
            curr_k = f"{sel_y}-{sel_b}-{sel_u}-{sel_l}-{start_id}-{st.session_state.num_q_val}"
            if st.session_state.get('last_cfg') != curr_k:
                st.session_state.last_cfg = curr_k; reset_quiz_state(); st.rerun()

    if not base_df.empty and not st.session_state.finished:
        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            st.session_state.current_qid = f"{q.get('年度','0')}_{q.get('冊編號','0')}_{q.get('課編號','0')}_{q.get('句編號','0')}"
            
            st.markdown(f'<div class="hint-box"><span class="q-meta">題號 {st.session_state.q_idx + 1} (句編號 {int(q["句編號"])})</span>&nbsp;&nbsp;&nbsp;{q["中文"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)

            nav = st.columns(4)
            if nav[0].button("退回"):
                if st.session_state.ans: st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
            if nav[1].button("重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
            if nav[2].button("上一題", disabled=(st.session_state.q_idx == 0)):
                st.session_state.q_idx -= 1; st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []; st.rerun()
            if nav[3].button("下一題"):
                if st.session_state.q_idx + 1 < len(quiz_list):
                    st.session_state.q_idx += 1; st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []; st.rerun()
                else: st.session_state.finished = True; st.rerun()

            tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())
            if not st.session_state.shuf: st.session_state.shuf = tokens.copy(); random.shuffle(st.session_state.shuf)

            st.write("---")
            btn_cols = st.columns(2)
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    with btn_cols[idx % 2]:
                        if st.button(token, key=f"t_{idx}", use_container_width=True):
                            st.session_state.ans.append(token); st.session_state.used_history.append(idx); st.rerun()

            if len(st.session_state.ans) == len(tokens):
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    dur = (datetime.now() - st.session_state.start_time).seconds
                    is_ok = "".join(st.session_state.ans).lower() == str(q['英文']).strip().replace(" ", "").lower()
                    log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌", duration=dur)
                    if is_ok: st.success("Correct!"); st.balloons()
                    else: st.error(f"錯誤！答案是: {q['英文']}")
                    st.session_state.start_time = datetime.now()

st.caption(f"Smooth Ver {VERSION}")
