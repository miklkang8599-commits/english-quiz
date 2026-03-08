# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.1 精準計時修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.1
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.1 [2026-03-08]: 
#   - 修復費時顯示 0.0s 的問題：重新設計計時啟動與終止邏輯。
#   - 強化紀錄框顯示：明確標示「句編號」。
#   - 維持 V2.7.0 的穩定解析與防崩潰機制。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.1"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 資料讀取 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None:
            df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=5)
        df_l = conn.read(worksheet="logs", ttl=5)
        return df_a, df_l
    except: return None, None

def log_event_fast(action_type, detail="", result="-"):
    """💡 精準計時：計算從題目顯示到按下按鈕的間隔"""
    now_ts = time.time()
    # 取得本題開始時間，若無則用當前時間
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = round(now_ts - start_ts, 1)
    
    # 防止極速點擊產生 0.0s，設定最低顯示 0.1s
    if duration < 0.1: duration = 0.1
    
    st.session_state.pending_log = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id,
        "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id,
        "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type,
        "內容": detail,
        "結果": result,
        "費時": duration
    }

def flush_pending_log():
    if st.session_state.get('pending_log'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_row = pd.DataFrame([st.session_state.pending_log])
            updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.pending_log = None
            st.cache_data.clear() 
        except: pass

# --- 2. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        input_id = st.text_input("帳號 (後四碼)")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.zfill(4)
                user = df_s[df_s['帳號_c'] == input_id.strip().zfill(4)]
                if not user.empty and str(user.iloc[0]['密碼']).split('.')[0] == input_pw.strip():
                    st.session_state.update({
                        "logged_in": True, "user_id": f"EA{input_id.zfill(4)}",
                        "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'],
                        "last_activity": time.time()
                    })
                    st.rerun()
    st.stop()

# --- 3. 介面樣式 ---
st.markdown("""
<style>
    .log-container { max-height: 250px; overflow-y: auto; background-color: #ffffff; border: 2px solid #eeeeee; border-radius: 10px; padding: 15px; }
    .log-entry { border-bottom: 1px solid #f0f0f0; padding: 8px 0; font-size: 14px; display: flex; justify-content: space-between; font-family: sans-serif; }
    .res-ok { color: #28a745; font-weight: bold; }
    .res-no { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 學生主介面 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.title(f"👋 {st.session_state.user_name}")

# 手動設定區
with st.expander("⚙️ 設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="sv")
    su = c[1].selectbox("項目", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="su")
    sy = c[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="sy")
    sb = c[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="sb")
    sl = c[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="sl")
    
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 範圍內共 {len(base)} 題 | 編號：{int(min(nums))} ~ {int(max(nums))}")
        sc = st.columns(2)
        start = sc[0].number_input("起始句編號", int(min(nums)), int(max(nums)), int(min(nums)))
        num = sc[1].number_input("練習題數", 1, 50, 10)
        if st.button("🚀 開始練習", use_container_width=True):
            st.session_state.quiz_list = base[base['句編號_int'] >= start].head(int(num)).to_dict('records')
            # 💡 啟動初始計時
            st.session_state.update({"q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# --- 5. 核心練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    clean_ans = re.sub(r'[^A-Za-z]', '', str(q["單選答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()

    st.markdown(f'''<div style="background:#f0f7ff; padding:20px; border-radius:10px; border-left:6px solid #007bff; margin-bottom:15px;">
                <b>📝 題目 {st.session_state.q_idx+1} / {len(st.session_state.quiz_list)} (句編號: {q["句編號"]})</b><br><br>
                <span style="font-size:22px;">{disp}</span></div>''', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event_fast("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.current_res = ("✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({clean_ans})")
                st.session_state.show_analysis = True
                st.rerun()
        if st.session_state.get('show_analysis'):
            if "✅" in st.session_state.current_res: st.success(st.session_state.current_res)
            else: st.error(st.session_state.current_res)
            if st.button("下一題 ➡️", type="primary"):
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    # 💡 切換題目時重設計時起點
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()
