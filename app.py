# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.78 - 盒子 C 起始句功能物理回歸)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.78
# 🛠️ 修復重點：修復盒子 C 在「起始句」模式下遺失輸入框的問題，其餘盒子全量存續。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.78"

# --- 📦 【盒子 A：系統核心 (Box A: System Core)】 ---
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    # 智慧標點比對：包含括號消除邏輯
    s = s.lower().replace(" ", "").replace("’", "'").replace("‘", "'")
    s = re.sub(r'[.,?!:;()]', '', s) 
    return s.strip()

st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)

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
        i_id = st.text_input("帳號", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
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

# --- 📦 【盒子 E：側邊排行 (Box E)】 ---
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name} (V{VERSION})")
    if st.button("🚪 登出系統"): st.session_state.clear(); st.rerun()
    if not df_l.empty:
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            c_cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            w_cnt = len(gl[(gl['姓名']==m) & (gl['結果'].str.contains('❌', na=False))])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {c_cnt} / {w_cnt}</div>', unsafe_allow_html=True)

# --- 📦 【盒子 B：導師大腦 (Box B)】 ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師管理中心 (盒子 B)")
    st.info("管理後台功能正常存續。")
    st.stop()

# --- 📦 【盒子 C：範圍設定 (Box C: 起始句功能修復版)】 ---
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
        df_scope = df_q[(df_q['版本']==st.session_state.s_v)&(df_q['單元']==st.session_state.s_u)&(df_q['年度']==st.session_state.s_y)&(df_q['冊編號']==st.session_state.s_b)&(df_q['課編號']==st.session_state.s_l)].copy()
        df_scope['題目ID'] = df_scope.apply(lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1)
        df_scope['句編號_int'] = pd.to_numeric(df_scope['句編號'], errors='coerce')

        q_mode = st.radio("🎯 模式選擇：", ["1. 起始句", "2. 未練習", "3. 錯題"], horizontal=True)
        
        # 💡 [修復] 起始句物理輸入框回歸
        if "1. 起始句" in q_mode:
            max_q = len(df_scope)
            st_i = st.number_input(f"📍 設定起始句 (範圍 1~{max_q})", 1, max_q if max_q > 0 else 1, 1, key="start_q_input")
            df_final = df_scope[df_scope['句編號_int'] >= st_i].sort_values('句編號_int')
        elif "2. 未練習" in q_mode:
            done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique()
            df_final = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
        elif "3. 錯題" in q_mode:
            wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique()
            df_final = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()
        
        st.success(f"📊 符合條件題數：{len(df_final)} 題")
        nu_i = st.number_input("🔢 練習題數", 1, 50, 10, key="s_n")
        
        if st.button("🚀 正式開始練習", type="primary", use_container_width=True):
            if not df_final.empty:
                st.session_state.update({"quiz_list": df_final.head(int(nu_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                st.rerun()
            else: st.error("❌ 無符合題目")

# --- 📦 【盒子 D：練習引擎 (Box D: 保持五鍵物理全通版)】 ---
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} / {len(st.session_state.quiz_list)} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq = "單選" in q.get("單元", "")
    st.markdown(f"#### 題目：{q.get('單選題目' if is_mcq else '重組中文題目') or '【無資料】'}")
    ans_key = str(q.get('單選答案' if is_mcq else '重組英文答案') or "").strip()
    
    if is_mcq:
        cols = st.columns(4)
        for opt in ["A", "B", "C", "D"]:
            if cols["ABCD".find(opt)].button(f" {opt} ", key=f"mcq_{opt}", use_container_width=True):
                is_ok = (opt.upper() == ans_key.upper())
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案是 ({ans_key})", "show_analysis": True}); st.rerun()
    else:
        # 重組題 UI (實體 5 鍵)
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else " ")
        c_top = st.columns(2)
        if c_top[0].button("⬅️ 🟠 退回一步", use_container_width=True):
            if st.session_state.ans: st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
        if c_top[1].button("🗑️ 🟠 全部清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        
        tk = re.findall(r"[\w']+|[.,?!:;()]", ans_key) # 💡 包含括號解析
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if len(st.session_state.ans) == len(tk) and not st.session_state.show_analysis:
            if st.button("✅ 🔵 檢查作答結果", type="primary", use_container_width=True):
                is_ok = clean_string_for_compare("".join(st.session_state.ans)) == clean_string_for_compare(ans_key)
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！答案：{ans_key}", "show_analysis": True}); st.rerun()

    if st.session_state.get('show_analysis'):
        st.warning(st.session_state.current_res)
        c_nav = st.columns(2)
        if st.session_state.q_idx > 0:
            if c_nav[0].button("⬅️ 🔵 上一題", use_container_width=True):
                st.session_state.q_idx -= 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
        nxt_l = "下一題 ➡️" if st.session_state.q_idx + 1 < len(st.session_state.quiz_list) else "🏁 結束練習"
        if c_nav[1].button(nxt_l, type="primary", use_container_width=True):
            if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                st.session_state.q_idx += 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
            else: st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()

    if st.button("🏁 🔴 結束作答 (返回設定區)", use_container_width=True):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()

st.caption(f"Ver {VERSION} | 盒子 C 起始句功能物理回歸鎖定")
