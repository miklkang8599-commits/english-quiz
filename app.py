# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.15 內建 11 項核心檢核字典版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.15
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🛠️ 核心功能自檢字典 (Core Audit Dictionary):
# 1. [角色分流] 管理/練習模式獨立 (Module 3, 5, 6)
# 2. [登入補零] 帳密 standardize 強制執行 (Module 2, 3)
# 3. [六重篩選] 組別、姓名、動作、版本、年度、任務 (Module 5-Tab0)
# 4. [任務指派] 最低錯誤數過濾 logic (Module 5-Tab1)
# 5. [任務管理] 已發佈清單與刪除 (Module 5-Tab2)
# 6. [學生任務] 自動偵測並一鍵執行 (Module 6-A)
# 7. [手動設定] 起始編號(s_i)、題數(s_n)、統計顯示 (Module 6-B) -> **LOCKED**
# 8. [同組排行] 側邊欄排行榜顯示 (Module 4)
# 9. [完整題號] [版本_年度_B冊_項目_L課_句] (Module 4, 6-D)
# 10. [毫秒換題] Buffer 緩衝寫入機制 (Module 2, 6-C)
# 11. [數據一致] 測驗結束整批回填雲端 (Module 2, 6-C)
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.15"

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

# --- [模組 2] 核心函數鎖定 (檢核點 2, 10, 11) ---
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

# --- [模組 3] 權限與登入 (檢核點 1, 2) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'view_mode' not in st.session_state: st.session_state.view_mode = "管理後台"

if not st.session_state.logged_in:
    df_q, df_s = load_static_data()
    _, c_login, _ = st.columns([1, 1.2, 1])
    with c_login:
        st.title("🧩 系統登入")
        i_id = st.text_input("帳號 (例如: 0097)", key="l_id")
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

