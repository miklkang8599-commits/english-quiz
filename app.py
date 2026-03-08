
# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.4 角色分流版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.4
# 📅 更新日期: 2026-03-08
#
# 📜 【GitHub 開發日誌】
# ------------------------------------------------------------------------------
# V2.7.4 [2026-03-08]: 
#   - 角色分流：老師登入預設顯示管理後台，學生預設顯示練習區。
#   - 變數隔離：修正老師指派任務與學生手動設定選單 Key 值衝突。
#   - 介面純淨化：移除冗餘的摺疊層級，提升操作直覺性。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.4"
IDLE_TIMEOUT = 300 

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 核心資料處理 ---
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
if 'view_mode' not in st.session_state: st.session_state.view_mode = "Auto"

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

# --- 3. 樣式與側邊欄 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .admin-container { background-color: #f1f8ff; padding: 25px; border-radius: 15px; border: 2px solid #0366d6; margin-bottom: 30px; }
    .student-container { background-color: #ffffff; padding: 10px; }
    .log-container { max-height: 250px; overflow-y: auto; background: white; border: 1px solid #ddd; padding: 10px; border-radius: 8px; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.info("模式切換")
        st.session_state.view_mode = st.radio("當前視野：", ["管理後台", "學生練習模式"])
    if st.button("🚪 登出系統", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    
    st.divider()
    if df_l is not None and not df_l.empty:
        st.subheader("📊 同組即時動態")
        gl = df_l[(df_l['分組'] == st.session_state.group_id) & (df_l['分組'] != "ADMIN")].sort_values('時間', ascending=False)
        if not gl.empty:
            online_cutoff = datetime.now() - pd.Timedelta(minutes=10)
            online = gl[gl['時間'] > online_cutoff]['姓名'].unique()
            st.write(f"🟢 在線：{', '.join(online) if len(online)>0 else '僅您'}")
            for _, r in gl[gl['動作'].str.contains('作答|單選|重組', na=False)].head(3).iterrows():
                st.caption(f"👤 {r['姓名']}: {'✅' if r['結果']=='✅' else '❌'} (題:{str(r['題目ID']).split('_')[-1]})")

# --- 4. 👨‍🏫 老師管理介面 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    with st.container():
        st.markdown('<div class="admin-container">', unsafe_allow_html=True)
        t_tabs = st.tabs(["📊 全班數據", "🔍 分組追蹤", "🎯 指派任務", "📜 任務管理"])
        
        with t_tabs[2]: # 指派任務
            cr = st.columns(5)
            # 使用 admin_ 前綴避免與學生選單衝突
            av = cr[0].selectbox("版本", sorted(df_q['版本'].unique()), key="admin_v")
            au = cr[1].selectbox("項目", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="admin_u")
            ay = cr[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="admin_y")
            ab = cr[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="admin_b")
            al = cr[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="admin_l")
            
            target_q = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
            st.write(f"已選定 {len(target_q)} 題")
            
            c_as1, c_as2 = st.columns(2)
            tgt = c_as1.selectbox("對象", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="admin_tgt")
            msg = c_as2.text_input("任務說明", value=f"{au}補強", key="admin_msg")
            
            if st.button("📢 確認發佈任務", type="primary"):
                ids = (target_q['版本'] + "_" + target_q['年度'] + "_" + target_q['冊編號'] + "_" + target_q['單元'] + "_" + target_q['課編號'] + "_" + target_q['句編號']).tolist()
                new_a = pd.DataFrame([{"對象 (分組/姓名)": tgt, "任務類型": "指派", "題目ID清單": ", ".join(ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                conn.update(worksheet="assignments", data=pd.concat([df_a, new_a], ignore_index=True))
                st.success("任務發佈成功！"); st.cache_data.clear(); st.rerun()
        
        with t_tabs[3]: # 任務管理
            if df_a is not None and not df_a.empty:
                for i, row in df_a.iterrows():
                    c_i, c_d = st.columns([4, 1])
                    c_i.info(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                    if c_d.button("🗑️ 刪除", key=f"del_{i}"):
                        conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop() # 老師看管理時，不顯示下方的學生練習區

# --- 5. 🚀 學生練習介面 ---
st.title("🚀 英文練習區")

# A. 指派任務偵測
current_tasks = pd.DataFrame()
if df_a is not None and not df_a.empty:
    current_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體")]

if not current_tasks.empty:
    task = current_tasks.iloc[-1]
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
            st.session_state.quiz_list = t_quiz
            st.session_state.update({"q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# B. 手動設定區
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
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 範圍共 {len(base)} 題 | 編號：{int(min(nums))} ~ {int(max(nums))}")
        sc1, sc2 = st.columns(2)
        start = sc1.number_input("起始編號", int(min(nums)), int(max(nums)), int(min(nums)), key="start_n")
        num = sc2.number_input("練習題數", 1, 50, 10, key="num_n")
        if st.button("🚀 載入自選練習", use_container_width=True):
            st.session_state.quiz_list = base[base['句編號_int'] >= start].head(int(num)).to_dict('records')
            st.session_state.update({"q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# C. 核心練習邏輯 (略，同 V2.7.3)
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    clean_ans = re.sub(r'[^A-Za-z]', '', str(q["單選答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()

    st.markdown(f'''<div style="background:#f0f7ff; padding:20px; border-radius:10px; border-left:6px solid #007bff; margin-bottom:15px;">
                <b>📝 題目 {st.session_state.q_idx+1} / {len(st.session_state.quiz_list)} (句編號: {q["句編號"]})</b><br><br>
                <span style="font-size:22px;">{disp}</span></div>''', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event_fast("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.current_res = ("✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({clean_ans})")
                st.session_state.show_analysis = True; st.rerun()
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
        # 重組題介面
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:22px;">'
                    f'{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.used_history:
                if bs[i%2].button(t, key=f"btn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event_fast("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                if is_ok: st.success("正確！"); time.sleep(0.5)
                else: st.error(f"正確答案: {clean_ans}")
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                    st.rerun()
                else: st.session_state.finished = True; st.rerun()

# D. 底部個人紀錄
st.divider()
st.subheader("📜 我的學習紀錄")
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(15)
    log_html = '<div class="log-container">'
    for _, row in my_logs.iterrows():
        qid = str(row['題目ID'])
        display = f"句編: {qid.split('_')[-1]}" if "_" in qid else row['動作']
        color = "green" if row['結果'] == "✅" else "red"
        log_html += f'<div class="log-entry"><span>🕒 {str(row["時間"]).split(" ")[-1][:8]} | <b>{display}</b></span><span>結果: <b style="color:{color}">{row["結果"]}</b> | {row["費時"]}s</span></div>'
    log_html += '</div>'
    st.markdown(log_html, unsafe_allow_html=True)

st.caption(f"Ver {VERSION}")
