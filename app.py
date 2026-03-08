# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.6 完整題目ID組合版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.6
# 📅 更新日期: 2026-03-09
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.6"

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

# --- 3. 樣式載入 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

st.markdown("""<style>
    .admin-container { background-color: #f1f8ff; padding: 25px; border-radius: 15px; border: 2px solid #0366d6; margin-bottom: 20px; }
    .sidebar-scroll { max-height: 250px; overflow-y: auto; background: #fdfdfd; border: 1px solid #eee; padding: 8px; border-radius: 8px; margin-bottom: 10px; }
    .q-card { background-color: #f8f9fa; padding: 20px; border-radius: 12px; border-left: 6px solid #007bff; margin-bottom: 15px; }
</style>""", unsafe_allow_html=True)

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式切換：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    
    # 同組動態 (組員與編號組合)
    if (st.session_state.view_mode == "練習模式" or st.session_state.group_id != "ADMIN") and df_l is not None:
        st.divider()
        st.subheader("🏆 同組今日排行榜")
        my_g = st.session_state.group_id
        gl = df_l[df_l['分組'] == my_g].copy()
        st.markdown('<div class="sidebar-scroll">', unsafe_allow_html=True)
        for m in sorted(df_s[df_s['分組'] == my_g]['姓名']):
            c_today = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {m}</span><b>{c_today} 題</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.subheader("🕒 同組最新活動")
        st.markdown('<div class="sidebar-scroll" style="max-height:180px;">', unsafe_allow_html=True)
        for _, r in gl[gl['動作'].str.contains('單選|重組', na=False)].sort_index(ascending=False).head(8).iterrows():
            p = str(r['題目ID']).split('_')
            # 💡 題號組合：版本_年度_冊_項目_課_句
            disp = f"{p[0]}_{p[1]}_B{p[2]}_{p[3]}_L{p[4]}_{p[5]}" if len(p)>=6 else r['題目ID']
            st.markdown(f'<div style="font-size:11px; margin-bottom:4px; border-bottom:1px dotted #eee;">👤 {r["姓名"]} {r["結果"]}<br>{disp}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. 👨‍🏫 導師管理中心 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    
    with t_tabs[0]: # 📊 數據追蹤 (六重篩選)
        if df_l is not None and not df_l.empty:
            c1, c2, c3 = st.columns(3)
            f_group = c1.selectbox("1. 依組別", ["全部組別"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]))
            n_opts = sorted(df_s[df_s['分組']==f_group]['姓名'].tolist()) if f_group != "全部組別" else sorted(df_s[df_s['分組']!="ADMIN"]['姓名'].tolist())
            f_name = c2.selectbox("2. 依姓名", ["全部學生"] + n_opts)
            f_act = c3.selectbox("3. 依動作", ["全部動作", "單選", "重組", "登入"])
            
            c4, c5, c6 = st.columns(3)
            f_ver = c4.selectbox("4. 依版本", ["全部版本"] + sorted(df_q['版本'].unique().tolist()))
            f_year = c5.selectbox("5. 依年度", ["全部年度"] + sorted(df_q['年度'].unique().tolist()))
            f_task = c6.selectbox("6. 依任務", ["全部任務"] + (df_a['說明文字'].unique().tolist() if df_a is not None else []))

            df_view = df_l.fillna("").copy()
            if f_group != "全部組別": df_view = df_view[df_view['分組'] == f_group]
            if f_name != "全部學生": df_view = df_view[df_view['姓名'] == f_name]
            if f_act != "全部動作": df_view = df_view[df_view['動作'].str.contains(f_act, na=False)]
            if f_ver != "全部版本": df_view = df_view[df_view['題目ID'].str.startswith(f_ver)]
            if f_year != "全部年度": df_view = df_view[df_view['題目ID'].str.contains(f"_{f_year}_", na=False)]
            if f_task != "全部任務":
                tk_qids = str(df_a[df_a['說明文字']==f_task].iloc[0]['題目ID清單']).split(',')
                df_view = df_view[df_view['題目ID'].isin([q.strip() for q in tk_qids])]
            
            st.dataframe(df_view.sort_index(ascending=False).head(200), use_container_width=True)
        else: st.info("目前雲端尚無作答數據。")

    with t_tabs[1]: # 🎯 指派任務 (略)
        ic1, ic2 = st.columns(2)
        adm_g = ic1.selectbox("指派組別", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="adm_as_g")
        adm_n = ic2.multiselect("指定學生", sorted(df_s[df_s['分組']==adm_g]['姓名'].tolist()) if adm_g != "全體" else [], key="adm_as_n")
        cs = st.columns(6)
        av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_as")
        au = cs[1].selectbox("項目", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au_as")
        ay = cs[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="ay_as")
        ab = cs[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="ab_as")
        al = cs[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="al_as")
        min_e = cs[5].number_input("最低錯誤數", 0, 10, 1, key="adm_e_as")
        
        scope_q = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
        final_ids = []
        if df_l is not None:
            for _, row in scope_q.iterrows():
                qid = f"{row['版本']}_{row['年度']}_{row['冊編號']}_{row['單元']}_{row['課編號']}_{row['句編號']}"
                err_cnt = len(df_l[(df_l['題目ID']==qid) & (df_l['結果']=='❌')])
                if err_cnt >= min_e: final_ids.append(qid)
        st.info(f"🔍 符合條件題目：{len(final_ids)} 題")
        msg = st.text_input("任務說明", value=f"{au}補強", key="adm_msg_as")
        if st.button("📢 發佈任務", type="primary", use_container_width=True) and final_ids:
            new_row = pd.DataFrame([{"對象 (分組/姓名)": (", ".join(adm_n) if adm_n else adm_g), "任務類型": "指派", "題目ID清單": ", ".join(final_ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_row], ignore_index=True))
            st.success("任務指派已成功！"); st.cache_data.clear(); st.rerun()

    with t_tabs[2]: # 📜 任務管理 (略)
        if df_a is not None and not df_a.empty:
            for i, row in df_a.iterrows():
                ci, cd = st.columns([4, 1])
                ci.warning(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                if cd.button("🗑️ 刪除", key=f"adm_del_{i}"):
                    conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
    st.stop()

# --- 6. 🚀 學生練習介面 ---
st.title("🚀 英文練習區")

# A. 任務偵測
if df_a is not None and not df_a.empty:
    my_tasks = df_a[(df_a['對象 (分組/姓名)'] == st.session_state.user_name) | (df_a['對象 (分組/姓名)'] == st.session_state.group_id) | (df_a['對象 (分組/姓名)'] == "全體") | (df_a['對象 (分組/姓名)'].str.contains(st.session_state.user_name, na=False))]
    if not my_tasks.empty:
        task = my_tasks.iloc[-1]
        st.error(f"🎯 **最新任務：{task['說明文字']}**")
        if st.button("⚡ 執行此任務"):
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

# B. 手動設定 (題數統計)
with st.expander("⚙️ 手動設定練習範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="sv_s")
    su = c[1].selectbox("項目", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="su_s")
    sy = c[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="sy_s")
    sb = c[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="sb_s")
    sl = c[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="sl_s")
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 該範圍共有 **{len(base)}** 題 | 句編號區間：{int(min(nums))} ~ {int(max(nums))}")
        sc1, sc2 = st.columns(2)
        st_i = sc1.number_input("起始句編號", int(min(nums)), int(max(nums)), int(min(nums)), key="st_i_s")
        num_i = sc2.number_input("預計練習題數", 1, 50, 10, key="num_i_s")
        actual_cnt = len(base[base['句編號_int']>=st_i].head(int(num_i)))
        if st.button(f"🚀 載入測驗 (共 {actual_cnt} 題)"):
            st.session_state.update({"quiz_list": base[base['句編號_int']>=st_i].head(int(num_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

# C. 核心練習區 (單選 + 重組)
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    is_mcq = "單選" in q["單元"]
    disp = q["單選題目"] if is_mcq else q["重組中文題目"]
    clean_ans = re.sub(r'[^A-Za-z]', '', str(q["單選答案"] if is_mcq else q["重組英文答案"])).upper() if is_mcq else str(q["重組英文答案"]).strip()

    st.markdown(f'<div class="q-card"><b>第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題 (句編號: {q["句編號"]})</b><br><br><span style="font-size:22px;">{disp}</span></div>', unsafe_allow_html=True)
    
    if is_mcq:
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if cols[i].button(opt, key=f"qopt_{i}", use_container_width=True, disabled=st.session_state.get('show_analysis', False)):
                is_ok = (opt == clean_ans)
                log_event_fast("單選", detail=opt, result="✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案是 ({clean_ans})", "show_analysis": True}); st.rerun()
        if st.session_state.get('show_analysis'):
            if "✅" in st.session_state.current_res: st.success(st.session_state.current_res)
            else: st.error(st.session_state.current_res)
            if st.button("下一題 ➡️", type="primary"):
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; st.rerun()
    else:
        st.markdown(f'<div style="background:white; padding:15px; border-radius:10px; border:1px solid #ddd; min-height:70px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:center; font-size:22px;">{" ".join(st.session_state.ans) if st.session_state.ans else "......"}</div>', unsafe_allow_html=True)
        tk = re.findall(r"[\w']+|[^\w\s]", clean_ans)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(2)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%2].button(t, key=f"qbtn_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if st.button("🔄 重填"): st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        if len(st.session_state.ans) == len(tk):
            if st.button("✅ 檢查答案並繼續", type="primary"):
                is_ok = "".join(st.session_state.ans).lower() == clean_ans.replace(" ","").lower()
                log_event_fast("重組", detail=" ".join(st.session_state.ans), result="✅" if is_ok else "❌")
                flush_pending_log()
                if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                    st.session_state.q_idx += 1; st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()}); st.rerun()
                else: st.session_state.finished = True; st.rerun()

# D. 個人紀錄 (💡 完整組合題號顯示)
st.divider()
st.subheader("📜 最近我的練習紀錄")
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(15)
    log_html = '<div class="log-container">'
    for _, row in my_logs.iterrows():
        p = str(row['題目ID']).split('_')
        # 💡 完整編號組合：版本_年度_冊_單元(項目)_課_句
        disp_qid = f"{p[0]}_{p[1]}_B{p[2]}_{p[3]}_L{p[4]}_{p[5]}" if len(p) >= 6 else row['題目ID']
        c = "green" if row['結果'] == "✅" else "red"
        log_html += f'<div style="border-bottom:1px solid #eee; padding:5px; font-size:13px; display:flex; justify-content:space-between;"><span>🕒 {str(row["時間"])[-8:]} | <b>{disp_qid}</b></span><span>結果: <b style="color:{c}">{row["結果"]}</b> | {row["費時"]}s</span></div>'
    log_html += '</div>'
    st.markdown(log_html, unsafe_allow_html=True)

if st.session_state.get('finished'):
    st.balloons()
    if st.button("返回設定頁"): 
        st.session_state.update({"quiz_loaded": False, "finished": False, "q_idx": 0})
        st.rerun()

st.caption(f"Ver {VERSION}")
