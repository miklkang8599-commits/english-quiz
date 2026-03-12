# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.85 - 盒子 E 類型衝突修復與數據防禦版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.85
# 📅 更新日期: 2026-03-12
# 🛠️ 修復重點：修復第 102 行之 TypeError，強化全系統資料類型一致性。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.85"

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
        # 💡 [防禦] 讀取時強制轉為字串並去除空白
        df_q = conn.read(worksheet="questions").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        df_s = conn.read(worksheet="students").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except: return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=10).fillna("").astype(str)
        df_l = conn.read(worksheet="logs", ttl=10).fillna("").astype(str)
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
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": str(user.iloc[0]['分組']), "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式"})
                    st.rerun()
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- 📦 【盒子 E：側邊排行 (修復 TypeError)】 ---
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出"): st.session_state.clear(); st.rerun()
    
    if not df_l.empty:
        st.divider(); st.subheader("🏆 今日排行")
        # 💡 [關鍵修復點]：強制將比較對象轉為字串
        curr_group = str(st.session_state.group_id)
        gl = df_l[df_l['分組'].astype(str) == curr_group].copy()
        # 💡 [修復第 102 行]：確保過濾邏輯類型一致
        member_list = sorted(df_s[df_s['分組'].astype(str) == curr_group]['姓名'].tolist())
        
        for m in member_list:
            c_cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            w_cnt = len(gl[(gl['姓名']==m) & (gl['結果'].str.contains("❌", na=False))])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {c_cnt} / {w_cnt}</div>', unsafe_allow_html=True)

# --- 📦 【盒子 B：導師管理中心 (Box B)】 ---
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
        if st.button("🚀 確認發佈指派", type="primary"):
            sq = df_q[(df_q['版本']==v_a)&(df_q['單元']==u_a)&(df_q['年度']==y_a)&(df_q['冊編號']==b_a)&(df_q['課編號']==l_a)]
            fids = [f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}" for _, r in sq.iterrows()]
            new_t = pd.DataFrame([{"對象 (分組/姓名)": tg_s if tg_s != "全組學生" else tg_g, "任務類型": "指派", "題目ID清單": ", ".join(fids), "說明文字": f"{u_a} 指派", "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_t], ignore_index=True)); st.success("發佈成功！"); st.rerun()
    with tabs[2]:
        if not df_a.empty:
            for i, r in df_a.iloc[::-1].iterrows():
                ci, cd = st.columns([5, 1]); ci.warning(f"📍 {r['說明文字']} ({r['對象 (分組/姓名)']})")
                if cd.button("🗑️ 刪除", key=f"dt_{i}"):
                    conn.update(worksheet="assignments", data=df_a.drop(i)); st.rerun()
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
        else:
            wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique()
            df_final = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()
        st.success(f"📊 符合條件題數：{len(df_final)} 題")
        nu_i = st.number_input("🔢 練習題數", 1, 50, 10, key="s_n")
        if st.button("🚀 開始練習", type="primary", use_container_width=True):
            if not df_final.empty:
                st.session_state.update({"quiz_list": df_final.head(int(nu_i)).to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time()})
                st.rerun()

    st.divider(); st.subheader("📜 您的答題紀錄列表 (捲軸式)")
    if not df_l.empty:
        my_l = df_l[df_l['姓名'] == st.session_state.user_name].sort_index(ascending=False).head(50)
        st.dataframe(my_l[["時間", "題目ID", "結果", "費時"]], use_container_width=True, height=250, hide_index=True)

# --- 📦 【盒子 D：練習引擎 (Box D)】 ---
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq = "單選" in q.get("單元", "")
    st.markdown(f"#### 題目：{q.get('單選題目' if is_mcq else '重組中文題目') or '【資料讀取中】'}")
    ans_key = str(q.get('單選答案' if is_mcq else '重組英文答案') or q.get('英文答案') or "").strip()
    
    if is_mcq:
        cols = st.columns(4)
        for opt in ["A", "B", "C", "D"]:
            if cols["ABCD".find(opt)].button(opt, key=f"mcq_{opt}", use_container_width=True):
                is_ok = (opt.upper() == ans_key.upper())
                buffer_log(q, "單選", opt, "✅" if is_ok else f"❌({ans_key})")
                st.session_state.update({"current_res": "✅" if is_ok else f"❌({ans_key})", "show_analysis": True}); st.rerun()
    else:
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else " ")
        c_top = st.columns(2)
        if c_top[0].button("⬅️ 🟠 退回一步", use_container_width=True):
            if st.session_state.ans: st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
        if c_top[1].button("🗑️ 🟠 全部清除", use_container_width=True):
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
        flush_buffer_to_cloud(); st.session_state.update({"quiz_loaded": False, "range_confirmed": False}); st.rerun()

st.caption(f"Ver {VERSION} | TypeError 修復與數據類型鎖定版")
