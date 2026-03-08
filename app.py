# ==============================================================================
# 🧩 英文全能練習系統 (V2.6.0 任務調度中心版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.6.0
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.6.0 [2026-03-08]: 
#   - 新增老師端「任務管理與刪除」功能。
#   - 修正學生端顯示邏輯：無任務時完全隱藏提醒區塊。
#   - 修復時間轉型引起的 TypeError，穩定側邊欄即時動態。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.6.0"
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

# --- 3. 資料載入與 UI 設定 ---
st.session_state.last_activity = time.time()
df_q, df_s, df_a, df_l = load_all_data()

st.markdown("""<style>
    .admin-box { background-color: #f1f8ff; padding: 20px; border-radius: 10px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .student-card { border-left: 4px solid #0366d6; margin-bottom: 5px; padding-left: 10px; font-weight: bold; background: #f8f9fa; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #1e88e5; margin-bottom: 15px; }
    .answer-display { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; min-height: 70px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; font-size: 20px; }
</style>""", unsafe_allow_html=True)

# 側邊欄即時動態
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

# --- 4. 導師全功能管理後台 ---
if st.session_state.group_id == "ADMIN":
    with st.expander("👨‍🏫 導師管理中心 V2.6.0", expanded=True):
        st.markdown('<div class="admin-box">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班紀錄", "🔍 分組全覽", "🎯 指派任務", "📜 任務管理與刪除"])
        
        with t_tabs[2]: # 指派任務
            if df_q is not None:
                cr = st.columns(5)
                f_v = cr[0].selectbox("版本", sorted([v for v in df_q['版本'].unique() if v != ""]), key="admin_v")
                f_u = cr[1].selectbox("項目", sorted([u for u in df_q[df_q['版本']==f_v]['單元'].unique() if u != ""]), key="admin_u")
                f_y = cr[2].selectbox("年度", sorted(list(df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)]['年度'].unique())), key="admin_y")
                f_b = cr[3].selectbox("冊別", sorted(list(df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==f_y)]['冊編號'].unique())), key="admin_b")
                f_l_idx = cr[4].selectbox("課次", sorted(list(df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==f_y)&(df_q['冊編號']==f_b)]['課編號'].unique())), key="admin_l")
                
                df_target = df_q[(df_q['版本']==f_v)&(df_q['單元']==f_u)&(df_q['年度']==f_y)&(df_q['冊編號']==f_b)&(df_q['課編號']==f_l_idx)]
                st.dataframe(df_target.head(10), use_container_width=True)
                
                c_as1, c_as2 = st.columns(2)
                tgt = c_as1.selectbox("指派對象", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]) + sorted(df_s['姓名'].unique().tolist()))
                msg = c_as2.text_input("任務名稱", value="請練習這幾題常錯題目")
                
                if st.button("📢 發佈新任務", type="primary"):
                    ids = (df_target['版本'] + "_" + df_target['年度'] + "_" + df_target['冊編號'] + "_" + df_target['單元'] + "_" + df_target['課編號'] + "_" + df_target['句編號']).tolist()
                    new_a = pd.DataFrame([{"對象 (分組/姓名)": tgt, "任務類型": "指派", "題目ID清單": ", ".join(ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                    conn.update(worksheet="assignments", data=pd.concat([df_a, new_a], ignore_index=True))
                    st.success("任務發佈成功！"); st.cache_data.clear(); st.rerun()

        with t_tabs[3]: # 💡 任務管理與刪除
            st.subheader("📜 目前已發佈的任務清單")
            if df_a is not None and not df_a.empty:
                for i, row in df_a.iterrows():
                    col_info, col_del = st.columns([4, 1])
                    col_info.info(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']} ({row['指派時間']})")
                    if col_del.button("🗑️ 刪除", key=f"del_{i}"):
                        new_df_a = df_a.drop(i)
                        conn.update(worksheet="assignments", data=new_df_a)
                        st.success("任務已刪除！"); st.cache_data.clear(); st.rerun()
            else: st.write("目前無任何任務。")
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 學生端顯示邏輯 (修正) ---
st.title(f"👋 {st.session_state.user_name}")

# 💡 嚴格篩選任務：只有符合對象的才顯示
current_tasks = pd.DataFrame()
if df_a is not None and not df_a.empty:
    current_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | 
                         (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | 
                         (df_a['對象 (分組/姓名)'] == "全體")]

if not current_tasks.empty:
    task = current_tasks.iloc[-1]
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

# 手動設定範圍
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

# --- 6. 練習區 ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    ans = q["單選答案"].strip().upper() if is_mcq else q["重組英文答案"].strip()

    st.markdown(f'<div class="q-card"><b>第 {st.session_state.q_idx+1} 題 ({q["單元"]})</b><br><br>{disp}</div>', unsafe_allow_html=True)
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True):
                ok = (opt == ans)
                log_event("單選", detail=opt, result="✅" if ok else "❌")
                if ok: st.success("正確！"); st.balloons()
                else: st.error(f"錯誤！答案是 ({ans})")
                st.session_state.show_analysis = True
        if st.session_state.get('show_analysis'):
            if q.get("單選解析"): st.warning(f"💡 解析：{q['單選解析']}")
            if st.button("下一題 ➡️"):
                if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx+=1; reset_quiz(); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.markdown(f'<div class="answer-display">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", ans)
        if not st.session_state.shuf: st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.ans, st.session_state.used_history = [], []; st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                ok = "".join(st.session_state.ans).lower() == ans.replace(" ","").lower()
                log_event("重組", detail=" ".join(st.session_state.ans), result="✅" if ok else "❌")
                if ok:
                    st.success("正確！"); time.sleep(0.5)
                    if st.session_state.q_idx+1 < len(st.session_state.quiz_list): st.session_state.q_idx+=1; reset_quiz(); st.rerun()
                    else: st.session_state.finished = True; st.rerun()
                else: st.error(f"正確答案: {ans}")

elif st.session_state.get('finished'):
    st.balloons(); st.success("測驗完成！"); st.button("回首頁", on_click=lambda: st.session_state.update({"quiz_loaded":False}))

st.caption(f"Ver {VERSION}")
