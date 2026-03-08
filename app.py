# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.8 導師中心完全修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.8
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.8 [2026-03-08]: 
#   - 深度修復導師管理中心：解決資料未定義報錯與指派任務選單連動失效。
#   - 統一資料讀取介面，確保 ADMIN 與學生角色切換順暢。
#   - 補強任務管理刪除邏輯。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.8"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 資料處理核心 ---
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
        if df_l is not None and not df_l.empty:
            df_l['時間'] = pd.to_datetime(df_l['時間'], errors='coerce')
        return df_a, df_l
    except: return None, None

def log_event_fast(action_type, detail="", result="-"):
    now_ts = time.time()
    start_ts = st.session_state.get('start_time_ts', now_ts)
    duration = max(0.1, round(now_ts - start_ts, 1))
    st.session_state.pending_log = {
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'), 
        "動作": action_type, "內容": detail, "結果": result, "費時": duration
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

# --- 2. 登入邏輯 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

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

# --- 3. 樣式與通用資料 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .admin-container { background-color: #f1f8ff; padding: 25px; border-radius: 15px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 12px; border-left: 6px solid #007bff; margin-bottom: 15px; }
    .sidebar-scroll { max-height: 250px; overflow-y: auto; background: #fdfdfd; border: 1px solid #eee; padding: 8px; border-radius: 8px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    
    # 同組動態 (僅學生模式顯示)
    if st.session_state.view_mode != "管理後台" and df_l is not None:
        st.divider()
        st.subheader("🏆 同組動態")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        if not gl.empty:
            st.markdown('<div class="sidebar-scroll">', unsafe_allow_html=True)
            for member in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名']):
                correct = len(gl[(gl['姓名']==member) & (gl['結果']=='✅')])
                st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {member}</span><b>{correct} 題</b></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 👨‍🏫 導師管理中心 (深度修正) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    with st.container():
        st.markdown('<div class="admin-container">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
        
        with t_tabs[0]: # 數據追蹤
            if df_l is not None:
                st.write("最新 50 筆作答紀錄")
                st.dataframe(df_l.sort_values('時間', ascending=False).head(50), use_container_width=True)
            else: st.info("尚無紀錄")

        with t_tabs[1]: # 🎯 指派任務 (同步連動選單)
            c1, c2 = st.columns(2)
            g_opts = ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"])
            adm_g = c1.selectbox("1. 選擇組別", g_opts, key="adm_g")
            adm_n = c2.multiselect("2. 選擇特定學生", sorted(df_s[df_s['分組']==adm_g]['姓名'].tolist()) if adm_g != "全體" else [], key="adm_n")
            
            cs = st.columns(5)
            # 老師專用五級連動選單
            av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av")
            au = cs[1].selectbox("項目", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au")
            ay = cs[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="ay")
            ab = cs[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="ab")
            al = cs[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="al")
            
            target_q = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
            st.write(f"已選定 {len(target_q)} 題")
            
            c_btn1, c_btn2 = st.columns(2)
            msg = c_btn1.text_input("說明文字", value=f"{au}補強", key="adm_msg")
            if c_btn2.button("📢 確認指派", type="primary", use_container_width=True):
                ids = (target_q['版本'] + "_" + target_q['年度'] + "_" + target_q['冊編號'] + "_" + target_q['單元'] + "_" + target_q['課編號'] + "_" + target_q['句編號']).tolist()
                tgt = ", ".join(adm_n) if adm_n else adm_g
                new_a = pd.DataFrame([{"對象 (分組/姓名)": tgt, "任務類型": "指派", "題目ID清單": ", ".join(ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                conn.update(worksheet="assignments", data=pd.concat([df_a, new_a], ignore_index=True))
                st.success("任務指派成功！"); st.cache_data.clear(); st.rerun()

        with t_tabs[2]: # 📜 任務管理
            if df_a is not None and not df_a.empty:
                for i, row in df_a.iterrows():
                    ci, cd = st.columns([4, 1])
                    ci.info(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                    if cd.button("🗑️ 刪除", key=f"adm_del_{i}"):
                        conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# --- 6. 🚀 學生練習介面 (穩定版) ---
st.title("🚀 英文練習區")

# A. 任務偵測
if df_a is not None and not df_a.empty:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **最新任務：{task['說明文字']}**")
        if st.button("⚡ 開始執行任務題目", type="primary"):
            q_ids = [qid.strip() for qid in str(task['題目ID清單']).split(',')]
            t_quiz = []
            for qid in q_ids:
                p = qid.split('_')
                if len(p) >= 6:
                    m = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                    if not m.empty: t_quiz.append(m.iloc[0].to_dict())
            if t_quiz:
                st.session_state.update({"quiz_list": t_quiz, "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                st.rerun()

# B. 手動設定
with st.expander("⚙️ 手動設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
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
        sc1, sc2 = st.columns(2)
        start_in = sc1.number_input("起始編號", int(base['句編號_int'].min()), int(base['句編號_int'].max()), int(base['句編號_int'].min()))
        num_in = sc2.number_input("題數", 1, 50, 10)
        if st.button("🚀 載入自選練習", use_container_width=True):
            st.session_state.update({"quiz_list": base[base['句編號_int']>=start_in].head(int(num_in)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# C. 練習核心
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    clean_ans = re.sub(r'[^A-Za-z]', '', str(q["單選答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()

    st.markdown(f'<div class="q-card"><b>📝 題目 {st.session_state.q_idx+1} (句編號: {q["句編號"]})</b><br><br><span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"qopt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event_fast("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({clean_ans})", "show_analysis": True})
                st.rerun()
        if st.session_state.get('show_analysis'):
            if "✅" in st.session_state.current_res: st.success(st.session_state.current_res)
            else: st.error(st.session_state.current_res)
            if st.button("下一題 ➡️", type="primary"):
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        # 重組邏輯 (略)
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:22px;">'
                    f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"qbtn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event_fast("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()

# D. 個人紀錄
st.divider()
st.subheader("📜 我的學習紀錄")
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(10)
    for _, row in my_logs.iterrows():
        st.markdown(f'<div style="border-bottom:1px solid #eee; padding:5px; font-size:13px; display:flex; justify-content:space-between;"><span>🕒 {str(row["時間"]).split(" ")[-1][:8]} | <b>{str(row["題目ID"]).split("_")[-1]}</b></span><span>結果: {row["結果"]} | {row["費時"]}s</span></div>', unsafe_allow_html=True)

st.caption(f"Ver {VERSION}")
