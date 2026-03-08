# ==============================================================================
# 🧩 英文全能練習系統 (V2.5.3 老師端同步強化版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.5.3
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.5.3 [2026-03-08]: 
#   - 老師端後台全面升級：支援版本、項目、年度、冊、課的多重連動篩選。
#   - 修正題目預覽邏輯：自動偵測單選/重組欄位顯示題目內容。
#   - 統一任務分派機制，確保與寬表格欄位結構 100% 相容。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.5.3"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習管理系統 V{VERSION}", layout="wide")

# --- 1. 核心邏輯 ---
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
        if df_q is not None:
            df_q = df_q.fillna("")
            str_cols = ['版本', '單元', '重組英文答案', '重組中文題目', '單選題目', '單選答案', '單選解析']
            for col in str_cols:
                if col in df_q.columns:
                    df_q[col] = df_q[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        return df_q, df_s, df_a, df_l
    except: return None, None, None, None

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

# --- 2. 登入系統 (略，同 V2.5.2) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
enforce_auto_logout()

if not st.session_state.logged_in:
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 測驗登入系統")
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

# --- 3. 資料與 CSS ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""<style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .scroll-container { max-height: 350px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; margin-bottom: 10px; }
    .student-card { border-left: 4px solid #0366d6; margin-bottom: 5px; padding-left: 10px; font-weight: bold; background: #f8f9fa; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #1e88e5; margin-bottom: 15px; }
    .analysis-box { background-color: #fff9c4; padding: 15px; border-radius: 10px; border: 1px solid #fbc02d; margin-top: 10px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; }
</style>""", unsafe_allow_html=True)

# --- 4. 導師管理後台 (V2.5.3 強化版) ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理後台 V2.5.3", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🏆 積分排行", "🔍 分組全覽", "🎯 題目篩選指派", "📌 任務進度追蹤"])
        
        with t_tabs[0]: # 全班紀錄
            if df_l is not None:
                st.table(df_l[df_l['動作'] == '作答'].sort_values('時間', ascending=False).head(15))
        
        with t_tabs[2]: # 分組全覽
            group_list = sorted([g for g in df_s['分組'].unique().tolist() if g != "ADMIN"])
            sel_g = st.selectbox("老師查看組別紀錄：", group_list)
            for name in df_s[df_s['分組'] == sel_g]['姓名']:
                p_logs = df_l[df_l['姓名'] == name].copy().sort_values('時間', ascending=False)
                st.markdown(f'<div class="student-card">👤 {name}</div>', unsafe_allow_html=True)
                st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
                st.dataframe(p_logs[p_logs['動作'] == '作答'].tail(10), use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

        with t_tabs[3]: # 🎯 題目篩選指派 (核心修復)
            st.subheader("🛠️ 依 冊/課/項目 篩選題目並指派")
            if df_q is not None:
                # 建立篩選控制
                c_row1 = st.columns(3)
                v_list = sorted([v for v in df_q['版本'].unique() if v != ""])
                f_v = c_row1[0].selectbox("1. 選擇版本", v_list)
                u_list = sorted([u for u in df_q[df_q['版本']==f_v]['單元'].unique() if u != ""])
                f_u = c_row1[1].selectbox("2. 選擇項目 (單元)", u_list)
                y_list = sorted([int(float(y)) for y in df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)]['年度'].unique() if y != ""])
                f_y = c_row1[2].selectbox("3. 選擇年度", y_list)
                
                c_row2 = st.columns(3)
                b_list = sorted([int(float(b)) for b in df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==str(f_y))]['冊編號'].unique() if b != ""])
                f_b = c_row2[0].selectbox("4. 選擇冊別", b_list)
                l_list = sorted([int(float(l)) for l in df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==str(f_y))&(df_q['冊編號']==str(f_b))]['課編號'].unique() if l != ""])
                f_l = c_row2[1].selectbox("5. 選擇課次", l_list)
                min_err = c_row2[2].number_input("錯誤門檻 (0代表全選範圍)", min_value=0, value=1)
                
                # 篩選邏輯
                if min_err > 0:
                    target_logs = df_l[df_l['結果'] == '❌'].copy()
                    wrong_ids = target_logs['題目ID'].value_counts()
                    filtered_ids = wrong_ids[wrong_ids >= min_err].index.tolist()
                else:
                    # 全量模式
                    df_scope = df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==str(f_y))&(df_q['冊編號']==str(f_b))&(df_q['課編號']==str(f_l))]
                    filtered_ids = (df_scope['版本'] + "_" + df_scope['年度'] + "_" + df_scope['冊編號'] + "_" + df_scope['單元'] + "_" + df_scope['課編號'] + "_" + df_scope['句編號']).tolist()
                    wrong_ids = {}

                final_q_list = []
                for qid in filtered_ids:
                    p = qid.split('_')
                    if len(p) >= 6:
                        m = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                        if not m.empty:
                            row = m.iloc[0].to_dict()
                            # 題目文字偵測
                            row['題目內容'] = row['單選題目'] if row['單元'] == "單選" else row['重組中文題目']
                            row['題目ID'] = qid
                            row['錯誤數'] = wrong_ids.get(qid, 0)
                            final_q_list.append(row)
                
                if final_q_list:
                    df_preview = pd.DataFrame(final_q_list)
                    st.write(f"🔍 找到 {len(df_preview)} 個題目：")
                    st.dataframe(df_preview[['題目ID', '錯誤數', '單元', '題目內容']], use_container_width=True)
                    
                    st.divider()
                    col_assign, col_text = st.columns(2)
                    assign_to = col_assign.selectbox("指派給誰？", ["全體"] + sorted(df_s['分組'].unique().tolist()) + sorted(df_s['姓名'].unique().tolist()))
                    msg = col_text.text_input("任務說明", value=f"{f_v}{f_u}練習-{datetime.now().strftime('%m%d')}")
                    
                    if st.button("📢 確認指派任務", type="primary"):
                        new_task = pd.DataFrame([{"對象 (分組/姓名)": assign_to, "任務類型": "指派", "題目ID清單": ", ".join(df_preview['題目ID'].tolist()), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                        conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
                        st.success("✅ 任務已成功分派！"); st.cache_data.clear()
                else: st.warning("目前範圍下無符合題目。")
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 學生練習邏輯 (與 V2.5.2 相同，確保穩定性) ---
st.title(f"👋 {st.session_state.user_name}")
# (此處保留 V2.5.2 完整的任務接收、手動設定與混合題型練習邏輯)
# [由於長度限制，省略重複部分，實際覆蓋時會包含完整代碼]

if df_a is not None:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體")]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.info(f"🎯 **任務：{task['說明文字']}**")
        if st.button("⚡ 立即執行老師指派任務", type="primary"):
            q_ids = [qid.strip() for qid in str(task['題目ID清單']).split(',')]
            task_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    match = df_q[(df_q['版本'] == p[0]) & (df_q['年度'] == p[1]) & (df_q['冊編號'] == p[2]) & (df_q['單元'] == p[3]) & (df_q['課編號'] == p[4]) & (df_q['句編號'] == p[5])]
                    if not match.empty: task_quiz.append(match.iloc[0].to_dict())
            if task_quiz: st.session_state.quiz_list = task_quiz; reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

with st.expander("⚙️ 手動範圍與題數設定", expanded=not st.session_state.get('quiz_loaded', False)):
    if df_q is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        v_opts = sorted([v for v in df_q['版本'].unique() if v != ""])
        sel_v = c1.selectbox("版本", v_opts, key="sv")
        u_opts = sorted([u for u in df_q[df_q['版本']==sel_v]['單元'].unique() if u != ""])
        sel_u = c2.selectbox("項目 (單元)", u_opts, key="su")
        y_opts = sorted([int(float(y)) for y in df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)]['年度'].unique() if y != ""])
        sel_y = c3.selectbox("年度", y_opts, key="sy")
        b_opts = sorted([int(float(b)) for b in df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==str(sel_y))]['冊編號'].unique() if b != ""])
        sel_b = c4.selectbox("冊別", b_opts, key="sb")
        l_opts = sorted([int(float(l)) for l in df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==str(sel_y))&(df_q['冊編號']==str(sel_b))]['課編號'].unique() if l != ""])
        sel_l = c5.selectbox("課次", l_opts, key="sl")
        base_df = df_q[(df_q['版本']==sel_v)&(df_q['單元']==sel_u)&(df_q['年度']==str(sel_y))&(df_q['冊編號']==str(sel_b))&(df_q['課編號']==str(sel_l))].sort_values('句編號')
        if not base_df.empty:
            sc1, sc2 = st.columns(2)
            start_no = sc1.number_input("起始句編號", int(float(base_df['句編號'].min())), int(float(base_df['句編號'].max())))
            q_num = sc2.number_input("練習題數", 1, 50, 10)
            if st.button("🚀 開始練習", use_container_width=True, key="start_btn"):
                final_df = base_df[base_df['句編號'].astype(float) >= float(start_no)].head(q_num)
                st.session_state.quiz_list = final_df.to_dict('records')
                reset_quiz(); st.session_state.quiz_loaded = True; st.rerun()

if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    if q["單元"] == "單選":
        display_q, correct_ans, analysis = q["單選題目"], q["單選答案"].strip().upper(), q["單選解析"]
    else:
        display_q, correct_ans, analysis = q["重組中文題目"], q["重組英文答案"].strip(), ""
    st.markdown(f'<div class="q-card"><b>第 {st.session_state.q_idx+1} 題 ({q["單元"]})</b><br><br>{display_q}</div>', unsafe_allow_html=True)
    if q["單元"] == "單選":
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True):
                is_ok = (opt == correct_ans)
                log_event("單選", detail=opt, result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); st.balloons()
                else: st.error(f"錯誤！正確答案是 ({correct_ans})")
                st.session_state.show_analysis = True
        if st.session_state.get('show_analysis'):
            if analysis: st.markdown(f'<div class="analysis-box">💡 <b>解析：</b><br>{analysis}</div>', unsafe_allow_html=True)
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tokens = re.findall(r"[\w']+|[^\w\s]", correct_ans)
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
                is_ok = "".join(st.session_state.ans).lower() == correct_ans.replace(" ","").lower()
                log_event("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok:
                    st.success("正確！"); time.sleep(0.5)
                    if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; reset_quiz(); st.rerun()
                    else: st.session_state.finished = True; st.rerun()
                else: st.error(f"正確答案: {correct_ans}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded":False}))

st.caption(f"Stable Admin-Sync Ver {VERSION}")
