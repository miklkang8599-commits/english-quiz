# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.83 - 優化修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.83
# 📅 更新日期: 2026-03-14
# 🛠️ 修復重點：
#    1. [核心] set_page_config 移至最頂部，避免潛在初始化錯誤。
#    2. [資料] conn.create() → append 邏輯，logs/assignments 不再被覆蓋。
#    3. [功能] 單選題補上選項文字 (選項A/B/C/D 欄位)。
#    4. [穩定] 句編號 int() 轉換改用 pd.to_numeric 加保護。
#    5. [效能] load_dynamic_data 加上 @st.cache_data(ttl=10)。
#    6. [穩定] 資料載入失敗時提早 st.stop()，避免後續 None 崩潰。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.83"

# ==============================================================================
# ✅ 修復 1：set_page_config 必須是第一個 Streamlit 呼叫
# ==============================================================================
st.set_page_config(page_title=f"英文練習系統 V{VERSION}", layout="wide")

# ------------------------------------------------------------------------------
# 📦 【盒子 A：系統核心 (時區與基礎邏輯)】
# ------------------------------------------------------------------------------
def get_now():
    """物理鎖定台灣時間 (GMT+8)"""
    return datetime.utcnow() + timedelta(hours=8)

def standardize(v):
    """ID 標準化"""
    val = str(v).split('.')[0].strip()
    return val.zfill(4) if val.isdigit() else val

def clean_string_for_compare(s):
    """標點忽略比對邏輯 (含括號相容)"""
    s = s.lower().replace(" ", "").replace("\u2018", "'").replace("\u2019", "'")
    s = re.sub(r'[.,?!:;()]', '', s)
    return s.strip()

def show_version_caption():
    """全域版號顯示組件"""
    st.caption(f"🚀 系統版本：Ver {VERSION} | 🌍 台灣時間鎖定 (GMT+8)")

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

# ==============================================================================
# ✅ 修復 5：load_dynamic_data 加上快取，避免每次 rerun 都重新讀取
# ==============================================================================
@st.cache_data(ttl=10)
def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=0)
        df_l = conn.read(worksheet="logs", ttl=0)
        return df_a, df_l
    except:
        return pd.DataFrame(), pd.DataFrame()

# ==============================================================================
# ✅ 修復 2：append 寫入函式，取代錯誤的 conn.create()
# ==============================================================================
def append_to_sheet(worksheet_name: str, new_row: pd.DataFrame):
    """安全地將一行資料附加到工作表末尾"""
    try:
        existing = conn.read(worksheet=worksheet_name, ttl=0)
        if existing is None or existing.empty:
            existing = pd.DataFrame(columns=new_row.columns)
        updated = pd.concat([existing, new_row], ignore_index=True)
        conn.update(worksheet=worksheet_name, data=updated)
        # 清除快取讓下次讀取到最新資料
        load_dynamic_data.clear()
        return True
    except Exception as e:
        st.warning(f"⚠️ 資料寫入失敗: {e}")
        return False

# ------------------------------------------------------------------------------
# 🔐 【權限控管與登入】
# ------------------------------------------------------------------------------
if not st.session_state.get('logged_in', False):
    df_q, df_s = load_static_data()
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### 🔵 系統登入")
        i_id = st.text_input("帳號 (學號/員工編號)", key="l_id")
        i_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("🚀 登入系統", use_container_width=True):
            # ==============================================================
            # ✅ 修復 6：資料載入失敗時提早停止
            # ==============================================================
            if df_s is None:
                st.error("❌ 無法載入學生資料，請稍後再試")
                st.stop()
            std_id, std_pw = standardize(i_id), standardize(i_pw)
            df_s['c_id'] = df_s['帳號'].apply(standardize)
            df_s['c_pw'] = df_s['密碼'].apply(standardize)
            user = df_s[df_s['c_id'] == std_id]
            if not user.empty and user.iloc[0]['c_pw'] == std_pw:
                st.session_state.clear()
                st.session_state.update({
                    "logged_in": True,
                    "user_id": f"EA{std_id}",
                    "user_name": user.iloc[0]['姓名'],
                    "group_id": user.iloc[0]['分組'],
                    "view_mode": "管理後台" if user.iloc[0]['分組'] == "ADMIN" else "練習模式"
                })
                st.rerun()
            else:
                st.error("❌ 帳號或密碼錯誤")
        show_version_caption()
    st.stop()

# 載入資料（登入後）
df_q, df_s = load_static_data()
df_a, df_l = load_dynamic_data()

