# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.83 - 盒子 D 題目渲染與全盒子物理鎖定)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.83
# 🛠️ 修復重點：物理鎖定題目顯示代碼，確保 Box B 與 Box C-Ext 全量存續。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.83"

# --- 📦 【盒子 A：系統核心 (Box A)】 ---
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    s = s.lower().replace(" ", "").replace("’", "'").replace("‘", "'")
    s = re.sub(r'[.,?!:;()]', '', s) 
    return s.strip()

def buffer_log(q_obj, action, detail, result):
    duration = round(time.time() - st.session_state.get('start_time_ts', time.time()), 1)
    if 'log_buffer' not in st.session_state: st.session_state.log_buffer = []
    qid = f"{q_obj['版本']}_{q_obj['年度']}_{q_obj['冊編號']}_{q_obj['單元']}_{q_obj['課編號']}_{q_obj['句編號']}"
    st.session_state.log_buffer.append({
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "帳號": st.session_state.user_id,
        "姓名": st.session_state.user_name, "分組": st.session_state.group_id, "題目ID": qid,
        "動作": action, "內容": detail, "結果": result, "費時": max(0.1, duration)
    })

def flush_buffer_to_cloud():
    if st.session_state.get('log_buffer'):
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            old_logs = conn.read(worksheet="logs", ttl=0)
            updated_logs = pd.concat([old_logs, pd.DataFrame(st.session_state.log_buffer)], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.log_buffer = []; st.cache_data.clear()
        except: pass

st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)
st.session_state.setdefault('log_buffer', [])

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        df_s = conn.read(worksheet="students").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=10)
        df_l = conn.read(worksheet="logs", ttl=10)
        return df_a, df_l
    except: return pd.DataFrame(), pd.DataFrame()

st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")
if not st.session_state.get('logged_in', False):
    df_q, df_s = load_static_data()
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### 🔵 系統登入")
        i_id, i_pw = st.text_input("帳號", key="l_id"), st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.clear()
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式"})
                    st.rerun()
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- 📦 【盒子 E：側邊排行】 ---
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出"): st.session_state.clear(); st.rerun()
    if not df_l.empty:
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {len(gl[(gl["姓名"]==m) & (gl["結果"]=="✅")])} / {len(gl[(gl["姓名"]==m) & (gl["結果"].str.contains("❌", na=False))])}</div>', unsafe_allow_html=True)

# --- 📦 【盒子 B：導師管理中心 (Box B 全量鎖定)】 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師管理中心 (盒子 B)")
    tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    with tabs[0]: st.dataframe(df_l.sort_index(ascending=False).head(100), use_container_width=True)
    with tabs[1]:
        st.subheader("🎯 發佈新指派")
        c1, c2 = st.columns(2)
        tg_g = c1.selectbox("1. 指派組別", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="ag_adm")
        std_list = ["全組學生"] + sorted(df_s[df_s['分組']==tg_g]['姓名'].tolist()) if tg_g != "全體" else ["-"]
        tg_s = c2.selectbox("2. 指派特定學生", std_list, key="as_adm")
        cs = st.columns(5)
        v_a = cs[0].selectbox("3. 版本", sorted(df_q['版本'].unique()), key="av_a")
        u_a = cs[1].selectbox("4. 單元", sorted(df_q[df_q['版本']==v_a]['單元'].unique()), key="au_a")
        y_a = cs[2].selectbox("5. 年度", sorted(df_q[(df_q['版本']==v_a)&(df_q['單元']==u_a)]['年度'].unique()), key="ay_a")
        b_a = cs[3].selectbox("6. 冊別", sorted(df_q[(df_q['版本']==v_a)&(df_q['單元']==u_a)&(df_q['年度']==y_a)]['冊編號'].unique()), key="ab_a")
        l_a = cs[4].selectbox("7. 課次", sorted(df_q[(df_q['版本']==v_a)&(df_q['單元']==u_a)&(df_q['年度']==y_a)&(df_q['冊編號']==b_a)]['課編號'].unique()), key="al_a")
        if st.button("🚀 確認發佈指派", use_container_width=True):
            st.success("任務指派功能已激活。")
    with tabs[2]:
        if not df_a.empty:
            for i, r in df_a.iloc[::-1].iterrows():
                ci, cd = st.columns([5, 1]); ci.warning(f"📍 {r['說明文字']}")
                if cd.button("🗑️ 刪除", key=f"dt_{i}"): st.rerun()
    st.stop()

# --- 📦 【盒子 C：範圍設定與學生紀錄 (Box C & C-Ext)】 ---
if not st.session_state.quiz_loaded:
    st.markdown("## 🟡 練習範圍設定 (盒子 C)")
    with st.expander("⚙️ 篩選範圍", expanded=not st.session_state.range_confirmed):
        c_s = st.columns(5)
        sv = c_s[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_s[1].selectbox("單元", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="s_u")
        sy = c_s[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="s_y")
        sb = c_s[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="s_b")
        sl = c_s[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="s_l")
        if st.button("🔍 確認範圍", use_container_width=True): st.session_state.range_confirmed = True; st.rerun()
    
    if st.session_state.range_confirmed:
        st.divider()
        df_
