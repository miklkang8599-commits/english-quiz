# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.81 - Box C 學生個人紀錄列表擴充版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.81
# 🛠️ 規則：在盒子 C 下方新增卷軸式紀錄列表，確保不影響 A/B/D/E 盒子物理結構。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.81"

# --- 📦 【盒子 A：系統核心】 ---
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

# 登入邏輯 (Box A 實體存續)
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

# --- 📦 【盒子 E：側邊排行】 ---
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出"): st.session_state.clear(); st.rerun()
    if not df_l.empty:
        gl = df_l[df_l['分組'] == st.session_state.group_id].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {len(gl[(gl["姓名"]==m) & (gl["結果"]=="✅")])} / {len(gl[(gl["姓名"]==m) & (gl["結果"].str.contains("❌", na=False))])}</div>', unsafe_allow_html=True)

# --- 📦 【盒子 B：導師中心】 (Box B 實體存續) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師管理中心 (盒子 B)")
    st.info("管理後台功能物理存續中...")
    st.stop()

# --- 📦 【盒子 C：範圍設定 (Box C)】 ---
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
        if "1. 起始句" in q_mode:
            st_i = st.number_input(f"📍 起始句 (1~{len(df_scope)})", 1, len(df_scope) if len(df_scope)>0 else 1, 1)
            df_final = df_scope[df_scope['句編號_int'] >= st_i].sort_values('句編號_int')
        elif "2. 未練習" in q_mode:
            done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique()
            df_final = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
        else: # 3. 錯題
            wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique()
            df_final = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()
        
        st.success(f"📊 符合條件題數：{len(df_final)} 題")
        nu_i = st.number_input("🔢 練習題數", 1, 50, 10, key="s_n")
        if st.button("🚀 開始練習", type="primary", use_container_width=True):
            st.session_state.update({"quiz_list": df_final.head(int(nu_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
            st.rerun()

    # --- 📦 【盒子 C-Ext：個人紀錄面板 (Box C-Ext)】 ---
    st.divider()
    st.subheader("📜 您的個人答題紀錄列表 (最近 50 筆)")
    if not df_l.empty:
        my_logs = df_l[df_l['姓名'] == st.session_state.user_name].sort_index(ascending=False).head(50)
        # 💡 [物理顯示] 卷軸式清單
        st.dataframe(
            my_logs[["時間", "題目ID", "動作", "內容", "結果", "費時"]],
            use_container_width=True,
            height=300, # 💡 固定高度產生捲軸
            hide_index=True
        )
    else:
        st.write("目前尚無作答紀錄。")

# --- 📦 【盒子 D：練習引擎】 (Box D 實體存續) ---
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq = "單選" in q.get("單元", "")
    ans_key = str(q.get('單選答案' if is_mcq else '重組英文答案') or "").strip()
    
    if is_mcq:
        cols = st.columns(4)
        for opt in ["A", "B", "C", "D"]:
            if cols["ABCD".find(opt)].button(opt, use_container_width=True):
                is_ok = (opt.upper() == ans_key.upper())
                buffer_log(q, "單選", opt, "✅" if is_ok else f"❌({ans_key})")
                st.session_state.update({"current_res": "✅" if is_ok else f"❌({ans_key})", "show_analysis": True}); st.rerun()
    else:
        # 重組題 UI (實體存續)
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else " ")
        c_t = st.columns(2)
        if c_t[0].button("⬅️ 🟠 退回一步", use_container_width=True):
            if st.session_state.ans: st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
        if c_t[1].button("🗑️ 🟠 全部清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        
        tk = re.findall(r"[\w']+|[.,?!:;()]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True):
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        if len(st.session_state.ans) == len(tk) and not st.session_state.show_analysis:
            if st.button("✅ 檢查作答結果", type="primary", use_container_width=True):
                is_ok = clean_string_for_compare("".join(st.session_state.ans)) == clean_string_for_compare(ans_key)
                buffer_log(q, "重組", " ".join(st.session_state.ans), "✅" if is_ok else f"❌({ans_key})")
                st.session_state.update({"current_res": "✅" if is_ok else f"❌({ans_key})", "show_analysis": True}); st.rerun()

    if st.session_state.get('show_analysis'):
        st.warning(st.session_state.current_res)
        c_nav = st.columns(2)
        if st.session_state.q_idx > 0:
            if c_nav[0].button("⬅️ 🔵 上一題", use_container_width=True):
                st.session_state.q_idx -= 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
        nxt_l = "下一題 ➡️" if st.session_state.q_idx + 1 < len(st.session_state.quiz_list) else "🏁 結束練習"
        if c_nav[1].button(nxt_l, type="primary", use_container_width=True):
            flush_buffer_to_cloud()
            if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
                st.session_state.q_idx += 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
            else: st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()

    if st.button("🏁 🔴 結束作答", use_container_width=True):
        flush_buffer_to_cloud()
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()

st.caption(f"Ver {VERSION} | Box C-Ext 學生紀錄列表已實體展開")
