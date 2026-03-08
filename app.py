# ==============================================================================
# 🧩 英文全能練習系統 (V2.6.2 穩定比對版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.6.2
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.6.2 [2026-03-08]: 
#   - 修復單選題對案 Bug：新增模糊比對邏輯，自動剔除括號與空格。
#   - 強化 logs 時間轉型防護。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.6.2"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 核心邏輯 ---
def enforce_auto_logout():
    if st.session_state.get('logged_in'):
        now = time.time()
        if now - st.session_state.get('last_activity', now) > IDLE_TIMEOUT:
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
        
        if df_q is not None:
            df_q = df_q.fillna("")
            for col in df_q.columns:
                df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        if df_l is not None and not df_l.empty:
            df_l['時間'] = pd.to_datetime(df_l['時間'], errors='coerce')
            df_l = df_l.dropna(subset=['時間'])
            
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

# --- 3. 資料與側邊欄 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.button("🚪 登出系統"):
        log_event("登出")
        st.session_state.logged_in = False
        st.rerun()
    st.divider()
    if df_l is not None and not df_l.empty:
        st.subheader("📊 同組即時動態")
        gl = df_l[df_l['分組'] == st.session_state.group_id].sort_values('時間', ascending=False)
        online = gl[gl['時間'] > (datetime.now() - pd.Timedelta(minutes=10))]['姓名'].unique()
        st.write(f"🟢 在線：{', '.join(online) if len(online)>0 else '僅您'}")
        for _, r in gl[gl['動作'].str.contains('作答', na=False)].head(3).iterrows():
            st.info(f"👤 {r['姓名']}\n\n題：{r['題目ID']}")

# --- 4. 導師管理中心 (與 V2.6.1 邏輯一致) ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理中心 V2.6.2", expanded=True):
        st.markdown('<div style="background:#f1f8ff; padding:20px; border-radius:10px; border:2px solid #0366d6; margin-bottom:20px;">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🔍 分組全覽", "🎯 指派任務", "📜 任務管理"])
        with t_tabs[3]: # 任務管理
            if df_a is not None and not df_a.empty:
                for i, row in df_a.iterrows():
                    c_i, c_d = st.columns([4, 1])
                    c_i.info(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                    if c_d.button("🗑️ 刪除", key=f"del_{i}"):
                        conn.update(worksheet="assignments", data=df_a.drop(i))
                        st.success("已刪除"); st.cache_data.clear(); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 學生端與練習邏輯 ---
st.title(f"👋 {st.session_state.user_name}")

if df_a is not None and not df_a.empty:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | 
                    (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | 
                    (df_a['對象 (分組/姓名)'] == "全體") |
                    (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **老師任務：{task['說明文字']}**")
        if st.button("⚡ 立即執行任務", type="primary"):
            q_ids = [qid.strip() for qid in str(task['題目ID清單']).split(',')]
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    m = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                    if not m.empty: task_quiz.append(m.iloc[0].to_dict())
            if task_quiz: st.session_state.quiz_list = task_quiz; reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

# 手動設定
with st.expander("⚙️ 手動範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
    if df_q is not None:
        c = st.columns(5)
        sv = c[0].selectbox("版本 ", sorted([v for v in df_q['版本'].unique() if v != ""]), key="sv")
        su = c[1].selectbox("項目 ", sorted([u for u in df_q[df_q['版本']==sv]['單元'].unique() if u != ""]), key="su")
        sy = c[2].selectbox("年度 ", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique())), key="sy")
        sb = c[3].selectbox("冊別 ", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique())), key="sb")
        sl = c[4].selectbox("課次 ", sorted(list(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique())), key="sl")
        base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)]
        if not base.empty:
            sc1, sc2 = st.columns(2)
            nums = sorted([int(n) for n in base['句編號'].unique()])
            start = sc1.number_input("起始句編號 ", min(nums), max(nums), min(nums))
            num = sc2.number_input("練習題數 ", 1, 50, 10)
            if st.button("🚀 開始練習", use_container_width=True):
                st.session_state.quiz_list = base[base['句編號'].astype(int) >= start].sort_values('句編號').head(num).to_dict('records')
                reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

# --- 6. 核心練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    
    # 💡 修正單選對案邏輯：模糊比對
    raw_ans = q["單選答案"] if is_mcq else q["重組英文答案"]
    clean_ans = re.sub(r'[^A-Za-z]', '', raw_ans).upper() if is_mcq else raw_ans.strip()

    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:10px; border-left:6px solid #1e88e5; margin-bottom:15px;">'
                f'<b>第 {st.session_state.q_idx+1} 題 ({q["單元"]})</b><br><br>{disp}</div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True):
                # 只比對字母本身
                is_ok = (opt == clean_ans)
                log_event("單選", detail=opt, result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); st.balloons()
                else: st.error(f"錯誤！答案是 ({clean_ans})")
                st.session_state.show_analysis = True
        if st.session_state.get('show_analysis'):
            if q.get("單選解析"): st.warning(f"💡 解析：{q['單選解析']}")
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx+=1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.shuf: st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok:
                    st.success("正確！"); time.sleep(0.5)
                    if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx+=1; reset_quiz(); st.rerun()
                    else: st.session_state.finished = True; st.rerun()
                else: st.error(f"正確答案: {clean_ans}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded":False}))

st.caption(f"Ver {VERSION}")