# ==============================================================================
# ✅ 修復 6：資料載入失敗時提早停止，避免後續 None 錯誤
# ==============================================================================
if df_q is None or df_s is None:
    st.error("❌ 資料載入失敗，請重新整理頁面")
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 E：側邊排行】
# ------------------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 {st.session_state.user_name} ({st.session_state.group_id})")
    if st.session_state.group_id == "ADMIN":
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"])
    if st.button("🚪 登出系統", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.divider()
    st.markdown("🏆 **今日成就排行**")
    if not df_l.empty and '時間' in df_l.columns:
        today_str = get_now().strftime("%Y-%m-%d")
        gl = df_l[
            (df_l['分組'] == st.session_state.group_id) &
            (df_l['時間'].str.startswith(today_str))
        ].copy()
        for m in sorted(df_s[df_s['分組'] == st.session_state.group_id]['姓名'].tolist()):
            c_cnt = len(gl[(gl['姓名'] == m) & (gl['結果'] == '✅')])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {c_cnt} 題</div>', unsafe_allow_html=True)
    st.write("")
    st.caption(f"Ver {VERSION}")

# ------------------------------------------------------------------------------
# 📦 【盒子 B：導師中心】
# ------------------------------------------------------------------------------
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師中心 (盒子 B)")

    t1, t2, t3 = st.tabs(["📋 指派任務", "📈 數據監控", "📋 學生名單"])

    with t1:
        st.subheader("📢 發布新任務")
        c1, c2 = st.columns(2)
        target_group = c1.selectbox("目標班級/分組", sorted(df_s['分組'].unique()))
        task_title = c2.text_input("任務名稱", value=f"任務_{get_now().strftime('%m%d')}")

        sub_v = st.selectbox("選擇版本", sorted(df_q['版本'].unique()), key="admin_v")
        sub_u = st.multiselect("選擇單元", sorted(df_q[df_q['版本'] == sub_v]['單元'].unique()))

        if st.button("🚀 確認發布任務", use_container_width=True):
            new_task = pd.DataFrame([{
                "時間": get_now().strftime("%Y-%m-%d %H:%M:%S"),
                "對象": target_group,
                "任務名稱": task_title,
                "內容": f"{sub_v} | {','.join(sub_u)}",
                "狀態": "進行中"
            }])
            # ✅ 修復 2：改用 append 寫入
            if append_to_sheet("assignments", new_task):
                st.success("✅ 任務已成功指派至 Google Sheets！")

    with t2:
        st.subheader("📊 學生作答 Log (台灣時間排序)")
        if not df_l.empty:
            st.dataframe(df_l.sort_values("時間", ascending=False), use_container_width=True)
        else:
            st.info("目前尚無作答紀錄。")

    with t3:
        st.subheader("👥 學生帳號清單")
        st.dataframe(df_s, use_container_width=True)

    show_version_caption()
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 C：練習範圍設定】
# ------------------------------------------------------------------------------
if not st.session_state.quiz_loaded:
    st.markdown("## 🟡 練習範圍設定 (盒子 C)")

    with st.expander("⚙️ 篩選題目範圍", expanded=not st.session_state.range_confirmed):
        c_s = st.columns(5)
        sv = c_s[0].selectbox("版本", sorted(df_q['版本'].unique()), key="s_v")
        su = c_s[1].selectbox("單元", sorted(df_q[df_q['版本'] == sv]['單元'].unique()), key="s_u")
        sy = c_s[2].selectbox("年度", sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su)]['年度'].unique()), key="s_y")
        sb = c_s[3].selectbox("冊別", sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su) & (df_q['年度'] == sy)]['冊編號'].unique()), key="s_b")
        sl = c_s[4].selectbox("課次", sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su) & (df_q['年度'] == sy) & (df_q['冊編號'] == sb)]['課編號'].unique()), key="s_l")

        if st.button("🔍 確認範圍", use_container_width=True):
            st.session_state.range_confirmed = True
            st.rerun()

    if st.session_state.range_confirmed:
        df_scope = df_q[
            (df_q['版本'] == st.session_state.s_v) &
            (df_q['單元'] == st.session_state.s_u) &
            (df_q['年度'] == st.session_state.s_y) &
            (df_q['冊編號'] == st.session_state.s_b) &
            (df_q['課編號'] == st.session_state.s_l)
        ].copy()
        df_scope['題目ID'] = df_scope.apply(
            lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
        )

        st.markdown("---")
        q_mode = st.radio("🎯 模式選擇：", ["1. 起始句開始", "2. 未練習", "3. 錯題復習"], horizontal=True)

        cc1, cc2 = st.columns(2)
        all_sentences = sorted(df_scope['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0)
        start_q = cc1.selectbox("🔢 指定起始句編號", all_sentences)
        nu_i = cc2.number_input("🔢 練習題目數量", 1, 100, 10)

        # ==============================================================
        # ✅ 修復 4：用 pd.to_numeric 取代直接 int()，避免非數字崩潰
        # ==============================================================
        if "1. 起始句" in q_mode:
            df_scope['_num'] = pd.to_numeric(df_scope['句編號'], errors='coerce').fillna(0)
            df_final = df_scope[df_scope['_num'] >= int(start_q)].sort_values('_num').copy()
        elif "2. 未練習" in q_mode:
            done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique() if not df_l.empty else []
            df_final = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
        else:
            if not df_l.empty:
                wrong_ids = df_l[
                    (df_l['姓名'] == st.session_state.user_name) &
                    (df_l['結果'].str.contains('❌', na=False))
                ]['題目ID'].unique()
            else:
                wrong_ids = []
            df_final = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()

        st.success(f"📊 目前範圍內共有 {len(df_final)} 題符合條件")

        if st.button("🚀 正式開始練習", type="primary", use_container_width=True):
            if not df_final.empty:
                st.session_state.update({
                    "quiz_list": df_final.head(int(nu_i)).to_dict('records'),
                    "q_idx": 0,
                    "quiz_loaded": True,
                    "ans": [],
                    "used_history": [],
                    "shuf": [],
                    "show_analysis": False
                })
                st.rerun()
            else:
                st.error("❌ 此範圍內無符合題目，請重新選擇！")

    show_version_caption()

# ------------------------------------------------------------------------------
# 📦 【盒子 D：練習引擎】
# ------------------------------------------------------------------------------
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} / {len(st.session_state.quiz_list)} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq = "單選" in q.get("單元", "")

    # 題目標題
    title_key = "單選題目" if is_mcq else "重組中文題目"
    st.markdown(f"#### 題目：{q.get(title_key) or q.get('中文題目') or '【無資料】'}")

    # 正確答案
    ans_col = "單選答案" if is_mcq else "重組英文答案"
    ans_key = str(q.get(ans_col) or q.get("英文答案") or "").strip()

    if is_mcq:
        # ==============================================================
        # ✅ 修復 3：單選題顯示選項文字
        # ==============================================================
        cols = st.columns(4)
        for i, opt in enumerate(["A", "B", "C", "D"]):
            opt_text = q.get(f"選項{opt}", "")
            btn_label = f"{opt}. {opt_text}" if opt_text else f" {opt} "
            if cols[i].button(btn_label, key=f"mcq_{opt}", use_container_width=True):
                is_ok = (opt.upper() == ans_key.upper())
                st.session_state.update({
                    "current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{ans_key}",
                    "show_analysis": True
                })
                # 寫入 Log
                log_data = pd.DataFrame([{
                    "時間": get_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "姓名": st.session_state.user_name,
                    "分組": st.session_state.group_id,
                    "題目ID": q.get('題目ID', 'N/A'),
                    "結果": "✅" if is_ok else "❌"
                }])
                append_to_sheet("logs", log_data)
                st.rerun()
    else:
        # 重組題介面
        st.info(" ".join(st.session_state.ans) if st.session_state.ans else "請依序點選單字按鈕...")

        c_ctrl = st.columns(2)
        if c_ctrl[0].button("⬅️ 🟠 退回一步", use_container_width=True):
            if st.session_state.ans:
                st.session_state.ans.pop()
                st.session_state.used_history.pop()
                st.rerun()
        if c_ctrl[1].button("🗑️ 🟠 全部清除", use_container_width=True):
            st.session_state.update({"ans": [], "used_history": []})
            st.rerun()

        # 單字切分與打亂
        tk = re.findall(r"[\w']+|[.,?!:;()]", ans_key)
        if not st.session_state.get('shuf'):
            st.session_state.shuf = tk.copy()
            random.shuffle(st.session_state.shuf)

        bs = st.columns(3)
        for i, t in enumerate(st.session_state.shuf):
            if i not in st.session_state.get('used_history', []):
                if bs[i % 3].button(t, key=f"qb_{i}", use_container_width=True):
                    st.session_state.ans.append(t)
                    st.session_state.used_history.append(i)
                    st.rerun()

        if len(st.session_state.ans) == len(tk) and not st.session_state.show_analysis:
            if st.button("✅ 🔵 檢查作答結果", type="primary", use_container_width=True):
                is_ok = clean_string_for_compare("".join(st.session_state.ans)) == clean_string_for_compare(ans_key)
                st.session_state.update({
                    "current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{ans_key}",
                    "show_analysis": True
                })
                # ✅ 修復 2：改用 append 寫入 Log
                log_data = pd.DataFrame([{
                    "時間": get_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "姓名": st.session_state.user_name,
                    "分組": st.session_state.group_id,
                    "題目ID": q.get('題目ID', 'N/A'),
                    "結果": "✅" if is_ok else "❌"
                }])
                append_to_sheet("logs", log_data)
                st.rerun()

    if st.session_state.get('show_analysis'):
        st.warning(st.session_state.current_res)

    st.divider()
    c_nav = st.columns(2)
    if st.session_state.q_idx > 0:
        if c_nav[0].button("⬅️ 🔵 上一題", use_container_width=True):
            st.session_state.q_idx -= 1
            st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False})
            st.rerun()

    nxt_label = "下一題 ➡️" if st.session_state.q_idx + 1 < len(st.session_state.quiz_list) else "🏁 結束練習"
    if c_nav[1].button(nxt_label, type="primary", use_container_width=True):
        if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
            st.session_state.q_idx += 1
            st.session_state.update({"ans": [], "used_history": [], "shuf": [], "show_analysis": False})
            st.rerun()
        else:
            st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
            st.rerun()

    if st.button("🏁 🔴 結束作答 (返回主選單)", use_container_width=True):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
        st.rerun()

    show_version_caption()
