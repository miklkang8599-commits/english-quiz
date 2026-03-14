# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.78 - 台灣時區物理校正版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.78
# 📅 更新日期: 2026-03-14
# 🛠️ 修復重點：
#    1. 建立 get_now() 函數，強制鎖定台灣時區 (GMT+8)。
#    2. 繼承 V2.8.77 的括號 () 相容性與單字切分規則。
#    3. 鎖定常駐「上一題/下一題」藍色按鈕與底端紅色「結束作答」。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
import time
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.78"

# ------------------------------------------------------------------------------
# 📦 【盒子 A：系統核心 (時區與基礎邏輯)】
# ------------------------------------------------------------------------------
def get_now():
    """強制獲取台灣時間 (UTC+8)"""
    return datetime.utcnow() + timedelta(hours=8)

def standardize(v):
    """標準化 ID (補零至四位)"""
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    """智慧標點比對：統一縮寫、移除空格與包含括號在內的所有標點"""
    s = s.lower().replace(" ", "").replace("’", "'").replace("‘", "'")
    s = re.sub(r'[.,?!:;()]', '', s) 
    return s.strip()

# 初始化 Session State
st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)

# 建立 GSheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_static_data():
    try:
        df_q = conn.read(worksheet="questions").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        df_s = conn.read(worksheet="students").fillna("").astype(str).replace(r'\.0$', '', regex=True)
        return df_q, df_s
    except Exception as e:
        st.error(f"靜態資料載入失敗: {e}")
        return None, None

def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=10)
        df_l = conn.read(worksheet="logs", ttl=10)
        return df_a, df_l
    except Exception as e:
        st.warning(f"動態資料載入異常: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ------------------------------------------------------------------------------
# 🔐 【權限控管：登入與模式切換】
# ------------------------------------------------------------------------------
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
                    st.session_state.update({
                        "logged_in": True, 
                        "user_id": f"EA{std_id}", 
                        "user_name": user.iloc[0]['姓名'], 
                        "group_id": user.iloc[0]['分組'],
                        "view_mode": "管理後台" if user.iloc[0]['分組']=="ADMIN" else "練習模式"
                    })
                    st.rerun()
    st.stop()

# 載入資料
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# ------------------------------------------------------------------------------
# 📦 【盒子 E：側邊排行 (使用台灣時間過濾)】
# ------------------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name} ({st.session_state.group_id})")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出系統"):
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.markdown("🏆 **今日成就排行**")
    if not df_l.empty:
        today_str = get_now().strftime("%Y-%m-%d")
        # 這裡會因 get_now() 的修正而變得精準
        gl = df_l[(df_l['分組'] == st.session_state.group_id) & (df_l['時間'].str.startswith(today_str))].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            c_cnt = len(gl[(gl['姓名']==m) & (gl['結果']=='✅')])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {c_cnt} 題</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 📦 【盒子 B：管理後台 (僅 ADMIN 可見)】
# ------------------------------------------------------------------------------
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師中心 (盒子 B)")
    st.info("此區塊為管理功能，指派紀錄將使用台灣時間存檔。")
    # (導師功能邏輯略...)
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 C：練習範圍設定】
# ------------------------------------------------------------------------------
if not st.session_state.quiz_loaded:
    st.markdown("## 🟡 練習範圍設定 (盒子 C)")
    with st.expander("⚙️ 篩選題目範圍", expanded=not st.session_state.range_confirmed):
        c_s = st.columns(5)
        sv = c_s[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_s[1].selectbox("單元", sorted(df_q[df_q['版本']==sv]['單元'].unique()), key="s_u")
        sy = c_s[2].selectbox("年度", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)]['年度'].unique()), key="s_y")
        sb = c_s[3].selectbox("冊別", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)]['冊編號'].unique()), key="s_b")
        sl = c_s[4].selectbox("課次", sorted(df_q[(df_q['版本']==sv)&(df_q['單元']==su)&(df_q['年度']==sy)&(df_q['冊編號']==sb)]['課編號'].unique()), key="s_l")
        if st.button("🔍 確認篩選", use_container_width=True):
            st.session_state.range_confirmed = True
            st.rerun()
    
    if st.session_state.range_confirmed:
        df_scope = df_q[(df_q['版本']==st.session_state.s_v)&(df_q['單元']==st.session_state.s_u)&(df_q['年度']==st.session_state.s_y)&(df_q['冊編號']==st.session_state.s_b)&(df_q['課編號']==st.session_state.s_l)].copy()
        df_scope['題目ID'] = df_scope.apply(lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1)
        
        q_mode = st.radio("🎯 篩選模式：", ["1. 全部題目", "2. 未練習", "3. 錯題復習"], horizontal=True)
        if "2. 未練習" in q_mode:
            done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique()
            df_final = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
        elif "3. 錯題" in q_mode:
            wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique()
            df_final = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()
        else:
            df_final = df_scope.sort_values('句編號').copy()
        
        st.success(f"📊 符合條件題數：{len(df_final)} 題")
        nu_i = st.number_input("🔢 練習題數", 1, 50, 10, key="s_n")
        if st.button("🚀 開始練習", type="primary", use_container_width=True):
            if not df_final.empty:
                st.session_state.update({
                    "quiz_list": df_final.head(int(nu_i)).to_dict('records'), 
                    "q_idx": 0, 
                    "quiz_loaded": True, 
                    "ans": [], 
                    "used_history": [], 
                    "shuf": [], 
                    "show_analysis": False,
                    "start_time_ts": time.time()
                })
                st.rerun()

