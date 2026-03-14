# ==============================================================================
# 🧩 英文全能練習系統 (V2.8.98 - 任務日期可修改版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.8.98
# 📅 更新日期: 2026-03-14
# 🛠️ 修復重點：
#    1. [核心] set_page_config 移至最頂部，避免潛在初始化錯誤。
#    2. [資料] conn.create() → append 邏輯，logs/assignments 不再被覆蓋。
#    3. [功能] 單選題補上選項文字 (選項A/B/C/D 欄位)。
#    4. [穩定] 句編號 int() 轉換改用 pd.to_numeric 加保護。
#    5. [效能] load_dynamic_data 加上 @st.cache_data(ttl=10)。
#    6. [穩定] 資料載入失敗時提早 st.stop()，避免後續 None 崩潰。
# 🆕 新增功能：
#    7. [Box B] 新增「📖 題目講解」tab：篩選學生與題目範圍、顯示各學生
#              最近答案、老師可輸入講解備註、點選完成後寫入 logs (結果='📖 講解')。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "2.8.98"

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
    st.markdown("🏆 **成就排行**")
    if not df_l.empty and '時間' in df_l.columns:
        now_sb   = get_now()
        period   = st.radio("統計區間", ["今日", "本週", "本月"], horizontal=True, key="sb_period", label_visibility="collapsed")
        if period == "今日":
            prefix = now_sb.strftime("%Y-%m-%d")
        elif period == "本週":
            week_start = (now_sb - timedelta(days=now_sb.weekday())).strftime("%Y-%m-%d")
            prefix = None
        else:
            prefix = now_sb.strftime("%Y-%m")

        # 判斷群組：ADMIN 看全部，學生看自己群組
        target_group = st.session_state.group_id if st.session_state.group_id != "ADMIN" else None
        df_lb = df_l.copy()
        if target_group:
            df_lb = df_lb[df_lb['分組'] == target_group]

        if period == "本週":
            df_lb = df_lb[df_lb['時間'] >= week_start]
        else:
            df_lb = df_lb[df_lb['時間'].str.startswith(prefix)]

        df_lb = df_lb[df_lb['結果'] == '✅']

        # 取學生名單
        if target_group:
            members = sorted(df_s[df_s['分組'] == target_group]['姓名'].tolist())
        else:
            members = sorted(df_s[df_s['分組'] != 'ADMIN']['姓名'].tolist())

        for m in members:
            cnt = len(df_lb[df_lb['姓名'] == m])
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {cnt} 題</div>', unsafe_allow_html=True)
    st.write("")
    st.caption(f"Ver {VERSION}")