# --- [模組 4] 側邊欄與動態 (檢核點 8, 9) ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        flush_buffer_to_cloud(); st.session_state.logged_in = False; st.rerun()
    if (st.session_state.view_mode == "練習模式" or st.session_state.group_id != "ADMIN") and df_l is not None:
        st.divider()
        st.subheader("🏆 今日對題排行")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        st.markdown('<div style="max-height:200px; overflow-y:auto; background:#f9f9f9; padding:8px; border-radius:8px;">', unsafe_allow_html=True)
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名']):
            cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="display:flex; justify-content:space-between; font-size:13px;"><span>👤 {m}</span><b>{cnt} 題</b></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --- [模組 5] 管理中心 (檢核點 3, 4, 5) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    with t_tabs[0]: # 六重篩選
        c1, c2, c3 = st.columns(3)
        f_g = c1.selectbox("1. 組別", ["全部"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="f_g")
        f_n = c2.selectbox("2. 姓名", ["全部"] + sorted(df_s[df_s['分組']==f_g]['姓名'].tolist() if f_g!="全部" else df_s[df_s['分組']!="ADMIN"]['姓名'].tolist()), key="f_n")
        f_act = c3.selectbox("3. 動作", ["全部", "單選", "重組"], key="f_act")
        c4, c5, c6 = st.columns(3)
        f_v, f_y, f_t = c4.selectbox("4. 版本", ["全部"] + sorted(df_q['版本'].unique().tolist()), key="f_v"), c5.selectbox("5. 年度", ["全部"] + sorted(df_q['年度'].unique().tolist()), key="f_y"), c6.selectbox("6. 任務", ["全部"] + (df_a['說明文字'].unique().tolist() if df_a is not None else []), key="f_t")
        dv = df_l.fillna("").copy()
        if f_g != "全部": dv = dv[dv['分組'] == f_g]
        if f_n != "全部": dv = dv[dv['姓名'] == f_n]
        if f_act != "全部": dv = dv[dv['動作'].str.contains(f_act, na=False)]
        if f_v != "全部": dv = dv[dv['題目ID'].str.startswith(f_v)]
        if f_y != "全部": dv = dv[dv['題目ID'].str.contains(f"_{f_y}_", na=False)]
        if f_t != "全部" and df_a is not None:
            qids = str(df_a[df_a['說明文字']==f_t].iloc[0]['題目ID清單']).split(',')
            dv = dv[dv['題目ID'].isin([q.strip() for q in qids])]
        st.dataframe(dv.sort_index(ascending=False).head(100), use_container_width=True)
    with t_tabs[1]: # 任務指派 (加強篩選邏輯)
        ic1, ic2 = st.columns(2)
        ag, an = ic1.selectbox("組別", ["全體"]+sorted([g for g in df_s['分組'].unique() if g!="ADMIN"]), key="ag_adm"), ic2.multiselect("學生", sorted(df_s[df_s['分組']==ic1.session_state.get('ag_adm','全體')]['姓名'].tolist()) if ic1.session_state.get('ag_adm')!="全體" else [], key="an_adm")
        cs = st.columns(6)
        av, au, ay, ab, al = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_a"), cs[1].selectbox("項目", sorted(df_q['單元'].unique()), key="au_a"), cs[2].selectbox("年度", sorted(df_q['年度'].unique()), key="ay_a"), cs[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="ab_a"), cs[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="al_a")
        me = cs[5].number_input("最低錯誤數", 0, 10, 1, key="err_a")
        sq = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
        fids = [f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}" for _, r in sq.iterrows() if len(df_l[(df_l['題目ID']==f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}") & (df_l['結果']=='❌')]) >= me]
        st.info(f"🔍 篩選出 {len(fids)} 題")
        if st.button("📢 發佈任務", type="primary", key="btn_a") and fids:
            nr = pd.DataFrame([{"對象 (分組/姓名)": (", ".join(an) if an else ag), "任務類型": "指派", "題目ID清單": ", ".join(fids), "說明文字": f"{au}補強", "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, nr], ignore_index=True)); st.success("成功！"); st.cache_data.clear(); st.rerun()
    with t_tabs[2]:
        for i, r in df_a.iterrows():
            ci, cd = st.columns([4, 1])
            ci.warning(f"📍 {r['對象 (分組/姓名)']} | {r['說明文字']}")
            if cd.button("🗑️ 刪除", key=f"del_{i}"): conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
    st.stop()

# --- [模組 6] 學生練習區 (檢核點 6, 7, 10, 11) ---
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
            if t_quiz: st.session_state.update({"quiz_list": t_quiz, "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "log_buffer": []}); st.rerun()

with st.expander("⚙️ 手動設定範圍", expanded=not st.session_state.get('quiz_loaded', False)):
    c = st.columns(5)
    sv, su, sy, sb, sl = c[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v"), c[1].selectbox("項目", sorted(df_q['單元'].unique()), key="s_u"), c[2].selectbox("年度", sorted(df_q['年度'].unique()), key="s_y"), c[3].selectbox("冊別", sorted(df_q['冊編號'].unique()), key="s_b"), c[4].selectbox("課次", sorted(df_q['課編號'].unique()), key="s_l")
    base = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)&(df_q['課編號']==sl)].copy()
    if not base.empty:
        base['句編號_int'] = pd.to_numeric(base['句編號'], errors='coerce')
        base = base.sort_values('句編號_int')
        nums = base['句編號_int'].dropna().unique().tolist()
        st.info(f"📊 該單元共 **{len(base)}** 題 | 範圍：{int(min(nums))}~{int(max(nums))}")
        sc1, sc2 = st.columns(2)
        st_i = sc1.number_input("起始編號", int(min(nums)), int(max(nums)), int(min(nums)), key="s_i")
        nu_i = sc2.number_input("題數", 1, 50, 10, key="s_n")
        actual = len(base[base['句編號_int']>=st_i].head(int(nu_i)))
        if st.button(f"🚀 載入測驗 (共 {actual} 題)"):
            st.session_state.update({"quiz_list": base[base['句編號_int']>=st_i].head(int(nu_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "log_buffer": []}); st.rerun()

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
            if cols[i].button(