# ------------------------------------------------------------------------------
# 📦 【盒子 D：練習引擎 (全功能對位版)】
# ------------------------------------------------------------------------------
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} / {len(st.session_state.quiz_list)} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq = "單選" in q.get("單元", "")
    
    # 題目標題顯示
    title_key = "單選題目" if is_mcq else "重組中文題目"
    st.markdown(f"#### 題目：{q.get(title_key) or q.get('中文題目') or '【無題目資料】'}")
    
    # 正確答案抓取
    ans_col = "單選答案" if is_mcq else "重組英文答案"
    ans_key = str(q.get(ans_col) or q.get("英文答案") or "").strip()
    
    if is_mcq:
        # --- [D-1] 單選題介面 ---
        cols = st.columns(4)
        for opt in ["A", "B", "C", "D"]:
            if cols["ABCD".find(opt)].button(f" {opt} ", key=f"mcq_{opt}", use_container_width=True):
                is_ok = (opt.upper() == ans_key.upper())
                st.session_state.update({
                    "current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案是 ({ans_key})", 
                    "show_analysis": True
                })
                st.rerun()
    else:
        # --- [D-2] 重組題介面 ---
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else "請點選單字按鈕...")
        
        # 🟠 操作鍵：退回與清除
        c_ctrl = st.columns(2)
        if c_ctrl[0].button("⬅️ 🟠 退回一步", use_container_width=True):
            if st.session_state.ans:
                st.session_state.ans.pop()
                st.session_state.used_history.pop()
                st.rerun()
        if c_ctrl[1].button("🗑️ 🟠 全部清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []})
            st.rerun()
        
        # 標點相容切分規則
        tk = re.findall(r"[\w']+|[.,?!:;()]", ans_key)
        if not st.session_state.get('shuf'):
            st.session_state.shuf = tk.copy()
            random.shuffle(st.session_state.shuf)
        
        # 單字庫按鈕 (三欄)
        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i%3].button(t, key=f"qb_{i}", use_container_width=True):
                    st.session_state.ans.append(t)
                    st.session_state.used_history.append(i)
                    st.rerun()
        
        # 🔵 檢查按鈕 (集滿單字時出現)
        if len(st.session_state.ans) == len(tk) and not st.session_state.show_analysis:
            st.write("")
            if st.button("✅ 🔵 檢查作答結果", type="primary", use_container_width=True):
                is_ok = clean_string_for_compare("".join(st.session_state.ans)) == clean_string_for_compare(ans_key)
                st.session_state.update({
                    "current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{ans_key}", 
                    "show_analysis": True
                })
                # 寫入 Log (使用台灣時間)
                log_data = pd.DataFrame([{
                    "時間": get_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "姓名": st.session_state.user_name,
                    "分組": st.session_state.group_id,
                    "題目ID": q.get('題目ID', 'N/A'),
                    "結果": "✅" if is_ok else f"❌ ({'/'.join(st.session_state.ans)})"
                }])
                try: conn.create(worksheet="logs", data=log_data)
                except: pass
                st.rerun()

    # --- [D-3] 分析結果與常駐導覽 ---
    if st.session_state.get('show_analysis'):
        st.warning(st.session_state.current_res)
    
    st.divider()
    c_nav = st.columns(2)
    # 藍色導覽鍵：上一題
    if st.session_state.q_idx > 0:
        if c_nav[0].button("⬅️ 🔵 上一題", use_container_width=True):
            st.session_state.q_idx -= 1
            st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False})
            st.rerun()
    
    # 藍色導覽鍵：下一題
    nxt_label = "下一題 ➡️" if st.session_state.q_idx + 1 < len(st.session_state.quiz_list) else "🏁 結束練習"
    if c_nav[1].button(nxt_label, type="primary", use_container_width=True):
        if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
            st.session_state.q_idx += 1
            st.session_state.update({"ans":[], "used_history":[], "shuf":[], "show_analysis":False})
            st.rerun()
        else:
            st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
            st.rerun()

    # 🔴 結束作答 (全寬置底)
    st.write("")
    if st.button("🏁 🔴 結束作答 (返回設定區)", use_container_width=True):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
        st.rerun()

st.caption(f"Ver {VERSION} | 台灣時間 (GMT+8) 物理校正版")
