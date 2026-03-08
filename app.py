# ==============================================================================
# 🧩 英文全能練習系統 (Sentence Scramble & Multiple Choice)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.5.1
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.5.1 [2026-03-08]: 
#   - 支援寬表格結構：相容重組與單選專屬欄位，自動處理空白儲存格。
#   - 強化空值檢查：確保題目載入時不會因遺漏欄位而崩潰。
#   - 優化題目顯示：自動選擇「重組」或「單選」對應的欄位內容。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.5.1"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 核心邏輯與資料讀取 ---
def enforce_auto_logout():
    if st.session_state.get('logged_in'):
        if time.time() - st.session_state.get('last_activity', time.time()) > IDLE_TIMEOUT:
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.session_state.logged_in = False
            st.rerun()

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        df_a = conn.read(worksheet="assignments")
        df_l = conn.read(worksheet="logs")
        
        # 數值轉換
        for df in [df_q, df_a, df_l]:
            if df is not None:
                for col in ['年度', '冊編號', '課編號', '句編號']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 欄位空值預處理：將所有空白轉為空字串，避免程式出錯
        if df_q is not None:
            df_q = df_q.fillna("")
            for col in df_q.columns:
                df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        return df_q, df_s, df_a, df_l
    except Exception as e:
        st.error(f"資料讀取錯誤: {e}")
        return None, None, None, None

def log_event(action_type, detail="", result="-", duration=0):
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
            "動作": action_type, "內容": detail, "結果": result, "費時": duration
        }])
        old_logs = conn.read(worksheet="logs", ttl=0)
        updated_logs = pd.concat([old_logs, new_row], ignore_index=True)
        conn.update(worksheet="logs", data=updated_logs)
        st.cache_data.clear()
    except: pass

def reset_quiz():
    st.session_state.q_idx = 0
    st.session_state.ans, st.session_state.used_history, st.session_state.shuf = [], [], []
    st.session_state.start_time = datetime.now()
    st.session_state.finished = False
    st.session_state.show_analysis = False

# --- 2. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
enforce_auto_logout()

if not st.session_state.logged_in:
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        input_id = st.text_input("帳號 (後四碼)")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入", use_container_width=True):
            df_q, df_s, _, _ = load_all_data()
            df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.zfill(4)
            user = df_s[df_s['帳號_c'] == input_id.strip()]
            if not user.empty and str(user.iloc[0]['密碼']).split('.')[0] == input_pw.strip():
                st.session_state.logged_in = True
                st.session_state.last_activity = time.time()
                st.session_state.user_id = f"EA{input_id.zfill(4)}"
                st.session_state.user_name = user.iloc[0]['姓名']
                st.session_state.group_id = user.iloc[0]['分組']
                log_event("登入")
                st.rerun()
    st.stop()

# --- 3. UI 與 資料加載 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""<style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #1e88e5; margin-bottom: 15px; }
    .analysis-box { background-color: #fff9c4; padding: 15px; border-radius: 10px; border: 1px solid #fbc02d; margin-top: 10px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; }
</style>""", unsafe_allow_html=True)

# --- 4. 導師管理後台 (支援新架構篩選) ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.5.1", expanded=True):
        st.write("您可以在此依據新欄位結構指派任務。")

# --- 5. 學生任務偵測 ---
st.title(f"👋 {st.session_state.user_name}")
if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體")]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        if st.button(f"🎯 老師任務：{task['說明文字']}", type="primary"):
            q_ids = str(task['題目ID清單']).split(', ')
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    match = df_q[(df_q['版本'] == p[0]) & (df_q['年度'] == p[1]) & (df_q['冊編號'] == p[2]) & (df_q['單元'] == p[3]) & (df_q['課編號'] == p[4]) & (df_q['句編號'] == p[5])]
                    if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            if task_quiz: st.session_state.quiz_list = task_quiz; reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

# --- 6. 核心題目區：自動識別欄位 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    
    # 💡 關鍵：分流顯示內容
    if q["單元"] == "單選":
        display_question = q["單選題目"]
        correct_answer = q["單選答案"].strip().upper()
        analysis_text = q["單選解析"]
    else:
        display_question = q["重組中文題目"]
        correct_answer = q["重組英文答案"].strip()
        analysis_text = ""

    st.markdown(f'<div class="q-card"><b>第 {st.session_state.q_idx+1} 題 ({q["單元"]})</b><br><br>{display_question}</div>', unsafe_allow_html=True)
    
    # --- 單選題模式 ---
    if q["單元"] == "單選":
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True):
                is_ok = (opt == correct_answer)
                log_event("單選作答", detail=opt, result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); st.balloons()
                else: st.error(f"錯誤！正確答案是 ({correct_answer})")
                st.session_state.show_analysis = True

        if st.session_state.get('show_analysis'):
            if analysis_text: st.markdown(f'<div class="analysis-box">💡 <b>解析：</b><br>{analysis_text}</div>', unsafe_allow_html=True)
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()

    # --- 重組題模式 ---
    else:
        st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tokens = re.findall(r"[\w']+|[^\w\s]", correct_answer)
        if not st.session_state.shuf: st.session_state.shuf = tokens.copy(); random.shuffle(st.session_state.shuf)
        
        btns = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if btns[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        
        ctrl = st.columns(2)
        if ctrl[0].button("🔄 重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
        if len(st.session_state.ans) == len(tokens):
            if ctrl[1].button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == correct_answer.replace(" ","").lower()
                log_event("重組作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok:
                    st.success("正確！"); time.sleep(0.5)
                    if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                    else: st.session_state.finished = True; st.rerun()
                else: st.error(f"正確答案: {correct_answer}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded":False}))

st.caption(f"Ver {VERSION}")
