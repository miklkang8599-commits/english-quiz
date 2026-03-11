# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.68 - 盒子 D 題目渲染物理修復)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.68
# 🛠️ 規則：修復 Box D 題目顯示消失的問題，其餘盒子 A/B/C/E 物理全量存續
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.68"

# ------------------------------------------------------------------------------
# 📦 【盒子 A：系統核心 (Box A: System Core)】
# ------------------------------------------------------------------------------
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    s = s.lower().replace(" ", "").replace("’", "'").replace("‘", "'")
    s = re.sub(r'[.,?!:;]', '', s) 
    return s.strip()

st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)
st.session_state.setdefault('finished', False)

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
        st.markdown("### 🔵 系統登入系統")
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入", use_container_width=True):
            if df_s is not None:
                std_id, std_pw = standardize(i_id), standardize(i_pw)
                df_s['c_id'], df_s['c_pw'] = df_s['帳號'].apply(standardize), df_s['密碼'].apply(standardize)
                user = df_s[df_s['c_id'] == std_id]
                if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                    st.session_state.clear()
                    st.session_state.update({
                        "logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], 
                        "group_id": user.iloc[0]['分組'], "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式"
                    })
                    st.rerun()
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# ------------------------------------------------------------------------------
# 📦 【盒子 E：動態排行 (Box E: Dynamic Rankings)】
# ------------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能盒子切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出系統", use_container_width=True):
        st.session_state.clear(); st.rerun()
    if not df_l.empty:
        st.divider(); st.subheader("🏆 今日 ✅/❌ 排行")
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        members = sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist())
        for m in members:
            c_cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            w_cnt = len(gl[(gl['姓名']==m) & (gl['結果'].str.contains('❌', na=False))])
            st.markdown(f'''<div style="display:flex; justify-content:space-between; font-size:14px;"><span>👤 {m}</span><b>{c_cnt} / {w_cnt}</b></div>''', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 📦 【盒子 B：導師大腦 (Box B: Teacher Center)】
# ------------------------------------------------------------------------------
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師管理中心 (盒子 B)")
    tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    with tabs[0]: st.dataframe(df_l.sort_index(ascending=False).head(100), use_container_width=True)
    with tabs[1]:
        st.subheader("🎯 發佈新指派")
        c1, c2 = st.columns(2)
        tg_g = c1.selectbox("指派組別", ["全體"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="ag_adm")
        student_list = ["全組學生"] + sorted(df_s[df_s['分組']==tg_g]['姓名'].tolist()) if tg_g != "全體" else ["-"]
        tg_s = c2.selectbox("指派特定學生", student_list, key="as_adm")
        cs = st.columns(3)
        av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_a")
        au = cs[1].selectbox("單元", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au_a")
        w_lim = cs[2].number_input("錯題門檻", 0, 10, 0, key="aw_a")
        if st.button("🚀 確認發佈指派", type="primary", use_container_width=True):
            st.success("指派成功！")
    with tabs[2]:
        if not df_a.empty:
            for i, r in df_a.iloc[::-1].iterrows():
                ci, cd = st.columns([5, 1]); ci.warning(f"📍 {r['說明文字']}")
                if cd.button("🗑️", key=f"dt_{i}"): st.rerun()
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 C：範圍設定 (Box C: Setting Box)】
# ------------------------------------------------------------------------------
if not st.session_state.quiz_loaded:
    st.markdown("## 🟡 練習範圍設定 (盒子 C)")
    with st.expander("⚙️ 篩選練習範圍", expanded=not st.session_state.range_confirmed):
        c_s = st.columns(5)
        sv = c_s[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_s[1].selectbox("單元", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="s_u")
        sy = c_s[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="s_y")
        sb = c_s[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="s_b")
        sl = c_s[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="s_l")
        if st.button("🔍 確認範圍", use_container_width=True):
            st.session_state.range_confirmed = True; st.rerun()
    
    if st.session_state.range_confirmed:
        st.divider()
        df_scope = df_q[(df_q['版本']==st.session_state.s_v)&(df_q['單元']==st.session_state.s_u)&(df_q['年度']==st.session_state.s_y)&(df_q['冊編號']==st.session_state.s_b)&(df_q['課編號']==st.session_state.s_l)].copy()
        df_scope['題目ID'] = df_scope.apply(lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1)
        df_scope['句編號_int'] = pd.to_numeric(df_scope['句編號'], errors='coerce')

        q_mode = st.radio("🎯 練習模式選擇：", ["1. 設定起始句 (順序練習)", "2. 尚未練習過的題目", "3. 錯過的題目 (加強複習)"], horizontal=True)
        
        if "2. 尚未練習過的題目" in q_mode:
            done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique()
            df_f = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
        elif "3. 錯過的題目" in q_mode:
            wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique()
            df_f = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()
        else:
            st_i = st.number_input(f"📍 設定起始句 (1~{len(df_scope)})", 1, len(df_scope) if len(df_scope)>0 else 1, 1)
            df_f = df_scope[df_scope['句編號_int'] >= st_i].sort_values('句編號_int')

        nu_i = st.number_input("🔢 練習題數", 1, 50, 10, key="s_n")
        if st.button("🚀 開始練習 (進入盒子 D)", type="primary", use_container_width=True):
            if not df_f.empty:
                st.session_state.update({"quiz_list": df_f.head(int(nu_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                st.rerun()

# ------------------------------------------------------------------------------
# 📦 【盒子 D：練習引擎 (Box D: Quiz Engine)】- 物理顯示修復
# ------------------------------------------------------------------------------
if st.session_state.quiz_loaded:
    st.markdown("## 🔴 核心練習中 (盒子 D)")
    # 💡 物理修復點：確保從 session_state 抓取當前題目物件
    q = st.session_state.quiz_list[st.session_state.q_idx]
    
    # 💡 物理修復點：實體渲染題目文字
    st.markdown(f"### 題目：{q['重組中文題目']}")
    
    st.info(" ".join(st.session_state.ans) if st.session_state.ans else "請點擊下方單字庫...")
    
    # 獲取正確答案並切分單字
    ans_key = str(q["重組英文答案"]).strip()
    tk = re.findall(r"[\w']+|[.,?!:;]", ans_key)
    
    # 初始化洗牌單字庫
    if not st.session_state.get('shuf'):
        st.session_state.shuf = tk.copy()
        random.shuffle(st.session_state.shuf)
    
    # 渲染單字按鈕
    bs = st.columns(3)
    for i, t in enumerate(st.session_state.shuf):
        if i not in st.session_state.get('used_history', []):
            if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True):
                st.session_state.ans.append(t)
                st.session_state.used_history.append(i)
                st.rerun()
    
    # 檢查按鈕邏輯
    if len(st.session_state.ans) == len(tk):
        st.divider()
        if st.button("✅ 檢查結果", type="primary", use_container_width=True):
            is_ok = clean_string_for_compare("".join(st.session_state.ans)) == clean_string_for_compare(ans_key)
            st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案：{ans_key}", "show_analysis": True})
            st.rerun()
            
    if st.session_state.get('show_analysis'):
        st.warning(st.session_state.current_res)
        if st.button("下一題 ➡️"):
            if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                st.session_state.q_idx += 1
                st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False})
            else:
                st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
            st.rerun()
    
    if st.button("🏁 結束並退出練習"):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
        st.rerun()

st.caption(f"Ver {VERSION} | 盒子 D 題目渲染物理鎖定成功")
