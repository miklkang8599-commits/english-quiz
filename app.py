# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 1.9.1
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V1.9.1 [2026-03-08]: 
#   - 老師後台分流：練習紀錄 (作答) 與 系統紀錄 (登入/出) 分開表格顯示，避免雜亂。
#   - 移除練習紀錄中冗餘的動作欄位。
# V1.9.0 [2026-03-08]: 
#   - 時間格式優化：後台所有「費時」改以「分秒」顯示。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "1.9.1"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="wide")

# --- 1. 連線與資料讀取 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_all_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        num_cols = ['年度', '冊編號', '課編號', '句編號']
        for col in num_cols:
            if col in df_q.columns:
                df_q[col] = pd.to_numeric(df_q[col], errors='coerce')
        if '單元' in df_q.columns:
            df_q['單元'] = df_q['單元'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        return df_q.dropna(subset=['英文', '中文', '年度']), df_s
    except: return None, None

@st.cache_data(ttl=10)
def load_logs_data():
    try:
        df = conn.read(worksheet="logs")
        df['時間'] = pd.to_datetime(df['時間'])
        return df
    except: return None

# --- 2. 輔助函數 ---
def format_duration(seconds):
    try:
        s = int(float(seconds))
        if s <= 0: return "-"
        if s < 60: return f"{s}秒"
        m, sec = divmod(s, 60)
        return f"{m}分{sec}秒" if sec > 0 else f"{m}分"
    except: return "-"

def get_int_list(df, col):
    if df is None or df.empty: return []
    vals = df[col].dropna().unique()
    return sorted([int(float(x)) for x in vals])

def get_str_list(df, col):
    if df is None or df.empty: return []
    return sorted(df[col].dropna().unique().tolist())

def log_event(action_type, detail="", result="-", duration=0):
    if not st.session_state.get('logged_in'): return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = pd.DataFrame([{
            "時間": now, "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
            "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
            "動作": action_type, "內容": detail, "結果": result, "費時": duration
        }])
        if action_type in ["作答", "登入", "登出"]:
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

# --- 3. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    l_sp, c_login, r_sp = st.columns([1, 1.2, 1])
    with c_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("🧩 學生登入系統")
        with st.container(border=True):
            col_ea, col_input = st.columns([1, 4])
            col_ea.markdown("### EA")
            input_id = col_input.text_input("帳號", max_chars=4, label_visibility="collapsed", placeholder="請輸入4位數字")
            input_pw = st.text_input("密碼", type="password", max_chars=4, placeholder="請輸入密碼")
            if st.button("🚀 確認登入", type="primary", use_container_width=True):
                df_q, df_s = load_all_data()
                if df_s is not None:
                    df_s['帳號_c'] = df_s['帳號'].astype(str).str.split('.').str[0].str.strip().str.zfill(4)
                    df_s['密碼_c'] = df_s['密碼'].astype(str).str.split('.').str[0].str.strip().str.zfill(4)
                    user = df_s[df_s['帳號_c'] == str(input_id).strip().zfill(4)]
                    if not user.empty and str(user.iloc[0]['密碼_c']) == str(input_pw).strip().zfill(4):
                        st.session_state.logged_in = True
                        st.session_state.user_id = f"EA{input_id.zfill(4)}"
                        st.session_state.user_name = user.iloc[0]['姓名']
                        st.session_state.group_id = user.iloc[0]['分組']
                        log_event("登入")
                        st.rerun()
                    else: st.error("❌ 帳號或密碼錯誤")
    st.stop()

# --- 4. CSS ---
st.markdown("""
    <style>
    @keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .marquee-container { background: #333; color: #00ff00; padding: 5px 0; overflow: hidden; white-space: nowrap; margin-bottom:10px; border-radius:5px; }
    .marquee-text { display: inline-block; animation: marquee 25s linear infinite; font-size: 16px; }
    .hint-box { background-color: #f8f9fa; padding: 15px 20px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 10px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 10px; }
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .sub-header { color: #0366d6; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 15px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

logs_df = load_logs_data()
df_q, df_s = load_all_data()

# --- 5. 導師管理後台 ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 (Teacher Control Panel)", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tab1, t_tab2, t_tab3, t_tab4 = st.tabs(["全班紀錄", "難題分析", "積分排行", "🔍 個別學生追蹤"])
        
        with t_tab1:
            if logs_df is not None:
                st.markdown('<p class="sub-header">📝 全班練習紀錄 (作答)</p>', unsafe_allow_html=True)
                quiz_logs = logs_df[logs_df['動作'] == '作答'].sort_values('時間', ascending=False).head(15).copy()
                quiz_logs['費時'] = quiz_logs['費時'].apply(format_duration)
                st.table(quiz_logs[['時間', '姓名', '分組', '題目ID', '結果', '費時']])
                
                st.markdown('<p class="sub-header">🔑 全班系統紀錄 (登入/出)</p>', unsafe_allow_html=True)
                sys_logs = logs_df[logs_df['動作'].isin(['登入', '登出'])].sort_values('時間', ascending=False).head(10)
                st.table(sys_logs[['時間', '姓名', '分組', '動作']])
        
        with t_tab2:
            if logs_df is not None:
                wrong_counts = logs_df[logs_df['結果'] == '❌']['題目ID'].value_counts().reset_index()
                wrong_counts.columns = ['題目ID', '錯誤次數']
                st.bar_chart(wrong_counts.set_index('題目ID'))

        with t_tab3:
            if logs_df is not None:
                st_stats = logs_df[logs_df['動作'] == '作答'].groupby('姓名').agg(
                    總次數=('結果', 'count'),
                    答對數=('結果', lambda x: (x == '✅').sum())
                )
                st_stats['正確率'] = (st_stats['答對數'] / st_stats['總次數'] * 100).round(1).astype(str) + '%'
                st.dataframe(st_stats, use_container_width=True)

        with t_tab4:
            if df_s is not None and logs_df is not None:
                col_g, col_s = st.columns(2)
                group_list = sorted(df_s['分組'].unique().tolist())
                if "ADMIN" in group_list: group_list.remove("ADMIN")
                selected_group = col_g.selectbox("1. 請選擇組別", group_list)
                
                filtered_students = df_s[df_s['分組'] == selected_group].copy()
                filtered_students['display_name'] = filtered_students['姓名'] + " (EA" + filtered_students['帳號'].astype(str).str.split('.').str[0].str.zfill(4) + ")"
                student_options = sorted(filtered_students['display_name'].tolist())
                target_student = col_s.selectbox("2. 請選擇學生", student_options)
                
                if target_student:
                    selected_name = target_student.split(" (")[0]
                    p_all = logs_df[logs_df['姓名'] == selected_name].copy().sort_values('時間', ascending=False)
                    
                    st.write(f"---")
                    st.write(f"### 📋 {selected_name} 的紀錄回顧")
                    
                    st.markdown('<p class="sub-header">📝 練習表現</p>', unsafe_allow_html=True)
                    p_quiz = p_all[p_all['動作'] == '作答'].copy()
                    if not p_quiz.empty:
                        p_quiz['題目ID'] = p_quiz['題目ID'].astype(str).str.replace('.0', '', regex=False)
                        p_quiz['費時'] = p_quiz['費時'].apply(format_duration)
                        st.table(p_quiz[['時間', '題目ID', '結果', '內容', '費時']])
                    else: st.info("尚無練習紀錄")

                    st.markdown('<p class="sub-header">🔑 登入歷史</p>', unsafe_allow_html=True)
                    p_sys = p_all[p_all['動作'].isin(['登入', '登出'])]
                    if not p_sys.empty:
                        st.table(p_sys[['時間', '動作']])
                    else: st.info("尚無登入紀錄")
        st.markdown('</div>', unsafe_allow_html=True)

# 跑馬燈
if logs_df is not None:
    recent = logs_df[logs_df['結果'] == '✅'].tail(3)
    m_text = " | ".join([f"🔥 {r['姓名']}({r['分組']}) 剛剛答對了!" for _, r in recent.iterrows()])
    if m_text: st.markdown(f'<div class="marquee-container"><div class="marquee-text">{m_text}</div></div>', unsafe_allow_html=True)

# 側邊欄
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.button("🚪 登出系統"): log_event("登出"); st.session_state.logged_in = False; st.rerun()
    st.divider()
    if logs_df is not None:
        st.subheader("📊 同組即時動態")
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        group_data = logs_df[logs_df['分組'] == st.session_state.group_id]
        online_users = group_data[group_data['時間'] > ten_mins_ago]['姓名'].unique()
        st.write("🟢 在線組員：" + (", ".join(online_users) if len(online_users) > 0 else "僅您在線"))
        recent_2 = group_data[group_data['動作'] == '作答'].sort_values('時間', ascending=False).head(2)
        for _, row in recent_2.iterrows():
            st.info(f"👤 {row['姓名']}\n\n題：{str(row['題目ID']).replace('.0', '')}")

# 練習邏輯
if df_q is not None:
    with st.expander("⚙️ 範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
        c1, c2, c3, c4 = st.columns(4)
        sel_y = c1.selectbox("年度", get_int_list(df_q, '年度'))
        df_f1 = df_q[df_q['年度'] == sel_y]
        sel_b = c2.selectbox("冊別", get_int_list(df_f1, '冊編號'))
        df_f2 = df_f1[df_f1['冊編號'] == sel_b]
        sel_u = c3.selectbox("單元內容", get_str_list(df_f2, '單元'))
        df_f3 = df_f2[df_f2['單元'] == sel_u]
        sel_l = c4.selectbox("課次", get_int_list(df_f3, '課編號'))
        base_df = df_f3[df_f3['課編號'] == sel_l].sort_values('句編號')
        
        if not base_df.empty:
            s1, s2 = st.columns([1, 1])
            start_id = s1.number_input("起始句編號", int(base_df['句編號'].min()), int(base_df['句編號'].max()), step=1)
            if 'num_q_tmp' not in st.session_state: st.session_state.num_q_tmp = 10
            sc1, sc2, sc3 = s2.columns([1, 2, 1])
            if sc1.button("➖"): st.session_state.num_q_tmp = max(1, st.session_state.num_q_tmp - 1)
            sc2.markdown(f"<h5 style='text-align: center;'>題數: {st.session_state.num_q_tmp}</h5>", unsafe_allow_html=True)
            if sc3.button("➕"): st.session_state.num_q_tmp += 1
            if st.button("🚀 載入測驗", type="primary", use_container_width=True):
                st.session_state.quiz_list = base_df[base_df['句編號'] >= start_id].head(st.session_state.num_q_tmp).to_dict('records')
                st.session_state.quiz_loaded = True; reset_quiz(); st.rerun()

    if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
        quiz_list = st.session_state.quiz_list
        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            st.session_state.current_qid = f"{int(q['年度'])}_{int(q['冊編號'])}_{q['單元']}_{int(q['課編號'])}_{int(q['句編號'])}"
            st.markdown(f'<div class="hint-box"><span style="color:#1e88e5; font-weight:bold;">題號 {st.session_state.q_idx + 1} (句編號 {int(q["句編號"])})</span><br>{q["中文"]}</div>', unsafe_allow_html=True)
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
            eng_raw = str(q['英文']).strip()
            tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)
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
                    is_ok = "".join(st.session_state.ans).lower() == eng_raw.replace(" ", "").lower()
                    log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌", duration=dur)
                    if is_ok: st.success("Correct!"); st.balloons()
                    else: st.error(f"錯誤！正確答案: {eng_raw}")
                    st.session_state.start_time = datetime.now()

st.caption(f"Ver {VERSION}")