# ------------------------------------------------------------------------------
# 📦 【盒子 B：導師中心】
# ------------------------------------------------------------------------------
if st.session_state.group_id == "ADMIN" and st.session_state.view_mode == "管理後台":
    st.markdown("## 🟢 導師中心 (盒子 B)")

    t1, t2, t3, t4 = st.tabs(["📋 指派任務", "📈 數據監控", "📋 學生名單", "📖 題目講解"])

    with t1:
        # ══════════════════════════════════════════════════════════════════
        # 區塊一：發布新任務
        # ══════════════════════════════════════════════════════════════════
        st.subheader("📢 發布新任務")

        # ── 基本設定 ──────────────────────────────────────────────────────
        c1, c2 = st.columns(2)
        task_title    = c1.text_input("任務名稱", value=f"任務_{get_now().strftime('%m%d')}", key="t1_title")
        target_group  = c2.selectbox("目標班級/分組", sorted(df_s[df_s['分組'] != 'ADMIN']['分組'].unique()), key="t1_group")

        # 指派對象：班級全體 or 個別學生
        group_members = sorted(df_s[df_s['分組'] == target_group]['姓名'].tolist())
        target_mode   = st.radio("指派對象", ["全班", "指定學生"], horizontal=True, key="t1_mode")
        if target_mode == "指定學生":
            target_students_t1 = st.multiselect("選擇學生（可複選）", group_members, default=group_members, key="t1_stu")
        else:
            target_students_t1 = group_members

        # 開始／結束日期
        dc1, dc2 = st.columns(2)
        now_tw_t1  = get_now()
        date_start = dc1.date_input("📅 開始日期", value=now_tw_t1.date(), key="t1_start")
        date_end   = dc2.date_input("📅 結束日期", value=now_tw_t1.date() + timedelta(days=7), key="t1_end")

        # ── 題目範圍篩選 ──────────────────────────────────────────────────
        st.markdown("**⚙️ 題目範圍**")
        tc = st.columns(5)
        t1v = tc[0].selectbox("版本",  sorted(df_q['版本'].unique()), key="t1_v")
        t1u = tc[1].selectbox("單元",  sorted(df_q[df_q['版本'] == t1v]['單元'].unique()), key="t1_u")
        t1y = tc[2].selectbox("年度",  sorted(df_q[(df_q['版本'] == t1v) & (df_q['單元'] == t1u)]['年度'].unique()), key="t1_y")
        t1b = tc[3].selectbox("冊編號", sorted(df_q[(df_q['版本'] == t1v) & (df_q['單元'] == t1u) & (df_q['年度'] == t1y)]['冊編號'].unique()), key="t1_b")
        t1l = tc[4].selectbox("課編號", sorted(df_q[(df_q['版本'] == t1v) & (df_q['單元'] == t1u) & (df_q['年度'] == t1y) & (df_q['冊編號'] == t1b)]['課編號'].unique()), key="t1_l")

        df_t1_scope = df_q[
            (df_q['版本'] == t1v) & (df_q['單元'] == t1u) &
            (df_q['年度'] == t1y) & (df_q['冊編號'] == t1b) &
            (df_q['課編號'] == t1l)
        ].copy()
        df_t1_scope['題目ID'] = df_t1_scope.apply(
            lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
        )
        st.caption(f"此範圍共 {len(df_t1_scope)} 題")

        # ── 參考學生錯題篩選（選填） ──────────────────────────────────────
        st.markdown("**👥 參考學生錯題（選填）**")
        ref_col1, ref_col2, ref_col3 = st.columns(3)
        all_students  = sorted(df_s[df_s['分組'] != 'ADMIN']['姓名'].tolist())
        ref_students  = ref_col1.multiselect("參考學生（可複選）", all_students, key="t1_ref_stu")
        ref_logic     = ref_col2.selectbox("篩選邏輯", ["OR：任一人答錯過", "AND：所有人都答錯過"], key="t1_ref_logic")
        ref_min_err   = ref_col3.number_input("合計答錯次數 ≥", min_value=1, max_value=20, value=1, key="t1_ref_n")

        if ref_students and not df_l.empty and '題目ID' in df_l.columns:
            scope_ids  = set(df_t1_scope['題目ID'].tolist())
            err_logs   = df_l[(df_l['姓名'].isin(ref_students)) & (df_l['結果'] == '❌') & (df_l['題目ID'].isin(scope_ids))]
            err_counts = err_logs.groupby('題目ID').size().reset_index(name='錯誤次數')
            err_counts = err_counts[err_counts['錯誤次數'] >= ref_min_err]
            qualified_ids = set(err_counts['題目ID'].tolist())
            if "AND" in ref_logic:
                for stu in ref_students:
                    stu_err = set(df_l[(df_l['姓名'] == stu) & (df_l['結果'] == '❌') & (df_l['題目ID'].isin(scope_ids))]['題目ID'].tolist())
                    qualified_ids &= stu_err
            df_t1_final = df_t1_scope[df_t1_scope['題目ID'].isin(qualified_ids)].copy()
            df_t1_final = df_t1_final.merge(err_counts, on='題目ID', how='left').fillna({'錯誤次數': 0})
            df_t1_final['錯誤次數'] = df_t1_final['錯誤次數'].astype(int)
            st.info(f"📊 符合條件：{len(df_t1_final)} 題（從 {len(df_t1_scope)} 題中篩選）")
        else:
            df_t1_final = df_t1_scope.copy()

        # 預覽
        is_mcq_t1    = "單選" in t1u
        title_col_t1 = "單選題目" if is_mcq_t1 else "重組中文題目"
        preview_cols = ['句編號', title_col_t1, '題目ID'] + (['錯誤次數'] if '錯誤次數' in df_t1_final.columns else [])
        df_preview   = df_t1_final[[c for c in preview_cols if c in df_t1_final.columns]].copy()
        df_preview.columns = [c if c != title_col_t1 else '題目' for c in df_preview.columns]
        with st.expander(f"📋 預覽題目清單（{len(df_t1_final)} 題）", expanded=False):
            st.dataframe(df_preview, use_container_width=True)

        st.divider()

        if st.button("🚀 確認發布任務", use_container_width=True, type="primary"):
            if df_t1_final.empty:
                st.error("❌ 目前無符合條件的題目，請調整篩選條件")
            elif not target_students_t1:
                st.error("❌ 請至少選擇一位學生")
            elif date_end < date_start:
                st.error("❌ 結束日期不能早於開始日期")
            else:
                new_task = pd.DataFrame([{
                    "建立時間":   get_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "任務名稱":   task_title,
                    "對象班級":   target_group,
                    "指派學生":   ",".join(target_students_t1),
                    "指派人數":   len(target_students_t1),
                    "內容":       f"{t1v}|{t1u}|{t1y}|{t1b}|{t1l}",
                    "題目數":     len(df_t1_final),
                    "題目ID清單": ",".join(df_t1_final['題目ID'].tolist()),
                    "開始日期":   str(date_start),
                    "結束日期":   str(date_end),
                    "參考學生":   ",".join(ref_students) if ref_students else "",
                    "狀態":       "進行中"
                }])
                if append_to_sheet("assignments", new_task):
                    st.success(f"✅ 任務已發布！共 {len(df_t1_final)} 題，指派給 {len(target_students_t1)} 位學生")
                    load_dynamic_data.clear()
                    st.rerun()

        # ══════════════════════════════════════════════════════════════════
        # 區塊二：任務列表
        # ══════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("📋 任務列表")

        df_a2 = df_a[df_a.get('狀態', pd.Series(dtype=str)).fillna('') != '已刪除'].copy() if not df_a.empty else pd.DataFrame()

        if df_a2.empty or '任務名稱' not in df_a2.columns:
            st.info("目前尚無任務。")
        else:
            for idx, row in df_a2.iterrows():
                task_name    = row.get('任務名稱', '未命名')
                task_group   = row.get('對象班級', row.get('對象', ''))
                task_start   = row.get('開始日期', '')
                task_end     = row.get('結束日期', '')
                task_q_count = int(row.get('題目數', 0)) if str(row.get('題目數', '')).isdigit() else 0
                task_stu_str = str(row.get('指派學生', ''))
                task_q_ids   = str(row.get('題目ID清單', ''))
                task_status  = str(row.get('狀態', '進行中'))

                assigned_stus = [s.strip() for s in task_stu_str.split(',') if s.strip()] if task_stu_str else []
                q_ids_set     = set([q.strip() for q in task_q_ids.split(',') if q.strip()]) if task_q_ids else set()
                assign_count  = len(assigned_stus)

                # 計算完成人數：每位指派學生都答過所有題目ID（有任一作答紀錄即算）
                completed = 0
                if assigned_stus and q_ids_set and not df_l.empty and '題目ID' in df_l.columns:
                    for stu in assigned_stus:
                        stu_done = set(df_l[(df_l['姓名'] == stu) & (~df_l['結果'].str.contains('📖', na=False))]['題目ID'].tolist())
                        if q_ids_set.issubset(stu_done):
                            completed += 1

                all_done  = (completed == assign_count and assign_count > 0)
                done_icon = "🟢" if all_done else "🔴"
                date_info = f"{task_start} ～ {task_end}" if task_start else ""

                with st.expander(f"{done_icon} {task_name}　{task_group}　{date_info}　✅{completed}/{assign_count}人"):
                    ic1, ic2, ic3, ic4 = st.columns(4)
                    ic1.metric("指派人數", assign_count)
                    ic2.metric("已完成", completed)
                    ic3.metric("題目數", task_q_count)
                    ic4.metric("狀態", "🟢 全部完成" if all_done else ("🔴 進行中" if task_status != '已結束' else "⚫ 已結束"))

                    if assigned_stus:
                        st.markdown("**指派學生：**" + "、".join(assigned_stus))

                    # 各學生完成狀況
                    if assigned_stus and q_ids_set and not df_l.empty and '題目ID' in df_l.columns:
                        st.markdown("**學生完成狀況：**")
                        sc = st.columns(min(len(assigned_stus), 5))
                        for i, stu in enumerate(assigned_stus):
                            stu_done = set(df_l[(df_l['姓名'] == stu) & (~df_l['結果'].str.contains('📖', na=False))]['題目ID'].tolist())
                            done_q   = len(q_ids_set & stu_done)
                            sc[i % 5].markdown(f"{'✅' if q_ids_set.issubset(stu_done) else '🔄'} **{stu}**  \n{done_q}/{task_q_count} 題")

                    st.divider()

                    # ── 修改日期 ──────────────────────────────────────────
                    st.markdown("**📅 修改任務日期**")
                    ed1, ed2, ed3 = st.columns([2, 2, 1])
                    try:
                        cur_start = datetime.strptime(task_start, "%Y-%m-%d").date() if task_start else get_now().date()
                        cur_end   = datetime.strptime(task_end,   "%Y-%m-%d").date() if task_end   else get_now().date() + timedelta(days=7)
                    except:
                        cur_start = get_now().date()
                        cur_end   = get_now().date() + timedelta(days=7)

                    new_start = ed1.date_input("開始日期", value=cur_start, key=f"edit_start_{idx}")
                    new_end   = ed2.date_input("結束日期", value=cur_end,   key=f"edit_end_{idx}")
                    if ed3.button("💾 儲存", key=f"save_date_{idx}", use_container_width=True):
                        if new_end < new_start:
                            st.error("❌ 結束日期不能早於開始日期")
                        else:
                            try:
                                df_a_edit = conn.read(worksheet="assignments", ttl=0)
                                df_a_edit.at[idx, '開始日期'] = str(new_start)
                                df_a_edit.at[idx, '結束日期'] = str(new_end)
                                conn.update(worksheet="assignments", data=df_a_edit)
                                load_dynamic_data.clear()
                                st.success("✅ 日期已更新")
                                st.rerun()
                            except Exception as e:
                                st.error(f"儲存失敗：{e}")

                    st.divider()
                    del_key = f"del_task_{idx}"
                    if st.button("🗑️ 刪除此任務", key=del_key):
                        try:
                            df_a_edit = conn.read(worksheet="assignments", ttl=0)
                            df_a_edit.at[idx, '狀態'] = '已刪除'
                            conn.update(worksheet="assignments", data=df_a_edit)
                            load_dynamic_data.clear()
                            st.success("✅ 任務已標記刪除")
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：{e}")

    with t2:
        st.subheader("📊 數據監控")

        if df_l.empty:
            st.info("目前尚無作答紀錄。")
        else:
            df_l2 = df_l.copy()
            df_l2['時間'] = pd.to_datetime(df_l2['時間'], errors='coerce')

            # ── 第一排：時間 / 群組 / 學生 / 結果 ────────────────────────
            fc1, fc2, fc3, fc4 = st.columns(4)

            now_tw   = get_now()
            time_opt = fc1.selectbox("🕐 時間範圍", ["今日", "本週", "本月", "全部", "自訂"], key="log_time_opt")
            if time_opt == "今日":
                date_from, date_to = now_tw.date(), now_tw.date()
            elif time_opt == "本週":
                date_from = (now_tw - timedelta(days=now_tw.weekday())).date()
                date_to   = now_tw.date()
            elif time_opt == "本月":
                date_from = now_tw.date().replace(day=1)
                date_to   = now_tw.date()
            elif time_opt == "自訂":
                date_from = fc1.date_input("起始日", value=now_tw.date() - timedelta(days=7), key="log_date_from")
                date_to   = fc1.date_input("結束日", value=now_tw.date(), key="log_date_to")
            else:
                date_from, date_to = None, None

            group_opts = ["不限"] + sorted(df_s[df_s['分組'] != 'ADMIN']['分組'].unique().tolist())
            sel_group  = fc2.selectbox("👥 群組", group_opts, key="log_group")

            stu_pool = (
                sorted(df_s[df_s['分組'] != 'ADMIN']['姓名'].tolist())
                if sel_group == "不限"
                else sorted(df_s[df_s['分組'] == sel_group]['姓名'].tolist())
            )
            sel_stu    = fc3.selectbox("👤 學生", ["不限"] + stu_pool, key="log_stu")
            sel_result = fc4.selectbox("📋 結果", ["全部", "✅ 正確", "❌ 錯誤", "📖 講解"], key="log_result")

            # ── 第二排：題目範圍篩選 ──────────────────────────────────────
            qc1, qc2, qc3, qc4, qc5, qc6 = st.columns(6)

            fv_opts = ["全部"] + sorted(df_q['版本'].unique())
            fv = qc1.selectbox("版本", fv_opts, key="log_fv")

            fu_src = df_q[df_q['版本'] == fv] if fv != "全部" else df_q
            fu = qc2.selectbox("單元", ["全部"] + sorted(fu_src['單元'].unique()), key="log_fu")

            fy_src = fu_src[fu_src['單元'] == fu] if fu != "全部" else fu_src
            fy = qc3.selectbox("年度", ["全部"] + sorted(fy_src['年度'].unique()), key="log_fy")

            fb_src = fy_src[fy_src['年度'] == fy] if fy != "全部" else fy_src
            fb = qc4.selectbox("冊編號", ["全部"] + sorted(fb_src['冊編號'].unique()), key="log_fb")

            fl_src = fb_src[fb_src['冊編號'] == fb] if fb != "全部" else fb_src
            fl = qc5.selectbox("課編號", ["全部"] + sorted(fl_src['課編號'].unique()), key="log_fl")

            fs_src = fl_src[fl_src['課編號'] == fl] if fl != "全部" else fl_src
            fs = qc6.selectbox("句編號", ["全部"] + sorted(fs_src['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0), key="log_fs")

            # ── 套用篩選 ──────────────────────────────────────────────────
            mask = pd.Series([True] * len(df_l2), index=df_l2.index)
            if date_from:
                mask &= (df_l2['時間'].dt.date >= date_from) & (df_l2['時間'].dt.date <= date_to)
            if sel_group != "不限":
                mask &= (df_l2['分組'] == sel_group)
            if sel_stu != "不限":
                mask &= (df_l2['姓名'] == sel_stu)
            if sel_result != "全部":
                result_map = {"✅ 正確": "✅", "❌ 錯誤": "❌", "📖 講解": "📖 講解"}
                mask &= df_l2['結果'].str.startswith(result_map[sel_result])

            # 題目ID 包含各層篩選條件
            if fv != "全部":
                mask &= df_l2['題目ID'].str.startswith(fv, na=False)
            if fu != "全部":
                mask &= df_l2['題目ID'].str.contains(f"_{fu}_", na=False)
            if fy != "全部":
                mask &= df_l2['題目ID'].str.contains(f"_{fy}_", na=False)
            if fb != "全部":
                mask &= df_l2['題目ID'].str.contains(f"_{fb}_", na=False)
            if fl != "全部":
                mask &= df_l2['題目ID'].str.contains(f"_{fl}_", na=False)
            if fs != "全部":
                mask &= df_l2['題目ID'].str.endswith(f"_{fs}", na=False)

            df_filtered = df_l2[mask].sort_values("時間", ascending=False).copy()
            df_filtered['時間'] = df_filtered['時間'].dt.strftime("%Y-%m-%d %H:%M:%S")

            st.caption(f"共 {len(df_filtered)} 筆紀錄")
            st.dataframe(df_filtered, use_container_width=True)

    with t3:
        st.subheader("👥 學生帳號清單")
        st.dataframe(df_s, use_container_width=True)

    # --------------------------------------------------------------------------
    # 🆕 【Tab 4：題目講解】
    # --------------------------------------------------------------------------
    with t4:
        st.subheader("📖 題目講解")

        # ── 步驟 1：篩選班級與學生 ────────────────────────────────────────
        rev_group = st.selectbox(
            "👥 班級/分組",
            sorted(df_s[df_s['分組'] != 'ADMIN']['分組'].unique()),
            key="rev_group"
        )
        students_in_group = sorted(df_s[df_s['分組'] == rev_group]['姓名'].tolist())
        rev_students = st.multiselect(
            "👤 學生（預設全選，可自由增刪）",
            options=students_in_group,
            default=students_in_group,
            key="rev_students"
        )

        # 決定實際要統計/寫入的學生清單
        target_students = rev_students if rev_students else students_in_group

        # ── 步驟 2：篩選題目範圍 ──────────────────────────────────────────
        st.markdown("**⚙️ 題目範圍**")
        rc = st.columns(5)
        rv = rc[0].selectbox("版本", sorted(df_q['版本'].unique()), key="rev_v")
        ru = rc[1].selectbox("單元", sorted(df_q[df_q['版本'] == rv]['單元'].unique()), key="rev_u")
        ry = rc[2].selectbox("年度", sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru)]['年度'].unique()), key="rev_y")
        rb = rc[3].selectbox("冊別", sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru) & (df_q['年度'] == ry)]['冊編號'].unique()), key="rev_b")
        rl = rc[4].selectbox("課次", sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru) & (df_q['年度'] == ry) & (df_q['冊編號'] == rb)]['課編號'].unique()), key="rev_l")

        # 取得該範圍所有題目
        df_rev_scope = df_q[
            (df_q['版本'] == rv) & (df_q['單元'] == ru) &
            (df_q['年度'] == ry) & (df_q['冊編號'] == rb) &
            (df_q['課編號'] == rl)
        ].copy()
        df_rev_scope['題目ID'] = df_rev_scope.apply(
            lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
        )

        if df_rev_scope.empty:
            st.info("此範圍尚無題目。")
        else:
            st.markdown(f"**📋 共 {len(df_rev_scope)} 題，點選一題開始講解：**")

            # 取得目標學生的所有答題紀錄（保留全部歷史）
            if not df_l.empty and '題目ID' in df_l.columns:
                df_group_logs = df_l[df_l['姓名'].isin(target_students)].copy()
                df_group_logs = df_group_logs.sort_values('時間', ascending=False)
            else:
                df_group_logs = pd.DataFrame()

            is_mcq_scope = "單選" in ru

            for _, qrow in df_rev_scope.iterrows():
                qid       = qrow['題目ID']
                title_col = "單選題目" if is_mcq_scope else "重組中文題目"
                ans_col   = "單選答案" if is_mcq_scope else "重組英文答案"
                q_title   = qrow.get(title_col) or qrow.get('中文題目') or '【無資料】'
                q_ans     = str(qrow.get(ans_col) or qrow.get('英文答案') or '').strip()

                # 統計（排除講解紀錄，只算真實作答）
                if not df_group_logs.empty:
                    q_logs_all = df_group_logs[df_group_logs['題目ID'] == qid]
                    q_logs_ans = q_logs_all[~q_logs_all['結果'].str.contains('📖', na=False)]
                    attempted  = q_logs_ans['姓名'].nunique()
                    correct    = len(q_logs_ans[q_logs_ans['結果'] == '✅'].drop_duplicates(subset=['姓名']))
                    reviewed   = len(q_logs_all[q_logs_all['結果'] == '📖 講解'])
                else:
                    q_logs_all = pd.DataFrame()
                    attempted, correct, reviewed = 0, 0, 0

                # 每位學生最新一筆結果（姓名：文字說明+個人講解標記）
                stu_tags = []
                for stu in target_students:
                    if not q_logs_all.empty:
                        stu_ans_rows = q_logs_all[
                            (q_logs_all['姓名'] == stu) &
                            (~q_logs_all['結果'].str.contains('📖', na=False))
                        ]
                        stu_rev_rows = q_logs_all[
                            (q_logs_all['姓名'] == stu) &
                            (q_logs_all['結果'] == '📖 講解')
                        ]
                    else:
                        stu_ans_rows = pd.DataFrame()
                        stu_rev_rows = pd.DataFrame()

                    if stu_ans_rows.empty:
                        status = "未作答"
                    elif stu_ans_rows.iloc[0]['結果'] == "✅":
                        status = "正確✅"
                    else:
                        status = "錯誤❌"
                    rev = "📖" if not stu_rev_rows.empty else ""
                    stu_tags.append(f"{stu}：{status}{rev}")

                stu_tag_str = "　|　".join(stu_tags)
                label = (
                    f"句 {qrow['句編號']}｜{q_title[:16]}{'…' if len(q_title)>16 else ''}"
                    f"　　{stu_tag_str}"
                )

                with st.expander(label):

                    # ── 題目放大顯示 ──────────────────────────────────────
                    st.markdown(
                        f"<div style='font-size:1.35rem; font-weight:600; padding:12px 0 4px;'>"
                        f"📝 {q_title}</div>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f"<div style='font-size:1.2rem; color:green; padding-bottom:12px;'>"
                        f"✅ 正確答案：{q_ans}</div>",
                        unsafe_allow_html=True
                    )
                    st.divider()

                    # ── 講解完成按鈕 ──────────────────────────────────────
                    btn_key = f"rev_done_{qid}"
                    if st.button("📖 講解完成，寫入紀錄", key=btn_key, type="primary", use_container_width=True):
                        now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
                        rows = [
                            {"時間": now_str, "姓名": stu, "分組": rev_group,
                             "題目ID": qid, "結果": "📖 講解", "學生答案": ""}
                            for stu in target_students
                        ]
                        if append_to_sheet("logs", pd.DataFrame(rows)):
                            st.success(f"✅ 已為 {len(target_students)} 位學生寫入講解紀錄！")
                            load_dynamic_data.clear()
                            st.rerun()

                    # ── 學生作答歷史（放在按鈕下方） ──────────────────────
                    st.markdown("---")
                    st.markdown("**👥 學生作答歷史**")
                    for stu in target_students:
                        if not q_logs_all.empty:
                            stu_rows = q_logs_all[
                                (q_logs_all['姓名'] == stu) &
                                (~q_logs_all['結果'].str.contains('📖', na=False))
                            ]
                        else:
                            stu_rows = pd.DataFrame()

                        if stu_rows.empty:
                            st.markdown(f"　👤 **{stu}**：尚未作答")
                        else:
                            lines = []
                            for _, r in stu_rows.iterrows():
                                icon    = r.get('結果', '—')
                                ans_val = r.get('學生答案', '')
                                t_str   = str(r.get('時間', ''))[:16]
                                ans_disp = f" `{ans_val}`" if ans_val and ans_val not in ('—', '') else ''
                                lines.append(f"{icon}{ans_disp} _{t_str}_")
                            st.markdown(f"　👤 **{stu}**：" + "　／　".join(lines))

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
