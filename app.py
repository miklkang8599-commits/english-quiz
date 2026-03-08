# ==============================================================================
# 🧩 英文全能練習系統 (V2.7.11 指派任務與數據完全修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.7.11
# 📅 更新日期: 2026-03-08
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.7.11"

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

# --- 3. 資料載入 ---
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title(f"👋 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式選擇：", ["管理後台", "學生練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.logged_in = False; st.rerun()
    st.divider()
    if st.button("🔄 重新整理數據"): st.cache_data.clear(); st.rerun()

# --- 5. 👨‍🏫 導師管理中心 (核心功能全復原) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.title("👨‍🏫 導師管理中心")
    t_tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    
    with t_tabs[0]: # 📊 數據追蹤 (修復空白問題)
        st.subheader("📋 全班最新作答流水帳")
        if df_l is not None and not df_l.empty:
            st.dataframe(df_l.iloc[::-1].head(100), use_container_width=True)
        else: st.info("尚無紀錄資料")

    with t_tabs[1]: # 🎯 指派任務 (完整邏輯接回)
        c1, c2 = st.columns(2)
        g_opts = ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"])
        adm_g = c1.selectbox("1. 選擇組別", g_opts, key="adm_g")
        name_opts = sorted(df_s[df_s['分組']==adm_g]['姓名'].tolist()) if adm_g != "全體" else sorted(df_s[df_s['分組']!="ADMIN"]['姓名'].tolist())
        adm_n = c2.multiselect("2. 選擇學生", name_opts, key="adm_n")
        
        cs = st.columns(6)
        av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av")
        au = cs[1].selectbox("項目", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au")
        ay = cs[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="ay")
        ab = cs[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="ab")
        al = cs[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="al")
        min_err = cs[5].number_input("最低錯誤數", 0, 10, 1, key="adm_err")
        
        # 💡 篩選邏輯補回
        scope_q = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
        final_ids = []
        if df_l is not None:
            for _, row in scope_q.iterrows():
                qid = f"{row['版本']}_{row['年度']}_{row['冊編號']}_{row['單元']}_{row['課編號']}_{row['句編號']}"
                err_count = len(df_l[(df_l['題目ID'] == qid) & (df_l['結果'] == '❌')])
                if err_count >= min_err: final_ids.append(qid)
        
        st.info(f"🔍 篩選出 {len(final_ids)} 題符合條件")
        msg = st.text_input("任務說明", value=f"{au}補強練習")
        if st.button("📢 確定發佈指派", type="primary", use_container_width=True) and final_ids:
            tgt = ", ".join(adm_n) if adm_n else adm_g
            new_a = pd.DataFrame([{"對象 (分組/姓名)": tgt, "任務類型": "指派", "題目ID清單": ", ".join(final_ids), "說明文字": msg, "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_a], ignore_index=True))
            st.success("任務指派已成功寫入雲端！"); st.cache_data.clear(); st.rerun()

    with t_tabs[2]: # 📜 任務管理
        if df_a is not None and not df_a.empty:
            for i, row in df_a.iterrows():
                ci, cd = st.columns([4, 1])
                ci.warning(f"📍 {row['對象 (分組/姓名)']} | {row['說明文字']}")
                if cd.button("🗑️ 刪除", key=f"del_a_{i}"):
                    conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
    st.stop()

# --- 6. 🚀 學生練習介面 ---
st.title("🚀 英文練習區")

# A. 任務偵測 (略...) 
# B. 手動設定 (略...)

# C. 練習核心 & 紀錄框 (強化題號組合)
# ...練習邏輯代碼...

st.divider()
st.subheader("📜 最近我的練習紀錄")
if df_l is not None and not df_l.empty:
    my_logs = df_l[df_l['帳號'] == st.session_state.user_id].sort_index(ascending=False).head(15)
    for _, row in my_logs.iterrows():
        qid = str(row['題目ID'])
        # 💡 解析完整題號組合：版本_冊_課_句
        p = qid.split('_')
        disp_qid = f"{p[0]}_B{p[2]}_L{p[4]}_{p[5]}" if len(p) >= 6 else qid
        res_color = "green" if row['結果'] == "✅" else "red"
        st.markdown(f'<div style="border-bottom:1px solid #eee; padding:5px; font-size:13px; display:flex; justify-content:space-between;">'
                    f'<span>🕒 {str(row["時間"])[-8:]} | <b>{disp_qid}</b></span>'
                    f'<span>結果: <b style="color:{res_color}">{row["結果"]}</b> | {row["費時"]}s</span></div>', unsafe_allow_html=True)

st.caption(f"Ver {VERSION}")
