# ==============================================================================
# 🧩 英文全能練習系統 (V2.5.6 時間格式修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.5.6
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.5.6 [2026-03-08]: 
#   - 修正 TypeError：強制將 logs 時間欄位轉為 datetime 格式，修復側邊欄報錯。
#   - 強化手動範圍設定連動穩定性。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.5.6"
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
        
        # 題目資料預處理
        if df_q is not None:
            df_q = df_q.fillna("")
            for col in df_q.columns:
                df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        # 💡 關鍵修復：強制轉化 logs 時間格式
        if df_l is not None and not df_l.empty:
            df_l['時間'] = pd.to_datetime(df_l['時間'], errors='coerce')
            df_l = df_l.dropna(subset=['時間']) # 移除格式錯誤的列
            
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

# --- 3. 資料載入與側邊欄 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.button("🚪 登出系統"):
        log_event("登出")
        st.session_state.logged_in = False
        st.rerun()
    st.divider()
    # 💡 修復後的側邊欄邏輯
    if df_l is not None and not df_l.empty:
        st.subheader("📊 同組即時動態")
        my_group_logs = df_l[df_l['分組'] == st.session_state.group_id].sort_values('時間', ascending=False)
        # 10 分鐘內在線
        online_cutoff = datetime.now() - pd.Timedelta(minutes=10)
        online_names = my_group_logs[my_group_logs['時間'] > online_cutoff]['姓名'].unique()
        st.write(f"🟢 在線組員：{', '.join(online_names) if len(online_names)>0 else '僅您在線'}")
        # 最近三次作答
        recent_q = my_group_logs[my_group_logs['動作'].str.contains('作答', na=False)].head(3)
        for _, row in recent_q.iterrows():
            st.info(f"👤 {row['姓名']}\n\n題：{row['題目ID']}")

# --- 4. 學生練習邏輯 ---
st.title(f"👋 {st.session_state.user_name}")

# A. 老師指派任務
if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體")]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **老師任務：{task['說明文字']}**")
        if st.button("⚡ 立即執行任務", type="primary"):
            q_ids = [qid.strip() for qid in str(task['題目ID清單']).split(',')]
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    match = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                    if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            if task_quiz: 
                st.session_state.quiz_list = task_quiz
                reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

# B. 手動範圍設定
with st.expander("⚙️ 手動範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
    if df_q is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        v_list = sorted([v for v in df_q['版本'].unique() if v != ""])
        sel_v = c1.selectbox("版本", v_list, key="v_sel")
        u_list = sorted([u for u in df_q[df_q['版本']==sel_v]['單元'].unique() if u != ""])
        sel_u = c2.selectbox("項目", u_list, key="u_sel")
        y_list = sorted(list(df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)]['年度'].unique()))
        sel_y = c3.selectbox("年度", y_list, key="y_sel")
        b_list = sorted(list(df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==sel_y)]['冊編號'].unique()))
        sel_b = c4.selectbox("冊別", b_list, key="b_sel")
        l_list = sorted(list(df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==sel_y)&(df_q['冊編號']==sel_b)]['課編號'].unique()))
        sel_l = c5.selectbox("課次", l_list, key="l_sel")
        
        base_df = df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==sel_y)&(df_q['冊編號']==sel_b)&(df_q['課編號']==sel_l)]
        if not base_df.empty:
            sc1, sc2 = st.columns(2)
            sorted_nums = sorted([int(n) for n in base_df['句編號'].unique()])
            start_no = sc1.number_input("起始句編號", min_value=min(sorted_nums), max_value=max(sorted_nums), value=min(sorted_nums))
            q_num = sc2.number_input("練習題數", 1, 50, 10)
            if st.button("🚀 開始練習", use_container_width=True):
                final_df = base_df[base_df['句編號'].astype(int) >= start_no].sort_values('句編號').head(q_num)
                st.session_state.quiz_list = final_df.to_dict('records')
                reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

# --- 5. 題目呈現 (與 2.5.5 邏輯一致) ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    
    is_mcq = "單選" in q["單元"]
    display_t = q["單選題目"] if is_mcq else q["重組中文題目"]
    correct_a = q["單選答案"].strip().upper() if is_mcq else q["重組英文答案"].strip()

    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:10px; border-left:6px solid #1e88e5; margin-bottom:15px;">'
                f'<b>第 {st.session_state.q_idx+1} 題 ({q["單元"]})</b><br><br>{display_t}</div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True):
                is_ok = (opt == correct_a)
                log_event("單選作答", detail=opt, result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); st.balloons()
                else: st.error(f"錯誤！答案是 ({correct_a})")
                st.session_state.show_analysis = True
        if st.session_state.get('show_analysis'):
            if q.get("單選解析"): st.warning(f"💡 解析：{q['單選解析']}")
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:20px;">'
                    f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tokens = re.findall(r"[\w']+|[^\w\s]", correct_a)
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
                is_ok = "".join(st.session_state.ans).lower() == correct_a.replace(" ","").lower()
                log_event("重組作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok:
                    st.success("正確！"); time.sleep(0.5)
                    if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                    else: st.session_state.finished = True; st.rerun()
                else: st.error(f"正確答案: {correct_a}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded":False}))

st.caption(f"Ver {VERSION}")
