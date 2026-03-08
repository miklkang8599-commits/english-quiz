# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.3.1
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.3.1 [2026-03-08]: 
#   - 補回「項目」(單元) 篩選維度：支援依題型項目過濾錯題。
#   - 優化導師後台篩選連動逻辑。
# V2.3.0 [2026-03-08]: 
#   - 整合所有管理功能分頁。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.3.1"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="wide")

# --- 1. 核心檢查與資料連線 ---
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
        if df_q is not None and '單元' in df_q.columns:
            df_q['單元'] = df_q['單元'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        return df_q, df_s, df_a, df_l
    except: return None, None, None, None

# --- 2. 輔助函數 ---
def format_duration(seconds):
    try:
        s = int(float(seconds))
        if s <= 0: return "-"
        m, sec = divmod(s, 60)
        return f"{m}分{sec}秒" if m > 0 else f"{sec}秒"
    except: return "-"

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

# --- 3. 登入系統 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
enforce_auto_logout()

if not st.session_state.logged_in:
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 學生登入系統")
        input_id = st.text_input("帳號 (後四碼)", placeholder="0001")
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

# --- 4. 主介面設計與資料載入 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""
    <style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .scroll-container { max-height: 350px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; margin-bottom: 10px; }
    .student-card { border-left: 4px solid #0366d6; margin-bottom: 5px; padding-left: 10px; font-weight: bold; background: #f8f9fa; }
    .sub-header { color: #0366d6; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 15px; font-weight: bold; }
    .hint-box { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 10px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 5. 導師全功能管理後台 ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.3.1", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🏆 積分排行", "🔍 分組全覽", "⚠️ 難題分析", "🎯 多重錯題指派", "📌 任務進度追蹤"])
        
        with t_tabs[0]: # 全班紀錄
            if df_l is not None:
                st.markdown('<p class="sub-header">📝 全班練習紀錄 (作答)</p>', unsafe_allow_html=True)
                q_logs = df_l[df_l['動作'] == '作答'].sort_values('時間', ascending=False).head(15).copy()
                q_logs['費時'] = q_logs['費時'].apply(format_duration)
                st.table(q_logs[['時間', '姓名', '分組', '題目ID', '結果', '費時']])
        
        with t_tabs[1]: # 積分排行
            if df_l is not None:
                st_stats = df_l[df_l['動作'] == '作答'].groupby('姓名').agg(總次數=('結果','count'), 答對數=('結果', lambda x: (x == '✅').sum()))
                st_stats['正確率'] = (st_stats['答對數'] / st_stats['總次數'] * 100).round(1).astype(str) + '%'
                st.dataframe(st_stats.sort_values('總次數', ascending=False), use_container_width=True)

        with t_tabs[2]: # 分組全覽 (捲動式)
            group_list = sorted([g for g in df_s['分組'].unique().tolist() if g != "ADMIN"])
            sel_g = st.selectbox("請選擇組別查看組員紀錄：", group_list)
            for name in df_s[df_s['分組'] == sel_g]['姓名']:
                p_logs = df_l[df_l['姓名'] == name].copy().sort_values('時間', ascending=False)
                st.markdown(f'<div class="student-card">👤 {name} (作答 {len(p_logs[p_logs["動作"]=="作答"])} 次)</div>', unsafe_allow_html=True)
                st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
                p_quiz = p_logs[p_logs['動作'] == '作答'].copy()
                if not p_quiz.empty:
                    p_quiz['費時'] = p_quiz['費時'].apply(format_duration)
                    st.dataframe(p_quiz[['時間', '題目ID', '結果', '內容', '費時']], use_container_width=True)
                else: st.info("尚無紀錄")
                st.markdown('</div>', unsafe_allow_html=True)

        with t_tabs[3]: # 難題分析
            if df_l is not None:
                wrong_counts = df_l[df_l['結果'] == '❌']['題目ID'].value_counts().reset_index()
                wrong_counts.columns = ['題目ID', '錯誤次數']
                st.bar_chart(wrong_counts.set_index('題目ID'))

        with t_tabs[4]: # 多重錯題指派 (補回「項目」)
            st.subheader("🎯 依 冊/課/項目 篩選錯題並指派")
            if df_l is not None and not df_l.empty:
                c1, c2, c3, c4, c5 = st.columns(5)
                f_y = c1.selectbox("年度", ["全部"] + sorted(list(df_q['年度'].unique())))
                f_b = c2.selectbox("冊別", ["全部"] + sorted([int(x) for x in df_q['冊編號'].unique()]))
                
                # 動態篩選單元項目
                u_df = df_q
                if f_b != "全部": u_df = u_df[u_df['冊編號'] == f_b]
                f_u = c3.selectbox("項目 (單元)", ["全部"] + sorted(list(u_df['單元'].unique())))
                
                f_l_num = c4.selectbox("課次", ["全部"] + sorted([int(x) for x in df_q['課編號'].unique()]))
                min_err = c5.number_input("錯誤門檻", min_value=1, value=1)
                
                # 篩選邏輯
                wrong_ids = df_l[df_l['結果'] == '❌']['題目ID'].value_counts()
                filtered_ids = wrong_ids[wrong_ids >= min_err].index.tolist()
                
                final_q = []
                for qid in filtered_ids:
                    p = str(qid).split('_')
                    if len(p) >= 5:
                        match = df_q[(df_q['年度'].astype(str).str.contains(p[0])) & 
                                     (df_q['冊編號'].astype(str).str.contains(p[1])) & 
                                     (df_q['單元']==p[2]) & 
                                     (df_q['課編號'].astype(str).str.contains(p[3])) & 
                                     (df_q['句編號'].astype(str).str.contains(p[4]))]
                        if not match.empty:
                            row = match.iloc[0].to_dict()
                            # 進行多維度過濾
                            if (f_y == "全部" or row['年度'] == f_y) and \
                               (f_b == "全部" or row['冊編號'] == f_b) and \
                               (f_u == "全部" or row['單元'] == f_u) and \
                               (f_l_num == "全部" or row['課編號'] == f_l_num):
                                row['題目ID'] = qid
                                row['錯誤次數'] = wrong_ids[qid]
                                final_q.append(row)
                
                if final_q:
                    df_final = pd.DataFrame(final_q)
                    st.write(f"🔍 符合條件的錯題共 {len(df_final)} 題：")
                    st.dataframe(df_final[['題目ID', '錯誤次數', '單元', '中文', '英文']], use_container_width=True)
                    
                    st.divider()
                    col_tgt, col_msg = st.columns(2)
                    assign_to = col_tgt.selectbox("指派給：", ["全體"] + sorted(df_s['分組'].unique().tolist()) + sorted(df_s['姓名'].unique().tolist()))
                    task_note = col_msg.text_input("任務說明", value=f"{f_b if f_b!='全部' else ''}冊{f_u if f_u!='全部' else ''}錯題加強")
                    
                    if st.button("📢 確認發佈任務", type="primary"):
                        new_task = pd.DataFrame([{"對象 (分組/姓名)": assign_to, "任務類型": "錯題加強", "題目ID清單": ", ".join(df_final['題目ID'].tolist()), "說明文字": task_note, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                        conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
                        st.success("✅ 任務已成功指派至 Google Sheets！")
                        st.cache_data.clear()
                else: st.warning("目前範圍內查無符合條件的錯題。")

        with t_tabs[5]: # 任務進度追蹤
            if not df_a.empty:
                for idx, row in df_a.iterrows():
                    st.write(f"📌 **{row['說明文字']}** ({row['對象 (分組/姓名)']})")
                    q_list = str(row['題目ID清單']).split(', ')
                    res = df_l[(df_l['動作']=='作答') & (df_l['題目ID'].isin(q_list))]
                    st.dataframe(res[['時間', '姓名', '題目ID', '結果']], use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 6. 學生端接收任務 ---
st.title(f"👋 {st.session_state.user_name}")

if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體")]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.info(f"🎯 **老師指派任務**：{task['說明文字']}")
        if st.button("⚡ 開始練習老師指派的任務", type="primary"):
            q_ids = str(task['題目ID清單']).split(', ')
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                match = df_q[(df_q['年度'].astype(str).str.contains(p[0])) & (df_q['冊編號'].astype(str).str.contains(p[1])) & (df_q['單元']==p[2]) & (df_q['課編號'].astype(str).str.contains(p[3])) & (df_q['句編號'].astype(str).str.contains(p[4]))]
                if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            st.session_state.quiz_list = task_quiz; st.session_state.quiz_loaded = True; reset_quiz(); st.rerun()

# --- 7. 題目重組練習邏輯 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{int(q['年度'])}_{int(q['冊編號'])}_{q['單元']}_{int(q['課編號'])}_{int(q['句編號'])}"
    st.markdown(f'<div class="hint-box">題 {st.session_state.q_idx+1}: {q["中文"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
    
    tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())
    if not st.session_state.shuf: st.session_state.shuf = tokens.copy(); random.shuffle(st.session_state.shuf)
    
    cols = st.columns(2)
    for i, t in enumerate(st.session_state.shuf):
        if i not in st.session_state.used_history:
            if cols[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()

    c_btns = st.columns(2)
    if c_btns[0].button("🔄 重填", use_container_width=True): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
    if len(st.session_state.ans) == len(tokens):
        if c_btns[1].button("✅ 檢查答案", type="primary", use_container_width=True):
            is_ok = "".join(st.session_state.ans).lower() == str(q['英文']).replace(" ","").lower()
            log_event("作答", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
            if is_ok:
                st.success("正確！"); time.sleep(1)
                if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
            else: st.error(f"正確答案: {q['英文']}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("任務完成！"); 
    if st.button("回選單"): st.session_state.quiz_loaded = False; st.rerun()

st.caption(f"Ver {VERSION}")
