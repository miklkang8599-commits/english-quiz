# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.46 導師管理中心全功能恢復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.46
# 📅 更新日期: 2026-03-09
# ------------------------------------------------------------------------------
# 🛠️ 核心功能檢核清單:
# [03-05] 🟢 導師管理中心分頁物理恢復 [07] 🟡 數值調整鈕 [20] 🟠 範圍重設
# [30] 🟡 效能優化連動 [31] 🔴 重組作答檢查鍵 -> LOCKED
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.46"

# --- ### 🔵 MODULE 1: 基礎定義 ---
def standardize(v):
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

# --- ### ⚪ MODULE 2: 數據中心 ---
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

def flush_buffer_to_cloud():
    if st.session_state.get('log_buffer'):
        try:
            old_logs = conn.read(worksheet="logs", ttl=0)
            new_rows = pd.DataFrame(st.session_state.log_buffer)
            updated_logs = pd.concat([old_logs, new_rows], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.session_state.log_buffer = []; st.cache_data.clear()
        except: pass

def buffer_log(action, detail, result):
    duration = round(time.time() - st.session_state.get('start_time_ts', time.time()), 1)
    st.session_state.log_buffer.append({
        "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "帳號": st.session_state.user_id, "姓名": st.session_state.user_name,
        "分組": st.session_state.group_id, "題目ID": st.session_state.get('current_qid','-'),
        "動作": action, "內容": detail, "結果": result, "費時": max(0.1, duration)
    })

# --- ### 🔵 MODULE 3: 登入模組 ---
st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
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
                    st.session_state.update({"logged_in": True, "user_id": f"EA{std_id}", "user_name": user.iloc[0]['姓名'], "group_id": user.iloc[0]['分組'], "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式", "quiz_loaded": False, "log_buffer": [], "start_time_ts": time.time()})
                    st.rerun()
    st.stop()

df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# --- ### 🟣 MODULE 4: 側邊欄 ---
with st.sidebar:
    st.markdown("### 🟣 使用者狀態")
    st.write(f"👤 {st.session_state.user_name}")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("模式切換：", ["管理後台", "練習模式"])
    if st.button("🚪 登出", use_container_width=True):
        flush_buffer_to_cloud(); st.session_state.clear(); st.rerun()

# --- ### 🟢 MODULE 5: 導師管理中心 (核心恢復 [03, 04, 05]) ---
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown(f"## 🟢 導師管理中心 (V{VERSION})")
    tabs = st.tabs(["📊 數據追蹤", "🎯 指派任務", "📜 任務管理"])
    
    with tabs[0]: # [03] 數據追蹤
        c1, c2, c3 = st.columns(3)
        fg = c1.selectbox("篩選組別", ["全部"] + sorted([g for g in df_s['分組'].unique() if g != "ADMIN"]), key="f_g")
        fn = c2.selectbox("篩選姓名", ["全部"] + sorted(df_s[df_s['分組']==fg]['姓名'].tolist() if fg!="全部" else df_s[df_s['分組']!="ADMIN"]['姓名'].tolist()), key="f_n")
        fa = c3.selectbox("篩選動作", ["全部", "單選", "重組"], key="f_act")
        dv = df_l.copy()
        if not dv.empty:
            if fg != "全部": dv = dv[dv['分組'] == fg]
            if fn != "全部": dv = dv[dv['姓名'] == fn]
            st.dataframe(dv.sort_index(ascending=False).head(100), use_container_width=True)

    with tabs[1]: # [04] 指派任務
        st.subheader("🎯 發佈任務範圍")
        cs = st.columns(5)
        av = cs[0].selectbox("版本", sorted(df_q['版本'].unique()), key="av_a")
        au = cs[1].selectbox("單元", sorted(df_q[df_q['版本']==av]['單元'].unique()), key="au_a")
        ay = cs[2].selectbox("年度", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)]['年度'].unique()), key="ay_a")
        ab = cs[3].selectbox("冊別", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)]['冊編號'].unique()), key="ab_a")
        al = cs[4].selectbox("課次", sorted(df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)]['課編號'].unique()), key="al_a")
        
        target_g = st.selectbox("指派組別", ["全體"]+sorted([g for g in df_s['分組'].unique() if g!="ADMIN"]), key="ag_adm")
        if st.button("📢 正式指派任務", type="primary", use_container_width=True):
            sq = df_q[(df_q['版本']==av)&(df_q['單元']==au)&(df_q['年度']==ay)&(df_q['冊編號']==ab)&(df_q['課編號']==al)]
            fids = [f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}" for _, r in sq.iterrows()]
            new_t = pd.DataFrame([{"對象 (分組/姓名)": target_g, "任務類型": "指派", "題目ID清單": ", ".join(fids), "說明文字": f"{au} 官方任務", "指派時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
            conn.update(worksheet="assignments", data=pd.concat([df_a, new_t], ignore_index=True)); st.success("指派成功！"); st.cache_data.clear(); st.rerun()

    with tabs[2]: # [05] 任務管理
        if not df_a.empty:
            for i, r in df_a.iloc[::-1].iterrows():
                ci, cd = st.columns([5, 1])
                ci.warning(f"📍 {r['說明文字']} (對象: {r['對象 (分組/姓名)']})")
                if cd.button("🗑️ 刪除", key=f"dt_{i}"):
                    conn.update(worksheet="assignments", data=df_a.drop(i)); st.cache_data.clear(); st.rerun()
    st.stop()

# --- ### 🟡 MODULE 6: 學生設定區 [07, 30鎖定] ---
st.markdown("## 🟡 英文練習設定區")

if st.session_state.get('quiz_loaded'):
    if st.button("🔄 🟠 重新設定範圍", type="secondary"):
        st.session_state.quiz_loaded = False; st.rerun()

if not st.session_state.get('quiz_loaded'):
    with st.expander("⚙️ 設定練習範圍", expanded=True):
        c_sel = st.columns(5)
        sv = c_sel[0].selectbox("1. 版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_sel[1].selectbox("2. 單元", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="s_u")
        sy = c_sel[2].selectbox("3. 年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="s_y")
        sb = c_sel[3].selectbox("4. 冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="s_b")
        # 💡 [30] 只有最後一層計算題數
        df_vuyb = df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]
        l_opts = {l: f"第 {l} 課 ({len(df_vuyb[df_vuyb['課編號']==l])} 題)" for l in sorted(df_vuyb['課編號'].unique())}
        sl = c_sel[4].selectbox("5. 課次", sorted(df_vuyb['課編號'].unique()), format_func=lambda x: l_opts.get(x), key="s_l")
        
        st.divider()
        c_num = st.columns(2)
        st_i = c_num[0].number_input("📍 起始句編號 (+/-)", 1, 100, 1, key="s_i")
        nu_i = c_num[1].number_input("🔢 練習題數 (+/-)", 1, 50, 10, key="s_n")
        
        final_base = df_vuyb[df_vuyb['課編號'] == sl].copy()
        if not final_base.empty:
            final_base['句編號_int'] = pd.to_numeric(final_base['句編號'], errors='coerce')
            actual_q = final_base[final_base['句編號_int']>=st_i].sort_values('句編號_int').head(int(nu_i))
            if st.button("🚀 正式開始練習", type="primary", use_container_width=True):
                st.session_state.update({"quiz_list": actual_q.to_dict('records'), "q_idx": 0, "quiz_loaded": True, "ans": [], "used_history": [], "shuf": [], "show_analysis": False, "start_time_ts": time.time(), "finished": False})
                st.rerun()

# --- ### 🔴 MODULE 7: 測驗引擎核心 [16, 25, 31鎖定] ---
if st.session_state.get('quiz_loaded') and not st.session_state.get('finished'):
    st.markdown("---")
    st.markdown("## 🔴 核心測驗練習中")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    st.session_state.current_qid = f"{q['版本']}_{q['年度']}_{q['冊編號']}_{q['單元']}_{q['課編號']}_{q['句編號']}"
    st.info(f"第 {st.session_state.q_idx+1} 題 / 共 {len(st.session_state.quiz_list)} 題")
    
    is_mcq = "單選" in q["單元"]
    ans_key = str(q["單選答案" if is_mcq else "重組英文答案"]).strip()
    st.subheader(f"題目：{q['單選題目'] if is_mcq else q['重組中文題目']}")
    
    if is_mcq:
        bc = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            if bc[i].button(opt, key=f"mcq_{i}", use_container_width=True):
                res = (opt == ans_key.upper()); buffer_log("單選", opt, "✅" if res else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if res else f"❌ 錯誤！答案是 ({ans_key})", "show_analysis": True}); st.rerun()
    else:
        # [25] 重組單字庫與 [16] 控制鍵
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else "請點擊單字庫進行排序...")
        c_ctrl = st.columns(2)
        if c_ctrl[0].button("⬅️ 🟠 退回", use_container_width=True) and st.session_state.ans:
            st.session_state.ans.pop(); st.session_state.used_history.pop(); st.rerun()
        if c_ctrl[1].button("🗑️ 🟠 清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []}); st.rerun()
        
        tk = re.findall(r"[\w']+|[^\w\s]", ans_key)
        if not st.session_state.get('shuf'): st.session_state.shuf = tk.copy(); random.shuffle(st.session_state.shuf)
        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True): 
                    st.session_state.ans.append(t); st.session_state.used_history.append(i); st.rerun()
        # [31] 檢查送出鍵
        if len(st.session_state.ans) == len(tk):
            st.divider()
            if st.button("✅ 檢查作答結果", type="primary", use_container_width=True):
                is_ok = "".join(st.session_state.ans).lower() == ans_key.replace(" ","").lower()
                buffer_log("重組", " ".join(st.session_state.ans), "✅" if is_ok else "❌")
                st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{ans_key}", "show_analysis": True}); st.rerun()

    if st.session_state.get('show_analysis'): st.warning(st.session_state.current_res)

    st.divider()
    nav = st.columns(2)
    if nav[0].button("⬅️ 🟠 上一題", disabled=(st.session_state.q_idx == 0), use_container_width=True):
        st.session_state.q_idx -= 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
    if nav[1].button("下一題 ➡️" if (st.session_state.q_idx + 1 < len(st.session_state.quiz_list)) else "🏁 結束測驗", type="secondary", use_container_width=True):
        if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
            st.session_state.q_idx += 1; st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False}); st.rerun()
        else: st.session_state.finished = True; flush_buffer_to_cloud(); st.rerun()

st.caption(f"Ver {VERSION} | 🟢 導師管理中心全功能物理恢復鎖定")
