# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.7 十一項功能完備版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.7
# 📅 更新日期: 2026-03-09
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.7"

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# --- 1. 資料處理核心 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions")
        df_s = conn.read(worksheet="students")
        if df_q is not None:
            df_q = df_q.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        if df_s is not None:
            df_s = df_s.fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=2)
        df_l = conn.read(worksheet="logs", ttl=2)
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

# --- 2. 登入系統 (核心功能 #2: 補零相容) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 英文系統登入")
        input_id = st.text_input("帳號 (後四碼)", placeholder="0097")
        input_pw = st.text_input("密碼", type="password")
        if st.button("🚀 登入系統", use_container_width=True):
            if df_s is not None:
                def clean_val(v): return str(v).split('.')[0].strip().zfill(4)
                target_id = clean_val(input_id)
                target_pw = str(input_pw).split('.')[0].strip()
                df_s['match_id'] = df_s['帳號'].apply(clean_val)
                df_s['match_pw'] = df_s['密碼'].apply(lambda x: str(x).split('.')[0].strip())
                user = df_s[df_s['match_id'] == target_id]
                if not user.empty and user.iloc[0]['match_pw'] == target_pw:
                    st.session_state.update({"logged_in": True, "user_id": f"EA{target_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "last_activity": time.time()})
                    st.rerun()
                else: st.error("❌ 登入失敗")
    st.stop()

# --- 3. 基礎架構載入 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .admin-container { background-color: #f1f8ff; padding: 25px; border-radius: 15px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .sidebar-scroll { max-height: 250px; overflow-y: auto; background: #fdfdfd; border: 1px solid #eee; padding: 8px; border-radius: 8px; margin-bottom: 10px; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 12px; border-left: 6px solid #007bff; margin-bottom: 15px; }
</style>""", unsafe_allow_html=True)

# --- 4. 側邊欄：功能點 #8, #9 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    if (st.session_state.view_mode == "練習模式" or st.session_state.group_id != "ADMIN") and df_l is not None:
        st.divider()
        st.subheader("🏆 今日對題排行")
        my_g = st.session_state.group_id
        gl = df_l[df_l['分組'] == my_g].copy()
        st.markdown('<div class="sidebar-scroll">', unsafe_allow_html=True)
        for m in sorted(df_s[df_s['分組'] == my_g]['姓名']):
            cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {m}</span><b>{cnt} 題</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.subheader("🕒 最新編號組合")
        st.markdown('<div class="sidebar-scroll" style="max-height:150px;">', unsafe_allow_html=True)
        for _, r in gl[gl['動作'].str.contains('單選|重組', na=False)].sort_index(ascending=False).head(8).iterrows():
            p = str(r['題目ID']).split('_')
            disp = f"{p[0]}_{p[1]}_B{p[2]}_{p[3]}_L{p[4]}_{p[5]}" if len(p)>=6 else r['題目ID']
            st.markdown(f'<div style="font-size:11px; margin-bottom:4px; border-bottom:1px dotted #eee;">👤 {r["姓名"]} {r["結果"]}<br>{disp}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 👨‍🏫 導師管理中心：功能點 #3, #4, #5 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    with t_tabs[0]: # 💡 六重篩選
        if df_l is not None and not df_l.empty:
            c1, c2, c3 = st.columns(3)
            f_g = c1.selectbox("1. 組別", ["全部"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]))
            n_opts = sorted(df_s[df_s['分組']==f_g]['姓名'].tolist()) if f_g != "全部" else sorted(df_s[df_s['分組']!="ADMIN"]['姓名'].tolist())
            f_n = c2.selectbox("2. 姓名", ["全部學生"] + n_opts)
            f_act = c3.selectbox("3. 動作", ["全部動作", "單選", "重組", "登入"])
            c4, c5, c6 = st.columns(3)
            f_v = c4.selectbox("4. 版本", ["全部版本"] + sorted(df_q['版本'].unique().tolist()))
            f_y = c5.selectbox("5. 年度", ["全部年度"] + sorted(df_q['年度'].unique().tolist()))
            f_t = c6.selectbox("6. 任務", ["全部任務"] + (df_a['說明文字'].unique().tolist() if df_a is not None else []))
            df_v = df_l.fillna("").copy()
            if f_g != "全部": df_v = df_v[df_v['分組'] == f_g]
            if f_n != "全部學生": df_v = df_view[df_view['姓名'] == f_n]
            if f_act != "全部動作": df_v = df_v[df_v['動作'].str.contains(f_act, na=False)]
            if f_v != "全部版本": df_v = df_v[df_v['題目ID'].str.startswith(f_v)]
            if f_y != "全部年度": df_v = df_v[df_v['題目ID'].str.contains(f"_{f_y}_", na=False)]
            if f_t != "全部任務":
                tk_qids = str(df_a[df_a['說明文字']==f_t].iloc[0]['題目ID清單']).split(',')
                df_v = df_v[df_v['題目ID'].isin([q.strip() for q in tk_qids])]
            st.dataframe(df_v.sort_index(ascending=False).head(200), use_container_width=True)
    with t_tabs[1]: # 🎯 指派任務
        ic1, ic2 = st.columns(2)
        adm_g = ic1.selectbox("指派組別", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="adm_g")
        adm_n = ic2.multiselect("指定學生", sorted(df_s[df_s['分組']==adm_g]['姓名'].tolist()) if adm_g != "全體" else [], key="adm_n")
        cs = st.columns(6)
        av, au, ay, ab, al = cs[0].selectbox("版本", sorted(df_q['版本'].unique())), cs[1].selectbox("項目", sorted(df_q['單元'].unique())), cs[2].selectbox("年度", sorted(df_q['年度'].unique())), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique())), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()))
        min_e = cs[5].number_input("最低錯誤數", 0, 10, 1)
        scope_q = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
        final_ids = []
        for _, row in scope_q.iterrows():
            qid = f"{row['版本']}_{row['年度']}_{row['冊編號']}_{row['單元']}_{row['課編號']}_{row['句編號']}"
            if len(df_l[(df_l['題目ID']==qid) & (df_l['結果']=='❌')]) >= min_e: final_ids.append(qid)
        st.info(f"🔍 篩選出 {len(final_ids)} 題")
        msg = st.text_input("任務說明", value=f"{au}補強")
        if st.button("📢 發佈指派任務", type="primary") and final_ids:
            new_a = pd.DataFrame([{"對象 (分組/姓名)": (", ".join(adm_n) if adm_n else adm_g), "任務類型": "指派", "題目ID清單": ", ".join(final_ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_a], ignore_index=True)); st.success("成功！"); st.cache_data.clear(); st.rerun()
    with t_tabs[2]: # 📜 任務管理
        if df_a is not None and not df_a.empty:
            for i, row in df_a.iterrows():
                ci, cd = st.columns([4, 1])
                ci.warning(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                if cd.button("🗑️ 刪除", key=f"del_{i}"): conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
    st.stop()

# --- 6. 🚀 學生練習介面：功能點 #6, #7, #10, #11 ---
st.title("🚀 英文練習區")
if df_a is not None and not df_a.empty:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **任務：{task['說明文字']}**")
        if st.button("⚡ 執行此任務"):
            t_quiz = []
            for qid in str(task['題目ID清單']).split(','):
                p = qid.strip().split('_')
                if len(p)>=6:
                    m = df_q[(df_q['版本']==p[0])&(df_q['年度']==p[1])&(df_q['冊編號']==p[2])&(df_q['單元']==p[3])&(df_q['課編號']==p[4])&(df_q['句編號']==p[5])]
                    if not m.empty: t_quiz.append(m.iloc[0].to_dict())
            if t_quiz: st.session_state.update({"quiz_list": t_quiz, "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()

with st.expander("⚙️ 手動設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv, su, sy, sb, sl = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="sv"), c[1].selectbox("項目", sorted(df_q['單元'].unique()), key="su"), c[2].selectbox("年度", sorted(df_q['年度'].unique()), key="sy"), c[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="sb"), c[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="sl")
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 該範圍共 **{len(base)}** 題")
        sc1, sc2 = st.columns(2)
        st_i = sc1.number_input("起始句編號", int(min(nums)), int(max(nums)), int(min(nums)))
        num_i = sc2.number_input("題數", 1, 50, 10)
        actual = len(base[base['句編號_int']>=st_i].head(int(num_i)))
        if st.button(f"🚀 載入測驗 (共 {actual} 題)"):
            st.session_state.update({"quiz_list": base[base['句編號_int']>=st_i].head(int(num_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()

if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    ans_key = re.sub(r'[^A-Za-z]', '', str(q["單選答案" if is_mcq else "重組英文答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()
    st.markdown(f'<div class="q-card"><b>第 {st.session_state.q_idx+1} 題 (句編號: {q["句編號"]})</b><br><br><span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"qopt_{i}", disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == ans_key)
                log_event_fast("單選", opt, "✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅" if is_ok else f"❌ 答案({ans_key})", "show_analysis": True}); st.rerun()
        if st.session_state.get('show_analysis'):
            st.write(st.session_state.current_res)
            if st.button("下一題 ➡️"):
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.write(" ".join(st.session_state.ans) if st.session_state.ans else "......")
        tk = re.findall(r"[\w']+|[^\w\s]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%2].button(t, key=f"qbtn_{i}"): st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查"):
                is_ok = "".join(st.session_state.ans).lower() == ans_key.replace(" ","").lower()
                log_event_fast("重組", " ".join(st.session_state.ans), "✅" if is_ok else "❌")
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list): st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; st.rerun()

st.divider() # 功能點 #10 練習紀錄
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(15)
    log_html = '<div class="log-container">'
    for _, row in my_logs.iterrows():
        p = str(row['題目ID']).split('_')
        disp_qid = f"{p[0]}_{p[1]}_B{p[2]}_{p[3]}_L{p[4]}_{p[5]}" if len(p) >= 6 else row['題目ID']
        log_html += f'<div style="font-size:13px;">🕒 {str(row["時間"])[-8:]} | <b>{disp_qid}</b> | {row["結果"]} | {row["費時"]}s</div>'
    st.markdown(log_html + "</div>", unsafe_allow_html=True)

if st.session_state.get('finished'):
    st.balloons(); st.button("回設定頁", on_click=lambda: st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0}))

st.caption(f"Stable Check Ver {VERSION}")
