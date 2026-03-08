# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.3.3
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.3.3 [2026-03-08]: 
#   - 錯題篩選門檻降至 0：支援老師直接從題庫挑選題目指派，不限於錯題。
#   - 優化篩選邏輯：當門檻為 0 時自動切換為全量題庫模式。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.3.3"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="wide")

# --- 1. 核心檢查與連線 ---
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
        input_id = st.text_input("帳號", placeholder="請輸入學號後四碼")
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

# --- 4. 主介面資料載入 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""<style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .scroll-container { max-height: 350px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; margin-bottom: 10px; }
    .student-card { border-left: 4px solid #0366d6; margin-bottom: 5px; padding-left: 10px; font-weight: bold; background: #f8f9fa; }
    .sub-header { color: #0366d6; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 15px; font-weight: bold; }
    .hint-box { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 10px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)

# --- 5. 導師全功能管理後台 ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.3.3", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🏆 積分排行", "🔍 分組全覽", "⚠️ 難題分析", "🎯 題目篩選指派", "📌 任務進度追蹤"])
        
        with t_tabs[4]: # 🎯 題目篩選指派
            st.subheader("🛠️ 依 組別/姓名/範圍 篩選題目並指派任務")
            if df_q is not None:
                # 第一排：身分過濾
                id_c1, id_c2 = st.columns(2)
                group_opts = ["無"] + sorted([g for g in df_s['分組'].unique().tolist() if g != "ADMIN"])
                f_group = id_c1.selectbox("步驟1: 篩選組別 (選「無」查看全體)", group_opts)
                name_opts = sorted(df_s['姓名'].unique().tolist()) if f_group == "無" else sorted(df_s[df_s['分組'] == f_group]['姓名'].unique().tolist())
                f_names = id_c2.multiselect("步驟2: 篩選學生 (可多選，不選代表全組)", name_opts)
                
                # 第二排：題目過濾
                c1, c2, c3, c4, c5 = st.columns(5)
                f_y = c1.selectbox("年度", ["全部"] + sorted(list(df_q['年度'].unique())))
                f_b = c2.selectbox("冊別", ["全部"] + sorted([int(x) for x in df_q['冊編號'].unique()]))
                f_u = c3.selectbox("項目", ["全部"] + sorted(list(df_q['單元'].unique())))
                f_l_num = c4.selectbox("課次", ["全部"] + sorted([int(x) for x in df_q['課編號'].unique()]))
                min_err = c5.number_input("最低錯誤次數 (設為0則挑選全題庫)", min_value=0, value=1) # 門檻降為 0
                
                # 篩選邏輯
                if min_err > 0:
                    # 模式 A: 找錯題
                    target_logs = df_l[df_l['結果'] == '❌'].copy()
                    if f_group != "無": target_logs = target_logs[target_logs['分組'] == f_group]
                    if f_names: target_logs = target_logs[target_logs['姓名'].isin(f_names)]
                    wrong_ids = target_logs['題目ID'].value_counts()
                    filtered_ids = wrong_ids[wrong_ids >= min_err].index.tolist()
                else:
                    # 模式 B: 找全量題庫
                    df_all_q = df_q.copy()
                    df_all_q['題目ID'] = df_all_q['年度'].astype(int).astype(str) + "_" + df_all_q['冊編號'].astype(int).astype(str) + "_" + df_all_q['單元'] + "_" + df_all_q['課編號'].astype(int).astype(str) + "_" + df_all_q['句編號'].astype(int).astype(str)
                    filtered_ids = df_all_q['題目ID'].tolist()
                
                final_q = []
                for qid in filtered_ids:
                    p = str(qid).split('_')
                    if len(p) >= 5:
                        match = df_q[(df_q['年度'].astype(str).str.contains(p[0])) & (df_q['冊編號'].astype(str).str.contains(p[1])) & (df_q['單元']==p[2]) & (df_q['課編號'].astype(str).str.contains(p[3])) & (df_q['句編號'].astype(str).str.contains(p[4]))]
                        if not match.empty:
                            row = match.iloc[0].to_dict()
                            if (f_y == "全部" or row['年度'] == f_y) and (f_b == "全部" or row['冊編號'] == f_b) and (f_u == "全部" or row['單元'] == f_u) and (f_l_num == "全部" or row['課編號'] == f_l_num):
                                row['題目ID'] = qid
                                row['錯誤次數'] = wrong_ids[qid] if min_err > 0 else 0
                                final_q.append(row)
                
                if final_q:
                    df_final = pd.DataFrame(final_q)
                    st.write(f"🔍 篩選結果：共 {len(df_final)} 題")
                    st.dataframe(df_final[['題目ID', '錯誤次數', '單元', '中文', '英文']], use_container_width=True)
                    st.divider()
                    col_t, col_n = st.columns(2)
                    default_tgt = f_group if f_group != "無" else "全體"
                    if f_names: default_tgt = ", ".join(f_names)
                    assign_to = col_t.selectbox("指派對象 (顯示用)", ["全體", f_group] + f_names + sorted(df_s['分組'].unique().tolist()))
                    task_note = col_n.text_input("任務名稱", value=f"{'自選' if min_err==0 else '錯題'}練習-{datetime.now().strftime('%m%d')}")
                    if st.button("📢 確認發佈任務", type="primary"):
                        new_task = pd.DataFrame([{"對象 (分組/姓名)": assign_to, "任務類型": "指派任務", "題目ID清單": ", ".join(df_final['題目ID'].tolist()), "說明文字": task_note, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                        conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
                        st.success("✅ 任務已成功分派！"); st.cache_data.clear()
                else: st.warning("目前過濾條件下無符合題目。")
        # (其餘管理分頁與 V2.3.2 相同)
        with t_tabs[0]:
            if df_l is not None:
                q_logs = df_l[df_l['動作'] == '作答'].sort_values('時間', ascending=False).head(15).copy()
                q_logs['費時'] = q_logs['費時'].apply(format_duration)
                st.table(q_logs[['時間', '姓名', '分組', '題目ID', '結果', '費時']])
        with t_tabs[2]:
            group_list = sorted([g for g in df_s['分組'].unique().tolist() if g != "ADMIN"])
            sel_g = st.selectbox("查看組別紀錄：", group_list)
            for name in df_s[df_s['分組'] == sel_g]['姓名']:
                p_logs = df_l[df_l['姓名'] == name].copy().sort_values('時間', ascending=False)
                st.markdown(f'<div class="student-card">👤 {name}</div>', unsafe_allow_html=True)
                st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
                p_quiz = p_logs[p_logs['動作'] == '作答'].copy()
                if not p_quiz.empty:
                    p_quiz['費時'] = p_quiz['費時'].apply(format_duration)
                    st.dataframe(p_quiz[['時間', '題目ID', '結果', '內容', '費時']], use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        with t_tabs[5]:
            if not df_a.empty:
                for idx, row in df_a.iterrows():
                    st.write(f"📌 **{row['說明文字']}** (對象: {row['對象 (分組/姓名)']})")
                    q_list = str(row['題目ID清單']).split(', ')
                    res = df_l[(df_l['動作']=='作答') & (df_l['題目ID'].isin(q_list))]
                    st.dataframe(res[['時間', '姓名', '題目ID', '結果']], use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 6. 學生端接收任務 ---
st.title(f"👋 {st.session_state.user_name}")
if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
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

# --- 7. 題目練習區 ---
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
