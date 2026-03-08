# ==============================================================================
# 🧩 英文重組練習旗艦版 (English Sentence Scramble App)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.4.0
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.4.0 [2026-03-08]: 
#   - 新增「版本」欄位支援：學生練習與導師指派均可依「版本」篩選。
#   - 修復 IndexError：強化重置邏輯，確保 quiz_list 載入時索引歸零。
#   - 題目 ID 升級：包含版本資訊，避免不同教材版本衝突。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.4.0"
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
        # 確保單元與版本為字串
        if df_q is not None:
            for col in ['單元', '版本']:
                if col in df_q.columns:
                    df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
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

# --- 4. 資料載入 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""<style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .scroll-container { max-height: 350px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; margin-bottom: 10px; }
    .student-card { border-left: 4px solid #0366d6; margin-bottom: 5px; padding-left: 10px; font-weight: bold; background: #f8f9fa; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 10px; }
    .hint-box { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 6px solid #1e88e5; font-size: 18px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)

# --- 5. 導師管理後台 ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.4.0", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🏆 積分排行", "🔍 分組全覽", "⚠️ 難題分析", "🎯 題目篩選指派", "📌 任務進度追蹤"])
        
        with t_tabs[4]: # 🎯 題目篩選指派 (加入版本篩選)
            st.subheader("🛠️ 題目篩選指派")
            if df_q is not None:
                id_c1, id_c2 = st.columns(2)
                f_group = id_c1.selectbox("1. 篩選組別", ["無"] + sorted([g for g in df_s['分組'].unique().tolist() if g != "ADMIN"]))
                name_opts = sorted(df_s['姓名'].unique().tolist()) if f_group == "無" else sorted(df_s[df_s['分組'] == f_group]['姓名'].unique().tolist())
                f_names = id_c2.multiselect("2. 篩選學生", name_opts)
                
                # 題目篩選列
                fc1, fc2, fc3, fc4, fc5, fc6 = st.columns(6)
                f_v = fc1.selectbox("版本", ["全部"] + sorted(list(df_q['版本'].unique())))
                f_y = fc2.selectbox("年度", ["全部"] + sorted(list(df_q['年度'].unique())))
                f_b = fc3.selectbox("冊別", ["全部"] + sorted([int(x) for x in df_q['冊編號'].unique()]))
                f_u = fc4.selectbox("項目", ["全部"] + sorted(list(df_q['單元'].unique())))
                f_l_num = fc5.selectbox("課次", ["全部"] + sorted([int(x) for x in df_q['課編號'].unique()]))
                min_err = fc6.number_input("錯誤門檻", min_value=0, value=1)
                
                # 核心篩選邏輯
                if min_err > 0:
                    target_logs = df_l[df_l['結果'] == '❌'].copy()
                    if f_group != "無": target_logs = target_logs[target_logs['分組'] == f_group]
                    if f_names: target_logs = target_logs[target_logs['姓名'].isin(f_names)]
                    wrong_ids = target_logs['題目ID'].value_counts()
                    filtered_ids = wrong_ids[wrong_ids >= min_err].index.tolist()
                else:
                    df_all_q = df_q.copy()
                    # 升級題目ID生成：版本_年度_冊_單元_課_句
                    df_all_q['題目ID'] = df_all_q['版本'] + "_" + df_all_q['年度'].astype(int).astype(str) + "_" + df_all_q['冊編號'].astype(int).astype(str) + "_" + df_all_q['單元'] + "_" + df_all_q['課編號'].astype(int).astype(str) + "_" + df_all_q['句編號'].astype(int).astype(str)
                    filtered_ids = df_all_q['題目ID'].tolist()
                    wrong_ids = {}

                final_q = []
                for qid in filtered_ids:
                    p = str(qid).split('_')
                    if len(p) >= 6: # 新格式：版本, 年度, 冊, 單元, 課, 句
                        match = df_q[(df_q['版本'] == p[0]) & (df_q['年度'].astype(str).str.contains(p[1])) & (df_q['冊編號'].astype(str).str.contains(p[2])) & (df_q['單元']==p[3]) & (df_q['課編號'].astype(str).str.contains(p[4])) & (df_q['句編號'].astype(str).str.contains(p[5]))]
                        if not match.empty:
                            row = match.iloc[0].to_dict()
                            if (f_v == "全部" or row['版本'] == f_v) and (f_y == "全部" or row['年度'] == f_y) and (f_b == "全部" or row['冊編號'] == f_b) and (f_u == "全部" or row['單元'] == f_u) and (f_l_num == "全部" or row['課編號'] == f_l_num):
                                row['題目ID'] = qid
                                row['錯誤次數'] = wrong_ids.get(qid, 0)
                                final_q.append(row)
                
                if final_q:
                    df_final = pd.DataFrame(final_q)
                    st.write(f"🔍 篩選結果：共 {len(df_final)} 題")
                    st.dataframe(df_final[['題目ID', '錯誤次數', '單元', '中文', '英文']], use_container_width=True)
                    st.divider()
                    col_t, col_n = st.columns(2)
                    assign_to = col_t.selectbox("指派對象", ["全體", f_group] + f_names + sorted(df_s['分組'].unique().tolist()))
                    task_note = col_n.text_input("任務名稱", value=f"任務-{datetime.now().strftime('%m%d')}")
                    if st.button("📢 確認發佈任務", type="primary"):
                        new_task = pd.DataFrame([{"對象 (分組/姓名)": assign_to, "任務類型": "指派", "題目ID清單": ", ".join(df_final['題目ID'].tolist()), "說明文字": task_note, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                        conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
                        st.success("✅ 任務已成功分派！"); st.cache_data.clear()
        
        # 其餘管理頁面 (省略部分重複邏輯，維持結構)
        with t_tabs[0]: st.table(df_l.sort_values('時間', ascending=False).head(15))
        with t_tabs[2]: # 分組全覽
            sg = st.selectbox("查看組別紀錄：", sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]))
            for name in df_s[df_s['分組'] == sg]['姓名']:
                st.markdown(f'<div class="student-card">👤 {name}</div>', unsafe_allow_html=True)
                st.dataframe(df_l[df_l['姓名']==name].tail(10))
        st.markdown('</div>', unsafe_allow_html=True)

# --- 6. 學生端接收任務 ---
st.title(f"👋 {st.session_state.user_name}")
if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.info(f"🎯 **老師任務**：{task['說明文字']}")
        if st.button("⚡ 執行指派任務", type="primary"):
            q_ids = str(task['題目ID清單']).split(', ')
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    match = df_q[(df_q['版本'] == p[0]) & (df_q['年度'] == int(p[1])) & (df_q['冊編號'] == int(p[2])) & (df_q['單元'] == p[3]) & (df_q['課編號'] == int(p[4])) & (df_q['句編號'] == int(p[5]))]
                    if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            if task_quiz:
                st.session_state.quiz_list = task_quiz
                reset_quiz() # 💡 關鍵修復：確保索引歸零
                st.session_state.quiz_loaded = True
                st.rerun()

# --- 7. 手動練習區 ---
with st.expander("⚙️ 手動範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    v_list = sorted(list(df_q['版本'].unique()))
    sel_v = sc1.selectbox("版本 ", v_list)
    df_v = df_q[df_q['版本'] == sel_v]
    y_list = sorted([int(x) for x in df_v['年度'].unique()])
    sel_y = sc2.selectbox("年度 ", y_list)
    df_y = df_v[df_v['年度'] == sel_y]
    b_list = sorted([int(x) for x in df_y['冊編號'].unique()])
    sel_b = sc3.selectbox("冊別 ", b_list)
    df_b = df_y[df_y['冊編號'] == sel_b]
    u_list = sorted(list(df_b['單元'].unique()))
    sel_u = sc4.selectbox("項目 ", u_list)
    df_u = df_b[df_b['單元'] == sel_u]
    l_list = sorted([int(x) for x in df_u['課編號'].unique()])
    sel_l = sc5.selectbox("課次 ", l_list)
    
    base_df = df_u[df_u['課編號'] == sel_l].sort_values('句編號')
    if not base_df.empty:
        cs1, cs2 = st.columns(2)
        st_id = cs1.number_input("起始句編號 ", int(base_df['句編號'].min()), int(base_df['句編號'].max()))
        num_q = cs2.number_input("測驗題數 ", 1, 50, 10)
        if st.button("🚀 載入自選練習", use_container_width=True):
            st.session_state.quiz_list = base_df[base_df['句編號'] >= st_id].head(num_q).to_dict('records')
            reset_quiz() # 💡 關鍵修復：確保索引歸零
            st.session_state.quiz_loaded = True
            st.rerun()

# --- 8. 題目練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    # 💡 IndexError 保險檢查
    if st.session_state.q_idx >= len(st.session_state.quiz_list):
        st.session_state.q_idx = 0
    
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{int(q['年度'])}_{int(q['冊編號'])}_{q['單元']}_{int(q['課編號'])}_{int(q['句編號'])}"
    
    st.markdown(f'<div class="hint-box">題 {st.session_state.q_idx+1} / {len(st.session_state.quiz_list)}<br>{q["中文"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
    
    # 練習按鈕邏輯
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
                st.success("正確！"); time.sleep(0.5)
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
            else: st.error(f"正確答案: {q['英文']}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("任務完成！"); 
    if st.button("回選單"): st.session_state.quiz_loaded = False; st.rerun()

st.caption(f"Stable Ver {VERSION}")
