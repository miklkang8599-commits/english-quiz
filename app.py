# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.20 導師函數指派與管理回歸鎖定版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.20
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🔒 核心功能檢核清單 (Core Function Registry):
# ... (前 11 項鎖定) ...
# [編號 12] 🎯 指派任務：create_assignment_logic
# [編號 13] 📜 任務管理：manage_assignment_logic
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.20"

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- [模組 1] 基礎數據處理 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None: df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        if df_s is not None: df_s = df_s.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=2)
        df_l = conn.read(worksheet="logs", ttl=2)
        return df_a, df_l
    except: return None, None

# --- [模組 2] 核心函數 (標準化與 Buffer) ---
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def buffer_log(action_type, detail="", result="-"):
    now_ts = time.time()
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = max(0.1, round(now_ts - start_ts, 1))
    new_entry = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type, "內容": detail, "結果": result, "費時": duration
    }
    if 'log_buffer' not in st.session_state: st.session_state.log_buffer = []
    st.session_state.log_buffer.append(new_entry)

def flush_buffer_to_cloud():
    if st.session_state.get('log_buffer'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_rows = pd.DataFrame(st.session_state.log_buffer)
            updated_logs = pd.concat([old_logs, new_rows], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.log_buffer = []
            st.cache_data.clear() 
        except: pass

# --- [模組 3] 登入 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入系統", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "log_buffer": []})
                    st.rerun()
                else: st.error("❌ 帳密錯誤")
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        flush_buffer_to_cloud(); st.session_state.logged_in = False; st.rerun()

# --- [模組 5] 導師管理中心 (編號 12, 13) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    
    with t_tabs[0]: # 數據追蹤
        c1, c2, c3 = st.columns(3)
        f_g = c1.selectbox("1. 組別", ["全部"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="f_g")
        f_n = c2.selectbox("2. 姓名", ["全部"] + sorted(df_s[df_s['分組']==f_g]['姓名'].tolist() if f_g!="全部" else df_s[df_s['分組']!="ADMIN"]['姓名'].tolist()), key="f_n")
        f_act = c3.selectbox("3. 動作", ["全部", "單選", "重組"], key="f_act")
        dv = df_l.fillna("").copy()
        if f_g != "全部": dv = dv[dv['分組'] == f_g]
        if f_n != "全部": dv = dv[dv['姓名'] == f_n]
        st.dataframe(dv.sort_index(ascending=False).head(100), use_container_width=True)

    with t_tabs[1]: # [編號 12] 🎯 指派任務函數回歸
        st.subheader("🎯 發佈新任務")
        ic1, ic2 = st.columns(2)
        ag = ic1.selectbox("對象組別", ["全體"]+sorted([g for g in df_s['分組'].unique() if g!="ADMIN"]), key="ag_adm")
        an = ic2.multiselect("特定學生 (選填)", sorted(df_s[df_s['分組']==ag]['姓名'].tolist()) if ag!="全體" else [], key="an_adm")
        
        cs = st.columns(6)
        av, au, ay, ab, al = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_a"), cs[1].selectbox("單元", sorted(df_q['單元'].unique()), key="au_a"), cs[2].selectbox("年度", sorted(df_q['年度'].unique()), key="ay_a"), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="ab_a"), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="al_a")
        me = cs[5].number_input("最低錯誤次數", 0, 10, 1, key="err_a")
        
        # 指派題目篩選邏輯
        sq = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
        fids = [f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}" for _, r in sq.iterrows() if len(df_l[(df_l['題目ID']==f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}") & (df_l['結果']=='❌')]) >= me]
        
        st.info(f"🔍 已根據全體歷史紀錄篩選出符合條件的 {len(fids)} 個錯誤題目")
        if st.button("📢 確定發佈任務", type="primary", key="btn_a") and fids:
            new_task = pd.DataFrame([{"對象 (分組/姓名)": (", ".join(an) if an else ag), "任務類型": "補強", "題目ID清單": ", ".join(fids), "說明文字": f"{au} 錯題補強", "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_task], ignore_index=True))
            st.success("✅ 任務指派成功！"); st.cache_data.clear(); st.rerun()

    with t_tabs[2]: # [編號 13] 📜 任務管理函數回歸
        st.subheader("📜 現有任務列表")
        if df_a is not None and not df_a.empty:
            # 倒序排列，最新的在上面
            for i, r in df_a.iloc[::-1].iterrows():
                with st.container():
                    col_info, col_del = st.columns([5, 1])
                    col_info.info(f"📌 **{r['說明文字']}** (對象: {r['對象 (分組/姓名)']}) \n\n 指派時間: {r['指派時間']}")
                    if col_del.button("🗑️ 刪除", key=f"del_task_{i}"):
                        new_df_a = df_a.drop(i)
                        conn.update(worksheet="assignments", data=new_df_a)
                        st.warning("已刪除該任務"); st.cache_data.clear(); st.rerun()
        else:
            st.write("目前尚無任何指派任務。")
    st.stop()

# --- [模組 6] 學生練習區 (核心鎖定) ---
st.title("🚀 英文練習區")

# A. 任務偵測
if df_a is not None and not df_a.empty:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **最新指派：{task['說明文字']}**")
        if st.button("⚡ 執行任務", key="btn_run"):
            t_quiz = []
            for qid in str(task['題目ID清單']).split(','):
                p = qid.strip().split('_')
                if len(p)>=6:
                    m = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                    if not m.empty: t_quiz.append(m.iloc[0].to_dict())
            if t_quiz: st.session_state.update({"quiz_list": t_quiz, "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "log_buffer": []}); st.rerun()

# B. 手動設定 (LOCKED)
with st.expander("⚙️ 手動設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv, su, sy, sb, sl = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v"), c[1].selectbox("項目", sorted(df_q['單元'].unique()), key="s_u"), c[2].selectbox("年度", sorted(df_q['年度'].unique()), key="s_y"), c[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="s_b"), c[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="s_l")
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 該單元共 {len(base)} 題 | 區間：{int(min(nums))}~{int(max(nums))}")
        sc1, sc2 = st.columns(2)
        st_i = sc1.number_input("起始句編號", int(min(nums)), int(max(nums)), int(min(nums)), key="s_i")
        nu_i = sc2.number_input("預計練習題數", 1, 50, 10, key="s_n")
        actual_data = base[base['句編號_int']>=st_i].head(int(nu_i))
        if st.button(f"🚀 載入自選測驗 ({len(actual_data)} 題)", key="s_btn"):
            st.session_state.update({"quiz_list": actual_data.to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "log_buffer": []}); st.rerun()

# C. 練習邏輯
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    ans_key = re.sub(r'[^A-Za-z]', '', str(q["單選答案" if is_mcq else "重組英文答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()
    
    st.markdown(f'<div style="background:#f8f9fa; padding:20px; border-radius:12px; border-left:6px solid #007bff;"><b>第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題</b><br><br><span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"qo_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == ans_key)
                buffer_log("單選", opt, "✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({ans_key})", "show_analysis": True}); st.rerun()
        if st.session_state.get('show_analysis'):
            st.write(st.session_state.current_res)
            if st.button("下一題 ➡️", key="btn_next"):
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()
    else:
        st.write(" ".join(st.session_state.ans) if st.session_state.ans else "......")
        tk = re.findall(r"[\w']+|[^\w\s]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%2].button(t, key=f"qb_{i}", use_container_width=True): st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填題目", key="btn_clear"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查並下一題", type="primary", key="btn_c_mix"):
                is_ok = "".join(st.session_state.ans).lower() == ans_key.replace(" ","").lower()
                buffer_log("重組", " ".join(st.session_state.ans), "✅" if is_ok else "❌")
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()

if st.session_state.get('finished'):
    st.balloons(); st.success("🎉 測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0, "log_buffer": []}))

st.caption(f"Ver {VERSION} (Admin Logic Restored & Locked)")
