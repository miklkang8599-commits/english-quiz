# ==============================================================================
# 🧩 英文全能練習系統 (V2.9.48 - API限流修復版)
# ==============================================================================
# 📌 版本編號 (VERSION): 2.9.48
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
import requests
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

VERSION = "2.9.62"

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

def is_admin(group_id):
    """ADMIN 和 TEACHER 都有管理後台權限"""
    return group_id in ("ADMIN", "TEACHER")

# 初始化 Session State
st.session_state.setdefault('range_confirmed', False)
st.session_state.setdefault('quiz_loaded', False)
st.session_state.setdefault('ans', [])
st.session_state.setdefault('used_history', [])
st.session_state.setdefault('show_analysis', False)

# 建立 GSheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)  # 靜態資料快取 5 分鐘（questions/students/reading 不常變動）
def load_static_data():
    try:
        df_q  = conn.read(worksheet="questions", ttl=300).fillna("").astype(str).replace(r'\.0$', '', regex=True)
        df_s  = conn.read(worksheet="students",  ttl=300).fillna("").astype(str).replace(r'\.0$', '', regex=True)
        try:
            df_r = conn.read(worksheet="reading", ttl=300).fillna("").astype(str).replace(r'\.0$', '', regex=True)
        except:
            df_r = pd.DataFrame()
        try:
            df_v = conn.read(worksheet="vocab", ttl=300).fillna("").astype(str).replace(r'\.0$', '', regex=True)
        except:
            df_v = pd.DataFrame()
        return df_q, df_s, df_r, df_v
    except Exception as e:
        st.error(f"靜態資料載入失敗: {e}")
        return None, None, pd.DataFrame(), pd.DataFrame()

# ==============================================================================
# ✅ 修復 5：load_dynamic_data 加上快取，避免每次 rerun 都重新讀取
# ==============================================================================
@st.cache_data(ttl=120)  # 動態資料快取 120 秒，加快學生答題速度
def load_dynamic_data():
    try:
        df_a = conn.read(worksheet="assignments", ttl=120)
        df_l = conn.read(worksheet="logs",        ttl=120)
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
    df_q, df_s, df_r, df_v = load_static_data()
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
                    "view_mode": "管理後台" if is_admin(user.iloc[0]["分組"]) else "練習模式"
                })
                st.rerun()
            else:
                st.error("❌ 帳號或密碼錯誤")
        show_version_caption()
    st.stop()

# 載入資料（登入後）
df_q, df_s, df_r, df_v = load_static_data()
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
    if is_admin(st.session_state.group_id):
        st.session_state.view_mode = st.radio("功能切換：", ["管理後台", "進入練習"], key="sidebar_view_mode")
    if st.button("🚪 登出系統", use_container_width=True, key="sidebar_logout"):
        st.session_state.clear()
        st.rerun()

    st.divider()
    st.markdown("🏆 **成就排行**")
    if not df_l.empty and '時間' in df_l.columns:
        now_sb   = get_now()
        period   = st.radio("統計區間", ["今日", "本週", "本月"], index=1, horizontal=True, key="sb_period", label_visibility="collapsed")
        if period == "今日":
            prefix = now_sb.strftime("%Y-%m-%d")
        elif period == "本週":
            week_start = (now_sb - timedelta(days=now_sb.weekday())).strftime("%Y-%m-%d")
            prefix = None
        else:
            prefix = now_sb.strftime("%Y-%m")

        # 判斷群組：ADMIN 看全部，學生看自己群組
        target_group = st.session_state.group_id if not is_admin(st.session_state.group_id) else None
        df_lb = df_l.copy()
        if target_group:
            df_lb = df_lb[df_lb['分組'] == target_group]

        if period == "本週":
            df_lb = df_lb[df_lb['時間'] >= week_start]
        else:
            df_lb = df_lb[df_lb['時間'].str.startswith(prefix)]

        df_lb_correct = df_lb[df_lb['結果'] == '✅']
        # 朗讀題：分數欄 >= 60 算達標（若無分數欄則只要有紀錄就算）
        df_lb_reading = df_lb[df_lb['結果'] == '🎤 朗讀'].copy()
        if '分數' in df_lb_reading.columns:
            df_lb_reading = df_lb_reading[pd.to_numeric(df_lb_reading['分數'], errors='coerce').fillna(0) >= 60]

        # 取學生名單
        if target_group:
            members = sorted(df_s[df_s['分組'] == target_group]['姓名'].tolist())
        else:
            members = sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['姓名'].tolist())

        for m in members:
            q_cnt = len(df_lb_correct[df_lb_correct['姓名'] == m])
            r_cnt = len(df_lb_reading[df_lb_reading['姓名'] == m])
            total = q_cnt + r_cnt
            detail = f"📝{q_cnt} 🎤{r_cnt}" if r_cnt > 0 else f"{q_cnt} 題"
            st.markdown(f'<div style="font-size:12px;">👤 {m}: {total} ({detail})</div>', unsafe_allow_html=True)
    st.write("")
    st.caption(f"Ver {VERSION}")

# ------------------------------------------------------------------------------
# 📦 【盒子 B：導師中心】
# ------------------------------------------------------------------------------
if is_admin(st.session_state.group_id) and st.session_state.view_mode == "管理後台":
    hc1, hc2 = st.columns([4, 1])
    hc1.markdown("## 🟢 導師中心")
    if hc2.button("🔄 更新資料", use_container_width=True, key="admin_refresh"):
        load_static_data.clear()
        load_dynamic_data.clear()
        st.cache_data.clear()
        st.rerun()

    t1, t2, t3, t4 = st.tabs(["📋 指派任務", "📈 數據監控", "📋 學生名單", "📖 題目講解"])

    with t1:
        # 發布成功後清空表單（在 widget 渲染前執行）
        if st.session_state.pop('t1_clear_form', False):
            for k in ['t1_group', 't1_mode', 't1_stu',
                      't1_inc_q', 't1_inc_reading', 't1_inc_vocab',
                      't1_ref_stu', 't1_ref_logic', 't1_ref_n',
                      't1_v', 't1_u', 't1_y', 't1_b', 't1_l', 't1_start_sent', 't1_q_count',
                      'rt_v', 'rt_u', 'rt_y', 'rt_b', 'rt_l', 'rt_start_sent', 'rt_q_count',
                      'vt_v', 'vt_u', 'vt_y', 'vt_b', 'vt_l', 'vt_start_sent', 'vt_q_count',
                      'vt_mode', 'vt_timer', 'vt_extra']:
                st.session_state.pop(k, None)

        # ══════════════════════════════════════════════════════════════════
        # 區塊一：發布新任務
        # ══════════════════════════════════════════════════════════════════
        st.subheader("📢 發布新任務")

        # ── 基本設定 ──────────────────────────────────────────────────────
        all_groups    = sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique().tolist())
        target_groups = st.multiselect("目標班級/分組（可複選）", all_groups, default=[], key="t1_group")

        # 指派對象：依選取班級合併學生名單
        if target_groups:
            group_members = sorted(df_s[df_s['分組'].isin(target_groups)]['姓名'].tolist())
        else:
            group_members = []

        target_mode = st.radio("指派對象", ["全班", "指定學生"], horizontal=True, key="t1_mode")
        if target_mode == "指定學生":
            target_students_t1 = st.multiselect("選擇學生（可複選）", group_members, default=group_members, key="t1_stu")
        else:
            target_students_t1 = group_members

        # 寫入任務時記錄所有選取班級
        target_group = ",".join(target_groups) if target_groups else ""

        # 開始／結束日期
        dc1, dc2 = st.columns(2)
        now_tw_t1  = get_now()
        date_start = dc1.date_input("📅 開始日期", value=now_tw_t1.date(), key="t1_start")
        date_end   = dc2.date_input("📅 結束日期", value=now_tw_t1.date() + timedelta(days=7), key="t1_end")

        # ── 題目範圍篩選（選填） ──────────────────────────────────────────
        include_q = st.checkbox("📝 加入重組／單選題", value=True, key="t1_inc_q")
        df_t1_final = pd.DataFrame()

        if include_q:
            st.markdown("**⚙️ 重組／單選題範圍**")
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
            total_in_scope = len(df_t1_scope)
            st.caption(f"此範圍共 {total_in_scope} 題")

            sc1, sc2 = st.columns(2)
            all_sent_nums = sorted(df_t1_scope['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0)
            t1_start_sent = sc1.selectbox("🔢 起始句編號", all_sent_nums, key="t1_start_sent") if all_sent_nums else None
            t1_q_count    = sc2.number_input("🔢 題目數量", min_value=0, max_value=total_in_scope, value=total_in_scope, key="t1_q_count")

            if t1_start_sent:
                df_t1_scope['_num'] = pd.to_numeric(df_t1_scope['句編號'], errors='coerce').fillna(0)
                df_t1_scope = df_t1_scope[df_t1_scope['_num'] >= int(t1_start_sent)].sort_values('_num').copy()
            if t1_q_count > 0:
                df_t1_scope = df_t1_scope.head(int(t1_q_count)).copy()
            st.caption(f"篩選後：{len(df_t1_scope)} 題")

            # 參考學生錯題篩選
            st.markdown("**👥 參考學生錯題（選填）**")
            ref_col1, ref_col2, ref_col3 = st.columns(3)
            all_students  = sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['姓名'].tolist())
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
                st.info(f"📊 符合條件：{len(df_t1_final)} 題")
            else:
                df_t1_final = df_t1_scope.copy()
                ref_students = []

            is_mcq_t1    = "單選" in t1u if include_q else False
            title_col_t1 = "單選題目" if is_mcq_t1 else "重組中文題目"
            preview_cols = ['句編號', title_col_t1, '題目ID'] + (['錯誤次數'] if '錯誤次數' in df_t1_final.columns else [])
            df_preview   = df_t1_final[[c for c in preview_cols if c in df_t1_final.columns]].copy()
            df_preview.columns = [c if c != title_col_t1 else '題目' for c in df_preview.columns]
            with st.expander(f"📋 預覽題目清單（{len(df_t1_final)} 題）", expanded=False):
                st.dataframe(df_preview, use_container_width=True)
        else:
            ref_students = []
            t1v = t1u = t1y = t1b = t1l = ""

        st.divider()

        # ── 朗讀題目範圍（選填） ──────────────────────────────────────────
        include_reading = st.checkbox("🎤 加入朗讀題", key="t1_inc_reading")
        df_r_final = pd.DataFrame()

        if include_reading:
            if df_r.empty:
                st.warning("reading 工作表尚無資料，無法加入朗讀題。")
            else:
                df_r2 = df_r.copy()
                if '題目ID' not in df_r2.columns:
                    df_r2['題目ID'] = df_r2.apply(
                        lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                    )
                if '單元' not in df_r2.columns:
                    df_r2['單元'] = '朗讀'

                st.markdown("**⚙️ 朗讀題範圍**")
                rc_ = st.columns(5)
                rv_ = rc_[0].selectbox("版本",  sorted(df_r2['版本'].unique()),  key="rt_v")
                ru_src = df_r2[df_r2['版本'] == rv_]
                ru_ = rc_[1].selectbox("單元",  sorted(ru_src['單元'].unique()),  key="rt_u")
                ry_src = ru_src[ru_src['單元'] == ru_]
                ry_ = rc_[2].selectbox("年度",  sorted(ry_src['年度'].unique()),  key="rt_y")
                rb_src = ry_src[ry_src['年度'] == ry_]
                rb_ = rc_[3].selectbox("冊編號", sorted(rb_src['冊編號'].unique()), key="rt_b")
                rl_src = rb_src[rb_src['冊編號'] == rb_]
                rl_ = rc_[4].selectbox("課編號", sorted(rl_src['課編號'].unique()), key="rt_l")

                df_r_final = rl_src[rl_src['課編號'] == rl_].copy()
                r_total = len(df_r_final)
                st.caption(f"此範圍共 {r_total} 題")

                # 起始句編號 & 題目數量
                rs1, rs2 = st.columns(2)
                r_sent_opts = sorted(df_r_final['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0) if '句編號' in df_r_final.columns else []
                r_start_sent = rs1.selectbox("🔢 起始句編號", r_sent_opts, key="rt_start_sent") if r_sent_opts else None
                r_q_count    = rs2.number_input("🔢 題目數量", min_value=0, max_value=max(r_total, 1), value=r_total, key="rt_q_count")

                # 套用起始句與數量
                if r_start_sent and '句編號' in df_r_final.columns:
                    df_r_final['_num'] = pd.to_numeric(df_r_final['句編號'], errors='coerce').fillna(0)
                    df_r_final = df_r_final[df_r_final['_num'] >= int(r_start_sent)].sort_values('_num').copy()
                if r_q_count > 0:
                    df_r_final = df_r_final.head(int(r_q_count)).copy()
                st.caption(f"篩選後：{len(df_r_final)} 題")

                preview_r_cols = [c for c in ['句編號', '朗讀句子', '英文句子', '題目ID'] if c in df_r_final.columns]
                with st.expander(f"📋 預覽朗讀清單（{len(df_r_final)} 題）", expanded=False):
                    st.dataframe(df_r_final[preview_r_cols], use_container_width=True)

        st.divider()

        # ── 單字重組範圍（選填） ──────────────────────────────────────────
        include_vocab = st.checkbox("🔤 加入單字重組題", key="t1_inc_vocab")
        df_v_final = pd.DataFrame()

        if include_vocab:
            if df_v.empty:
                st.warning("vocab 工作表尚無資料，無法加入單字題。")
            else:
                df_v2 = df_v.copy()
                if '題目ID' not in df_v2.columns:
                    df_v2['題目ID'] = df_v2.apply(
                        lambda r: f"V_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                    )

                st.markdown("**⚙️ 單字題範圍**")
                vc_ = st.columns(5)
                vv_ = vc_[0].selectbox("版本",  sorted(df_v2['版本'].unique()), key="vt_v")
                vu_src = df_v2[df_v2['版本'] == vv_]
                vu_ = vc_[1].selectbox("單元",  sorted(vu_src['單元'].unique()) if '單元' in vu_src.columns else ['單字'], key="vt_u")
                vy_src = vu_src[vu_src['單元'] == vu_] if '單元' in vu_src.columns else vu_src
                vy_ = vc_[2].selectbox("年度",  sorted(vy_src['年度'].unique()), key="vt_y")
                vb_src = vy_src[vy_src['年度'] == vy_]
                vb_ = vc_[3].selectbox("冊編號", sorted(vb_src['冊編號'].unique()), key="vt_b")
                vl_src = vb_src[vb_src['冊編號'] == vb_]
                vl_ = vc_[4].selectbox("課編號", sorted(vl_src['課編號'].unique()), key="vt_l")

                df_v_scope_t1 = vl_src[vl_src['課編號'] == vl_].copy()
                v_total = len(df_v_scope_t1)
                st.caption(f"此範圍共 {v_total} 題")

                vs1, vs2 = st.columns(2)
                v_sent_opts = sorted(df_v_scope_t1['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0) if '句編號' in df_v_scope_t1.columns else []
                vt_start = vs1.selectbox("🔢 起始句編號", v_sent_opts, key="vt_start_sent") if v_sent_opts else None
                vt_count = vs2.number_input("🔢 題目數量", 0, max(v_total, 1), v_total, key="vt_q_count")

                if vt_start and '句編號' in df_v_scope_t1.columns:
                    df_v_scope_t1['_num'] = pd.to_numeric(df_v_scope_t1['句編號'], errors='coerce').fillna(0)
                    df_v_scope_t1 = df_v_scope_t1[df_v_scope_t1['_num'] >= int(vt_start)].sort_values('_num').copy()
                if vt_count > 0:
                    df_v_scope_t1 = df_v_scope_t1.head(int(vt_count)).copy()

                # 難度設定
                vm1, vm2, vm3 = st.columns(3)
                vt_mode  = vm1.selectbox("模式鎖定", ["學生自選", "拆字母", "鍵盤"], key="vt_mode")
                vt_timer = vm2.number_input("限時（秒，0=不限）", 0, 300, 30, key="vt_timer")
                vt_extra = vm3.number_input("干擾字母數", 0, 10, 3, key="vt_extra")

                st.caption(f"篩選後：{len(df_v_scope_t1)} 題")
                df_v_final = df_v_scope_t1.copy()

                preview_v_cols = [c for c in ['句編號', '中文意思', '英文單字', '題目ID'] if c in df_v_final.columns]
                with st.expander(f"📋 預覽單字清單（{len(df_v_final)} 題）", expanded=False):
                    st.dataframe(df_v_final[preview_v_cols], use_container_width=True)

        st.divider()

        # 合計
        total_q = len(df_t1_final) + len(df_r_final) + len(df_v_final)
        st.info(f"📊 本次任務合計：重組/單選 {len(df_t1_final)} 題 ＋ 朗讀 {len(df_r_final)} 題 ＋ 單字 {len(df_v_final)} 題 ＝ **{total_q} 題**")

        if st.button("🚀 確認發布任務", use_container_width=True, type="primary"):
            if not target_groups:
                st.error("❌ 請至少選擇一個目標班級")
            elif not include_q and not include_reading and not include_vocab:
                st.error("❌ 請至少勾選一種題型")
            elif df_t1_final.empty and df_r_final.empty and df_v_final.empty:
                st.error("❌ 目前無符合條件的題目，請調整篩選條件")
            elif not target_students_t1:
                st.error("❌ 請至少選擇一位學生")
            elif date_end < date_start:
                st.error("❌ 結束日期不能早於開始日期")
            else:
                q_ids = df_t1_final['題目ID'].tolist() if (not df_t1_final.empty and '題目ID' in df_t1_final.columns) else []
                r_ids = df_r_final['題目ID'].tolist()  if (not df_r_final.empty  and '題目ID' in df_r_final.columns)  else []
                v_ids = df_v_final['題目ID'].tolist()  if (not df_v_final.empty  and '題目ID' in df_v_final.columns)  else []
                all_ids = q_ids + r_ids + v_ids

                has_q = bool(q_ids)
                has_r = bool(r_ids)
                has_v = bool(v_ids)
                if has_q and not has_r and not has_v:
                    task_type = "一般"
                elif has_r and not has_q and not has_v:
                    task_type = "朗讀"
                elif has_v and not has_q and not has_r:
                    task_type = "單字"
                else:
                    task_type = "混合"

                # vocab 難度設定存入任務
                vocab_cfg = ""
                if has_v:
                    vt_mode_val  = st.session_state.get('vt_mode', '學生自選')
                    vt_timer_val = st.session_state.get('vt_timer', 30)
                    vt_extra_val = st.session_state.get('vt_extra', 3)
                    vocab_cfg = f"{vt_mode_val}|{vt_timer_val}|{vt_extra_val}"

                # 自動產生任務說明摘要
                desc_parts = []
                if q_ids:
                    start_sent_label = f" 起始句{st.session_state.get('t1_start_sent', '')}" if st.session_state.get('t1_start_sent') else ""
                    desc_parts.append(f"重組/單選：{t1v} {t1u} {t1y}年 冊{t1b} 課{t1l}{start_sent_label}，共 {len(q_ids)} 題")
                if r_ids:
                    r_start = st.session_state.get('rt_start_sent', '')
                    r_start_label = f" 起始句{r_start}" if r_start else ""
                    # 取朗讀篩選範圍（若有選的話）
                    rv_ = st.session_state.get('rt_v', '')
                    ru_ = st.session_state.get('rt_u', '')
                    ry_ = st.session_state.get('rt_y', '')
                    rb_ = st.session_state.get('rt_b', '')
                    rl_ = st.session_state.get('rt_l', '')
                    r_scope = f"：{rv_} {ru_} {ry_}年 冊{rb_} 課{rl_}" if rv_ else ""
                    desc_parts.append(f"朗讀{r_scope}{r_start_label}，共 {len(r_ids)} 題")
                if v_ids:
                    v_start = st.session_state.get('vt_start_sent', '')
                    v_start_label = f" 起始句{v_start}" if v_start else ""
                    vv_v = st.session_state.get('vt_v', '')
                    vv_u = st.session_state.get('vt_u', '')
                    vv_y = st.session_state.get('vt_y', '')
                    vv_b = st.session_state.get('vt_b', '')
                    vv_l = st.session_state.get('vt_l', '')
                    v_scope = f"：{vv_v} {vv_u} {vv_y}年 冊{vv_b} 課{vv_l}" if vv_v else ""
                    desc_parts.append(f"單字{v_scope}{v_start_label}，共 {len(v_ids)} 題")
                publish_time = get_now().strftime("%Y-%m-%d-%H:%M")
                teacher_name = st.session_state.user_name
                groups_label = ",".join(target_groups)
                auto_desc = f"{teacher_name}-{publish_time}-{groups_label}-{'；'.join(desc_parts)}"

                new_task  = pd.DataFrame([{
                    "建立時間":   get_now().strftime("%Y-%m-%d %H:%M:%S"),
                    "任務名稱":   auto_desc,
                    "對象班級":   target_group,
                    "指派學生":   ",".join(target_students_t1),
                    "指派人數":   len(target_students_t1),
                    "內容":       f"{t1v}|{t1u}|{t1y}|{t1b}|{t1l}",
                    "任務說明":   "",
                    "單字設定":   vocab_cfg,
                    "題目數":     len(all_ids),
                    "題目ID清單": ",".join(all_ids),
                    "開始日期":   str(date_start),
                    "結束日期":   str(date_end),
                    "參考學生":   ",".join(ref_students) if ref_students else "",
                    "狀態":       "進行中",
                    "類型":       task_type
                }])
                if append_to_sheet("assignments", new_task):
                    st.success(f"✅ 任務已發布！共 {len(all_ids)} 題（重組/單選 {len(df_t1_final)} ＋ 朗讀 {len(df_r_final)}），指派給 {len(target_students_t1)} 位學生")
                    st.session_state['t1_clear_form'] = True
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
                task_stu_str = str(row.get('指派學生', ''))
                task_q_ids   = str(row.get('題目ID清單', ''))
                task_status  = str(row.get('狀態', '進行中'))

                assigned_stus = [s.strip() for s in task_stu_str.split(',') if s.strip()] if task_stu_str else []
                q_ids_set     = set([q.strip() for q in task_q_ids.split(',') if q.strip()]) if task_q_ids else set()
                task_q_count  = len(q_ids_set) if q_ids_set else max(int(float(str(row.get('題目數', 0)) or 0)), 0)
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
                    # 任務說明
                    admin_desc = str(row.get('任務說明', '')).strip()
                    if admin_desc and admin_desc != 'nan':
                        st.info(f"📋 {admin_desc}")

                    ic1, ic2, ic3, ic4 = st.columns(4)
                    ic1.metric("指派人數", assign_count)
                    ic2.metric("已完成", completed)
                    ic3.metric("題目數", task_q_count)
                    ic4.metric("狀態", "🟢 全部完成" if all_done else ("🔴 進行中" if task_status != '已結束' else "⚫ 已結束"))

                    # 各學生完成狀況
                    if assigned_stus and q_ids_set and not df_l.empty and '題目ID' in df_l.columns:
                        st.markdown("**學生完成狀況：**")
                        sc = st.columns(min(len(assigned_stus), 5))
                        for i, stu in enumerate(assigned_stus):
                            stu_done = set(df_l[(df_l['姓名'] == stu) & (~df_l['結果'].str.contains('📖', na=False))]['題目ID'].tolist())
                            done_q   = len(q_ids_set & stu_done)
                            sc[i % 5].markdown(f"{'✅' if q_ids_set.issubset(stu_done) else '🔄'} **{stu}**  \n{done_q}/{task_q_count} 題")

                    st.divider()
                    st.markdown("**✏️ 修改任務內容**")

                    # 任務名稱
                    new_name = st.text_input("任務名稱", value=task_name, key=f"edit_name_{idx}")

                    # 日期
                    ed1, ed2 = st.columns(2)
                    try:
                        cur_start = datetime.strptime(task_start, "%Y-%m-%d").date() if task_start else get_now().date()
                        cur_end   = datetime.strptime(task_end,   "%Y-%m-%d").date() if task_end   else get_now().date() + timedelta(days=7)
                    except:
                        cur_start = get_now().date()
                        cur_end   = get_now().date() + timedelta(days=7)
                    new_start = ed1.date_input("開始日期", value=cur_start, key=f"edit_start_{idx}")
                    new_end   = ed2.date_input("結束日期", value=cur_end,   key=f"edit_end_{idx}")

                    # 學生（可刪除）
                    st.markdown("**👥 指派學生（取消勾選即移除）**")
                    all_stu_pool = sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['姓名'].tolist())
                    new_stus = st.multiselect(
                        "學生名單", all_stu_pool,
                        default=[s for s in assigned_stus if s in all_stu_pool],
                        key=f"edit_stus_{idx}"
                    )

                    if st.button("💾 儲存修改", key=f"save_task_{idx}", type="primary", use_container_width=True):
                        if new_end < new_start:
                            st.error("❌ 結束日期不能早於開始日期")
                        elif not new_stus:
                            st.error("❌ 請至少保留一位學生")
                        else:
                            try:
                                df_a_edit = conn.read(worksheet="assignments", ttl=0)
                                df_a_edit.at[idx, '任務名稱'] = new_name.strip()
                                df_a_edit.at[idx, '開始日期'] = str(new_start)
                                df_a_edit.at[idx, '結束日期'] = str(new_end)
                                df_a_edit.at[idx, '指派學生'] = ",".join(new_stus)
                                df_a_edit.at[idx, '指派人數'] = len(new_stus)
                                conn.update(worksheet="assignments", data=df_a_edit)
                                load_dynamic_data.clear()
                                st.success("✅ 任務已更新")
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

            group_opts = ["不限"] + sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique().tolist())
            sel_group  = fc2.selectbox("👥 群組", group_opts, key="log_group")

            stu_pool = (
                sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['姓名'].tolist())
                if sel_group == "不限"
                else sorted(df_s[df_s['分組'] == sel_group]['姓名'].tolist())
            )
            sel_stu    = fc3.selectbox("👤 學生", ["不限"] + stu_pool, key="log_stu")
            sel_result = fc4.selectbox("📋 結果", ["全部", "✅ 正確", "❌ 錯誤", "📖 講解", "🎤 朗讀"], key="log_result")

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
                result_map = {"✅ 正確": "✅", "❌ 錯誤": "❌", "📖 講解": "📖 講解", "🎤 朗讀": "🎤 朗讀"}
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

        # ── 篩選 ──────────────────────────────────────────────────────────
        sa1, sa2 = st.columns(2)
        s_group_filter = sa1.selectbox(
            "班級/分組",
            ["全部"] + sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique().tolist()),
            key="t3_sgroup"
        )
        s_name_filter = sa2.text_input("🔍 姓名搜尋", placeholder="輸入姓名關鍵字", key="t3_sname")

        # 套用篩選
        df_s_show = df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])].copy()
        if s_group_filter != "全部":
            df_s_show = df_s_show[df_s_show['分組'] == s_group_filter]
        if s_name_filter.strip():
            df_s_show = df_s_show[df_s_show['姓名'].str.contains(s_name_filter.strip(), na=False)]

        # 帳號、密碼補零至4位，並移除無名欄位
        df_s_display = df_s_show.copy()
        # 移除 Unnamed 欄位
        df_s_display = df_s_display[[c for c in df_s_display.columns if not str(c).startswith('Unnamed')]]
        for col in ['帳號', '密碼']:
            if col in df_s_display.columns:
                df_s_display[col] = df_s_display[col].apply(
                    lambda v: str(v).split('.')[0].strip().zfill(4) if str(v).split('.')[0].strip().isdigit() else str(v)
                )

        st.caption(f"共 {len(df_s_display)} 位學生")
        st.dataframe(df_s_display.reset_index(drop=True), use_container_width=True)

        st.divider()
        st.subheader("🎤 朗讀紀錄明細")

        # ── 篩選條件 ──────────────────────────────────────────────────────
        f1, f2, f3 = st.columns(3)

        # 班級
        t3_group = f1.selectbox(
            "👥 班級",
            ["全部"] + sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique().tolist()),
            key="t3_rgroup"
        )
        if t3_group == "全部":
            t3_pool = sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['姓名'].tolist())
        else:
            t3_pool = sorted(df_s[df_s['分組'] == t3_group]['姓名'].tolist())

        # 姓名搜尋
        t3_name = f2.text_input("🔍 姓名搜尋", placeholder="輸入姓名關鍵字", key="t3_name")

        # 時間
        now_t3   = get_now()
        t3_time  = f3.selectbox("🕐 時間範圍", ["全部", "今日", "本週", "本月", "自訂"], key="t3_time")
        if t3_time == "今日":
            t3_from, t3_to = now_t3.date(), now_t3.date()
        elif t3_time == "本週":
            t3_from = (now_t3 - timedelta(days=now_t3.weekday())).date()
            t3_to   = now_t3.date()
        elif t3_time == "本月":
            t3_from = now_t3.date().replace(day=1)
            t3_to   = now_t3.date()
        elif t3_time == "自訂":
            dc1, dc2 = st.columns(2)
            t3_from = dc1.date_input("起始日", value=now_t3.date() - timedelta(days=7), key="t3_from")
            t3_to   = dc2.date_input("結束日", value=now_t3.date(), key="t3_to")
        else:
            t3_from, t3_to = None, None

        # 題目範圍
        st.markdown("**⚙️ 題目範圍（選填）**")
        qc = st.columns(5)
        t3_v_opts = ["全部"] + sorted(df_r['版本'].unique().tolist()) if not df_r.empty else ["全部"]
        t3_v = qc[0].selectbox("版本", t3_v_opts, key="t3_v")
        t3_u_src  = df_r[df_r['版本'] == t3_v] if (not df_r.empty and t3_v != "全部") else df_r
        t3_u_opts = ["全部"] + sorted(t3_u_src['單元'].unique().tolist()) if not df_r.empty else ["全部"]
        t3_u = qc[1].selectbox("單元", t3_u_opts, key="t3_u")
        t3_y_src  = t3_u_src[t3_u_src['單元'] == t3_u] if t3_u != "全部" else t3_u_src
        t3_y_opts = ["全部"] + sorted(t3_y_src['年度'].unique().tolist()) if not df_r.empty else ["全部"]
        t3_y = qc[2].selectbox("年度", t3_y_opts, key="t3_y")
        t3_b_src  = t3_y_src[t3_y_src['年度'] == t3_y] if t3_y != "全部" else t3_y_src
        t3_b_opts = ["全部"] + sorted(t3_b_src['冊編號'].unique().tolist()) if not df_r.empty else ["全部"]
        t3_b = qc[3].selectbox("冊編號", t3_b_opts, key="t3_b")
        t3_l_src  = t3_b_src[t3_b_src['冊編號'] == t3_b] if t3_b != "全部" else t3_b_src
        t3_l_opts = ["全部"] + sorted(t3_l_src['課編號'].unique().tolist()) if not df_r.empty else ["全部"]
        t3_l = qc[4].selectbox("課次", t3_l_opts, key="t3_l")

        # ── 套用篩選 ──────────────────────────────────────────────────────
        # 姓名過濾
        if t3_name.strip():
            t3_pool = [n for n in t3_pool if t3_name.strip() in n]

        if not df_l.empty and '題目ID' in df_l.columns:
            reading_logs = df_l[
                (df_l['姓名'].isin(t3_pool)) &
                (df_l['結果'] == '🎤 朗讀')
            ].copy()
            reading_logs['時間_dt'] = pd.to_datetime(reading_logs['時間'], errors='coerce')

            if t3_from:
                reading_logs = reading_logs[reading_logs['時間_dt'].dt.date >= t3_from]
                reading_logs = reading_logs[reading_logs['時間_dt'].dt.date <= t3_to]

            # 題目範圍：R_版本_年度_冊編號_單元_課編號_句編號
            if t3_v != "全部":
                reading_logs = reading_logs[reading_logs['題目ID'].str.contains(f"_{t3_v}_", na=False) | reading_logs['題目ID'].str.startswith(f"R_{t3_v}_", na=False)]
            if t3_b != "全部":
                reading_logs = reading_logs[reading_logs['題目ID'].str.contains(f"_{t3_b}_", na=False)]
            if t3_l != "全部":
                reading_logs = reading_logs[reading_logs['題目ID'].str.contains(f"_{t3_l}_", na=False)]

            reading_logs = reading_logs.sort_values('時間', ascending=False).drop(columns=['時間_dt'], errors='ignore')
        else:
            reading_logs = pd.DataFrame()

        st.caption(f"共 {len(reading_logs)} 筆紀錄")

        if reading_logs.empty:
            st.info("無符合條件的朗讀紀錄。")
        else:
            for stu in t3_pool:
                stu_logs = reading_logs[reading_logs['姓名'] == stu]
                if stu_logs.empty:
                    continue
                with st.expander(f"👤 {stu}　共 {len(stu_logs)} 筆", expanded=False):
                    display_cols = [c for c in ['時間', '題目ID', '學生答案', '分數'] if c in stu_logs.columns]
                    st.dataframe(stu_logs[display_cols].reset_index(drop=True), use_container_width=True)

    # --------------------------------------------------------------------------
    # 🆕 【Tab 4：題目講解】
    # --------------------------------------------------------------------------
    with t4:
        st.subheader("📖 題目講解")

        rev4_tab1, rev4_tab2 = st.tabs(["📝 重組／單選", "🎤 朗讀"])

        # ── 重組／單選講解 ────────────────────────────────────────────────
        with rev4_tab1:
            rev_group = st.selectbox(
                "👥 班級/分組",
                sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique()),
                key="rev_group"
            )
            students_in_group = sorted(df_s[df_s['分組'] == rev_group]['姓名'].tolist())

            # 任務篩選
            rev_task_ids     = None
            task_stu_default = students_in_group
            if not df_a.empty and '任務名稱' in df_a.columns:
                df_a_rev = df_a[
                    (df_a.get('狀態', pd.Series(dtype=str)).fillna('') != '已刪除') &
                    (df_a.get('類型',  pd.Series(dtype=str)).fillna('').isin(['一般', '混合', '']))
                ].copy()
                # 依班級過濾任務（減少選項數量）
                if not df_a_rev.empty and '對象班級' in df_a_rev.columns:
                    df_a_rev = df_a_rev[df_a_rev['對象班級'].str.contains(rev_group, na=False)]
                task_names = ["（不限）"] + df_a_rev['任務名稱'].tolist()
                sel_task = st.selectbox("📋 依任務篩選（選填）", task_names, key="rev_task")
                if sel_task != "（不限）":
                    task_row = df_a_rev[df_a_rev['任務名稱'] == sel_task].iloc[0]
                    ids_str  = str(task_row.get('題目ID清單', '') or '')
                    rev_task_ids = set([q.strip() for q in ids_str.split(',') if q.strip() and q.strip() != 'nan'])
                    content_str  = str(task_row.get('內容', ''))
                    parts = [p.strip() for p in content_str.split('|')]
                    if len(parts) == 5:
                        st.info(f"📋 {sel_task}　共 {len(rev_task_ids)} 題")
                        st.session_state['rev_v'] = parts[0]
                        st.session_state['rev_u'] = parts[1]
                        st.session_state['rev_y'] = parts[2]
                        st.session_state['rev_b'] = parts[3]
                        st.session_state['rev_l'] = parts[4]
                    stu_str = str(task_row.get('指派學生', '') or '')
                    task_stus = [s.strip() for s in stu_str.split(',') if s.strip()]
                    task_stu_default = [s for s in task_stus if s in students_in_group] or students_in_group
                else:
                    for k in ['rev_v','rev_u','rev_y','rev_b','rev_l']:
                        st.session_state.pop(k, None)

            rev_students = st.multiselect(
                "👤 學生（預設全選，可自由增刪）",
                options=students_in_group,
                default=task_stu_default,
                key="rev_students"
            )
            target_students = rev_students if rev_students else students_in_group

            def _rev_idx(opts, key):
                val = st.session_state.get(key)
                try: return opts.index(val) if val in opts else 0
                except: return 0

            st.markdown("**⚙️ 題目範圍**")
            rc = st.columns(5)
            rv_opts = sorted(df_q['版本'].unique())
            rv = rc[0].selectbox("版本", rv_opts, index=_rev_idx(rv_opts,'rev_v'), key="rev_v")
            ru_opts = sorted(df_q[df_q['版本'] == rv]['單元'].unique())
            ru = rc[1].selectbox("單元", ru_opts, index=_rev_idx(ru_opts,'rev_u'), key="rev_u")
            ry_opts = sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru)]['年度'].unique())
            ry = rc[2].selectbox("年度", ry_opts, index=_rev_idx(ry_opts,'rev_y'), key="rev_y")
            rb_opts = sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru) & (df_q['年度'] == ry)]['冊編號'].unique())
            rb = rc[3].selectbox("冊別", rb_opts, index=_rev_idx(rb_opts,'rev_b'), key="rev_b")
            rl_opts = sorted(df_q[(df_q['版本'] == rv) & (df_q['單元'] == ru) & (df_q['年度'] == ry) & (df_q['冊編號'] == rb)]['課編號'].unique())
            rl = rc[4].selectbox("課次", rl_opts, index=_rev_idx(rl_opts,'rev_l'), key="rev_l")

            df_rev_scope = df_q[
                (df_q['版本'] == rv) & (df_q['單元'] == ru) &
                (df_q['年度'] == ry) & (df_q['冊編號'] == rb) &
                (df_q['課編號'] == rl)
            ].copy()
            df_rev_scope['題目ID'] = df_rev_scope.apply(
                lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
            )
            if rev_task_ids:
                df_rev_scope = df_rev_scope[df_rev_scope['題目ID'].isin(rev_task_ids)].copy()


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

        # ── 朗讀講解 ──────────────────────────────────────────────────────
        with rev4_tab2:
            rrev_group = st.selectbox(
                "👥 班級/分組",
                sorted(df_s[~df_s['分組'].isin(['ADMIN','TEACHER'])]['分組'].unique()),
                key="rrev_group"
            )
            rrev_stus_pool = sorted(df_s[df_s['分組'] == rrev_group]['姓名'].tolist())

            # 任務篩選
            rrev_task_ids    = None
            rrev_stu_default = rrev_stus_pool
            if not df_a.empty and '任務名稱' in df_a.columns:
                df_a_rrev = df_a[
                    (df_a.get('狀態', pd.Series(dtype=str)).fillna('') != '已刪除') &
                    (df_a.get('類型',  pd.Series(dtype=str)).fillna('').isin(['朗讀', '混合']))
                ].copy()
                # 依班級過濾任務
                if not df_a_rrev.empty and '對象班級' in df_a_rrev.columns:
                    df_a_rrev = df_a_rrev[df_a_rrev['對象班級'].str.contains(rrev_group, na=False)]
                rrev_task_names = ["（不限）"] + df_a_rrev['任務名稱'].tolist()
                sel_rrev_task = st.selectbox("📋 依任務篩選（選填）", rrev_task_names, key="rrev_task")
                if sel_rrev_task != "（不限）":
                    rrev_task_row = df_a_rrev[df_a_rrev['任務名稱'] == sel_rrev_task].iloc[0]
                    rrev_ids_str  = str(rrev_task_row.get('題目ID清單', '') or '')
                    rrev_task_ids = set([q.strip() for q in rrev_ids_str.split(',') if q.strip() and q.strip() != 'nan'])
                    st.info(f"📋 {sel_rrev_task}　共 {len(rrev_task_ids)} 題")
                    rrev_stu_str   = str(rrev_task_row.get('指派學生', '') or '')
                    rrev_task_stus = [s.strip() for s in rrev_stu_str.split(',') if s.strip()]
                    rrev_stu_default = [s for s in rrev_task_stus if s in rrev_stus_pool] or rrev_stus_pool

            rrev_students = st.multiselect(
                "👤 學生（預設全選）",
                options=rrev_stus_pool,
                default=rrev_stu_default,
                key="rrev_students"
            )
            rrev_targets = rrev_students if rrev_students else rrev_stus_pool

            if df_r.empty:
                st.info("reading 工作表尚無資料。")
            else:
                df_r2 = df_r.copy()
                if '題目ID' not in df_r2.columns:
                    df_r2['題目ID'] = df_r2.apply(
                        lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                    )

                st.markdown("**⚙️ 朗讀題目範圍**")
                rrc = st.columns(5)
                rrv = rrc[0].selectbox("版本",  sorted(df_r2['版本'].unique()), key="rrev_v")
                rru_src = df_r2[df_r2['版本'] == rrv]
                rru = rrc[1].selectbox("單元",  sorted(rru_src['單元'].unique()) if '單元' in rru_src.columns else ['朗讀'], key="rrev_u")
                rry_src = rru_src[rru_src['單元'] == rru] if '單元' in rru_src.columns else rru_src
                rry = rrc[2].selectbox("年度",  sorted(rry_src['年度'].unique()), key="rrev_y")
                rrb_src = rry_src[rry_src['年度'] == rry]
                rrb = rrc[3].selectbox("冊別",  sorted(rrb_src['冊編號'].unique()), key="rrev_b")
                rrl_src = rrb_src[rrb_src['冊編號'] == rrb]
                rrl = rrc[4].selectbox("課次",  sorted(rrl_src['課編號'].unique()), key="rrev_l")

                df_rrev_scope = rrl_src[rrl_src['課編號'] == rrl].copy()
                if rrev_task_ids:
                    df_rrev_scope = df_rrev_scope[df_rrev_scope['題目ID'].isin(rrev_task_ids)].copy()


                if df_rrev_scope.empty:
                    st.info("此範圍尚無朗讀題目。")
                else:
                    st.markdown(f"**📋 共 {len(df_rrev_scope)} 題**")

                    # 取得目標學生朗讀 log
                    if not df_l.empty and '題目ID' in df_l.columns:
                        rrev_logs = df_l[
                            (df_l['姓名'].isin(rrev_targets)) &
                            (df_l['結果'] == '🎤 朗讀')
                        ].sort_values('時間', ascending=False).copy()
                    else:
                        rrev_logs = pd.DataFrame()

                    for _, qrow in df_rrev_scope.iterrows():
                        qid       = qrow['題目ID']
                        read_text = str(qrow.get('朗讀句子') or qrow.get('英文句子') or '').strip()

                        # 各學生最近一次分數
                        stu_tags = []
                        for stu in rrev_targets:
                            stu_rows_r = rrev_logs[rrev_logs['姓名'] == stu] if not rrev_logs.empty else pd.DataFrame()
                            stu_q_rows = stu_rows_r[stu_rows_r['題目ID'] == qid] if not stu_rows_r.empty else pd.DataFrame()
                            if stu_q_rows.empty:
                                stu_tags.append(f"{stu}：未作答")
                            else:
                                last_score = stu_q_rows.iloc[0].get('分數', '—')
                                stu_tags.append(f"{stu}：{last_score}分")

                        label = f"句 {qrow.get('句編號','')}｜{read_text[:20]}{'…' if len(read_text)>20 else ''}　　{'　|　'.join(stu_tags)}"

                        with st.expander(label):
                            st.markdown(
                                f"<div style='font-size:1.2rem; font-weight:600; padding:8px 0;'>{read_text}</div>",
                                unsafe_allow_html=True
                            )
                            st.divider()

                            # 講解完成按鈕
                            rrev_btn = f"rrev_done_{qid}"
                            if st.button("📖 講解完成，寫入紀錄", key=rrev_btn, type="primary", use_container_width=True):
                                now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
                                rows_r  = [{"時間": now_str, "姓名": stu, "分組": rrev_group,
                                            "題目ID": qid, "結果": "📖 講解", "學生答案": ""} for stu in rrev_targets]
                                if append_to_sheet("logs", pd.DataFrame(rows_r)):
                                    st.success(f"✅ 已為 {len(rrev_targets)} 位學生寫入講解紀錄！")
                                    load_dynamic_data.clear()
                                    st.rerun()

                            st.markdown("---")
                            st.markdown("**👥 學生朗讀歷史分數**")
                            for stu in rrev_targets:
                                stu_rows_r = rrev_logs[rrev_logs['姓名'] == stu] if not rrev_logs.empty else pd.DataFrame()
                                stu_q_rows = stu_rows_r[stu_rows_r['題目ID'] == qid] if not stu_rows_r.empty else pd.DataFrame()
                                if stu_q_rows.empty:
                                    st.markdown(f"　👤 **{stu}**：尚未朗讀")
                                else:
                                    lines = []
                                    for _, r in stu_q_rows.iterrows():
                                        sc    = r.get('分數', '—')
                                        t_str = str(r.get('時間', ''))[:16]
                                        lines.append(f"{sc}分 _{t_str}_")
                                    st.markdown(f"　👤 **{stu}**：" + "　／　".join(lines))

    show_version_caption()
    st.stop()

# ------------------------------------------------------------------------------
# 📦 【盒子 C：練習範圍設定】
# ------------------------------------------------------------------------------
if not st.session_state.quiz_loaded:

    # ══════════════════════════════════════════════════════════════════════
    # 🆕 學生任務列表（登入後優先顯示）
    # ══════════════════════════════════════════════════════════════════════
    user_name = st.session_state.user_name
    today_dt  = get_now().date()

    # 找出指派給這位學生、未刪除、日期有效的任務
    my_tasks = []
    debug_info = []  # 除錯用
    if not df_a.empty:
        for _, arow in df_a.iterrows():
            task_n = str(arow.get('任務名稱', ''))
            # 過濾已刪除
            if str(arow.get('狀態', '')).strip() == '已刪除':
                debug_info.append(f"❌ {task_n}：已刪除")
                continue

            # 確認學生在指派名單中
            stu_str  = str(arow.get('指派學生', '') or arow.get('對象', '') or '')
            assigned = [s.strip() for s in stu_str.split(',') if s.strip()]
            if user_name not in assigned:
                debug_info.append(f"❌ {task_n}：學生不在名單（名單：{stu_str[:50]}）")
                continue

            # 日期範圍檢查
            try:
                end_str = str(arow.get('結束日期', '')).strip()
                if not end_str or end_str == 'nan':
                    debug_info.append(f"❌ {task_n}：無結束日期")
                    continue
                t_end = datetime.strptime(end_str, "%Y-%m-%d").date()
                if t_end < today_dt:
                    debug_info.append(f"❌ {task_n}：已過期（{end_str}）")
                    continue
            except Exception as e:
                debug_info.append(f"❌ {task_n}：日期格式錯誤（{e}）")
                continue

            debug_info.append(f"✅ {task_n}：符合條件")
            # 題目ID清單必須有資料才顯示
            task_ids_str = str(arow.get('題目ID清單', '') or '')
            valid_ids = [q.strip() for q in task_ids_str.split(',') if q.strip() and q.strip() != 'nan']
            if not valid_ids:
                debug_info.append(f"⚠️ {task_n}：符合條件但題目ID清單為空，不顯示")
                continue
            my_tasks.append(arow)

    if my_tasks:
        st.markdown("## 📋 我的任務")
        for arow in my_tasks:
            task_name    = arow.get('任務名稱', '未命名')
            task_start   = arow.get('開始日期', '')
            task_end     = arow.get('結束日期', '')
            task_q_ids   = str(arow.get('題目ID清單', '') or '')
            # 過濾掉 nan 和空白
            q_ids_set    = set([q.strip() for q in task_q_ids.split(',') if q.strip() and q.strip() != 'nan'])
            task_q_count = len(q_ids_set) if q_ids_set else max(int(float(str(arow.get('題目數', 0) or 0))), 0)

            # 計算個人完成進度（混合任務：一般題答對 + 朗讀題有紀錄）
            task_type       = str(arow.get('類型', '一般'))
            is_reading_task = task_type == '朗讀'
            is_vocab_task   = task_type == '單字'
            is_mixed_task   = task_type == '混合'

            if q_ids_set and not df_l.empty and '題目ID' in df_l.columns:
                # 一般題完成：答對 ✅
                my_correct = set(df_l[(df_l['姓名'] == user_name) & (df_l['結果'] == '✅')]['題目ID'].tolist())
                # 朗讀題完成：有朗讀紀錄 🎤
                my_reading = set(df_l[(df_l['姓名'] == user_name) & (df_l['結果'] == '🎤 朗讀')]['題目ID'].tolist())
                my_done    = my_correct | my_reading
                done_cnt   = len(q_ids_set & my_done)
                all_done   = q_ids_set.issubset(my_done)
            else:
                my_done = set()
                done_cnt, all_done = 0, False

            status_icon = "🟢" if all_done else ("🎤" if is_reading_task else "🔴")
            date_info   = f"{task_start} ～ {task_end}" if task_start else ""

            with st.expander(f"{status_icon} {task_name}　{date_info}　{done_cnt}/{task_q_count} 題完成", expanded=not all_done):
                # 任務說明
                task_desc_text = str(arow.get('任務說明', '')).strip()
                if task_desc_text and task_desc_text != 'nan':
                    st.info(f"📋 {task_desc_text}")

                pc1, pc2 = st.columns(2)
                pc1.metric("總題數", task_q_count)
                pc2.metric("已完成", done_cnt)

                if all_done:
                    st.success("🎉 此任務已全部完成！")
                    # 再次練習按鈕（載入全部任務題目）
                    retry_key = f"retry_task_{task_name}"
                    if st.button("🔁 再次練習（全部題目）", key=retry_key, use_container_width=True):
                        if is_reading_task:
                            df_r2 = df_r.copy()
                            if '題目ID' not in df_r2.columns:
                                df_r2['題目ID'] = df_r2.apply(
                                    lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                                )
                            retry_r = df_r2[df_r2['題目ID'].isin(q_ids_set)].copy()
                            if not retry_r.empty:
                                records = retry_r.to_dict('records')
                                for rec in records:
                                    rec['_type'] = 'reading'
                                st.session_state.update({
                                    "quiz_list": records,
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()
                        else:
                            df_q2 = df_q.copy()
                            df_q2['題目ID'] = df_q2.apply(
                                lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
                            )
                            retry_q = df_q2[df_q2['題目ID'].isin(q_ids_set)].copy()
                            if not retry_q.empty:
                                st.session_state.update({
                                    "quiz_list": retry_q.to_dict('records'),
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()
                else:
                    task_content = str(arow.get('內容', ''))
                    parts        = [p.strip() for p in task_content.split('|')]
                    can_preload  = len(parts) == 5

                    btn_key = f"start_task_{task_name}"
                    label   = f"🚀 進入練習（剩餘 {task_q_count - done_cnt} 題）"

                    if st.button(label, key=btn_key, type="primary", use_container_width=True):
                        pending_ids = q_ids_set - my_done

                        if is_reading_task:
                            df_r2 = df_r.copy()
                            if '題目ID' not in df_r2.columns:
                                df_r2['題目ID'] = df_r2.apply(
                                    lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                                )
                            pending = df_r2[df_r2['題目ID'].isin(pending_ids)].copy()
                            if not pending.empty:
                                records = pending.to_dict('records')
                                for r in records:
                                    r['_type'] = 'reading'
                                st.session_state.update({
                                    "quiz_list": records,
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()

                        elif is_vocab_task:
                            # 純單字任務
                            df_v2 = df_v.copy() if not df_v.empty else pd.DataFrame()
                            if not df_v2.empty and '題目ID' not in df_v2.columns:
                                df_v2['題目ID'] = df_v2.apply(
                                    lambda r: f"V_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                                )
                            pending = df_v2[df_v2['題目ID'].isin(pending_ids)].copy() if not df_v2.empty else pd.DataFrame()
                            if not pending.empty:
                                vocab_cfg_str = str(arow.get('單字設定', '') or '')
                                vcfg = vocab_cfg_str.split('|') if vocab_cfg_str else []
                                v_mode_t  = vcfg[0] if len(vcfg) > 0 else '自選'
                                if v_mode_t == '學生自選':
                                    v_mode_t = '自選'
                                v_timer_t = int(vcfg[1]) if len(vcfg) > 1 else 30
                                v_extra_t = int(vcfg[2]) if len(vcfg) > 2 else 3
                                records = pending.to_dict('records')
                                for rec in records:
                                    rec['_type']        = 'vocab'
                                    rec['_vocab_mode']  = v_mode_t
                                    rec['_vocab_timer'] = v_timer_t
                                    rec['_vocab_extra'] = v_extra_t
                                st.session_state.update({
                                    "quiz_list": records,
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()

                        elif is_mixed_task:
                            df_q2 = df_q.copy()
                            df_q2['題目ID'] = df_q2.apply(
                                lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
                            )
                            df_r2 = df_r.copy() if not df_r.empty else pd.DataFrame()
                            if not df_r2.empty and '題目ID' not in df_r2.columns:
                                df_r2['題目ID'] = df_r2.apply(
                                    lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                                )
                            df_v2 = df_v.copy() if not df_v.empty else pd.DataFrame()
                            if not df_v2.empty and '題目ID' not in df_v2.columns:
                                df_v2['題目ID'] = df_v2.apply(
                                    lambda r: f"V_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                                )
                            pending_q = df_q2[df_q2['題目ID'].isin(pending_ids)].copy()
                            pending_r = df_r2[df_r2['題目ID'].isin(pending_ids)].copy() if not df_r2.empty else pd.DataFrame()
                            pending_v = df_v2[df_v2['題目ID'].isin(pending_ids)].copy() if not df_v2.empty else pd.DataFrame()
                            if not pending_r.empty:
                                pending_r['_type'] = 'reading'
                            if not pending_v.empty:
                                vocab_cfg_str = str(arow.get('單字設定', '') or '')
                                vcfg = vocab_cfg_str.split('|') if vocab_cfg_str else []
                                v_mode_mixed = vcfg[0] if len(vcfg) > 0 else '自選'
                                if v_mode_mixed == '學生自選':
                                    v_mode_mixed = '自選'
                                pending_v['_type']        = 'vocab'
                                pending_v['_vocab_mode']  = v_mode_mixed
                                pending_v['_vocab_timer'] = int(vcfg[1]) if len(vcfg) > 1 else 30
                                pending_v['_vocab_extra'] = int(vcfg[2]) if len(vcfg) > 2 else 3
                            pending = pd.concat([pending_q, pending_r, pending_v], ignore_index=True)
                            if not pending.empty:
                                st.session_state.update({
                                    "quiz_list": pending.to_dict('records'),
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()

                        elif can_preload:
                            # 一般任務：直接從 df_q 取出未完成題目載入
                            df_q2 = df_q.copy()
                            df_q2['題目ID'] = df_q2.apply(
                                lambda r: f"{r['版本']}_{r['年度']}_{r['冊編號']}_{r['單元']}_{r['課編號']}_{r['句編號']}", axis=1
                            )
                            pending_q = df_q2[df_q2['題目ID'].isin(pending_ids)].copy()
                            if not pending_q.empty:
                                st.session_state.update({
                                    "quiz_list": pending_q.to_dict('records'),
                                    "q_idx": 0, "quiz_loaded": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()
                            else:
                                # fallback：進盒子 C 預帶範圍
                                st.session_state.update({
                                    "s_v": parts[0], "s_u": parts[1],
                                    "s_y": parts[2], "s_b": parts[3], "s_l": parts[4],
                                    "task_q_ids": list(pending_ids),
                                    "range_confirmed": True,
                                    "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                                })
                                st.rerun()

                        else:
                            # 無法預帶：進盒子 C 讓學生自選
                            st.session_state.update({
                                "task_q_ids": list(pending_ids),
                                "range_confirmed": False,
                                "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                            })
                            st.rerun()


        st.divider()

    # 除錯：讓管理員看到原始 assignments 資料
    if not df_a.empty and is_admin(st.session_state.group_id):
        with st.expander("🔍 除錯：assignments 原始資料（僅管理員可見）", expanded=False):
            st.dataframe(df_a, use_container_width=True)
            st.write(f"今日：{today_dt} | 學生：{user_name} | 共 {len(my_tasks)} 個有效任務")

    # ══════════════════════════════════════════════════════════════════════
    # 原本的自由練習區（盒子 C）
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("## 🟡 練習範圍設定")

    # 從任務帶入的預設值
    def _idx(options, key, fallback=0):
        val = st.session_state.get(key, None)
        try:
            return options.index(val) if val in options else fallback
        except:
            return fallback

    tab_q, tab_r, tab_v = st.tabs(["📝 重組／單選", "🎤 朗讀", "🔤 單字重組"])

    # ── Tab：重組／單選 ───────────────────────────────────────────────────
    with tab_q:
        with st.expander("⚙️ 篩選題目範圍", expanded=not st.session_state.range_confirmed):
            sv_opts = sorted(df_q['版本'].unique())
            sv = st.selectbox("版本", sv_opts, index=_idx(sv_opts, 's_v'), key="s_v")
            su_opts = sorted(df_q[df_q['版本'] == sv]['單元'].unique())
            su = st.selectbox("單元", su_opts, index=_idx(su_opts, 's_u'), key="s_u")
            sy_opts = sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su)]['年度'].unique())
            sy = st.selectbox("年度", sy_opts, index=_idx(sy_opts, 's_y'), key="s_y")
            sb_opts = sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su) & (df_q['年度'] == sy)]['冊編號'].unique())
            sb = st.selectbox("冊別", sb_opts, index=_idx(sb_opts, 's_b'), key="s_b")
            sl_opts = sorted(df_q[(df_q['版本'] == sv) & (df_q['單元'] == su) & (df_q['年度'] == sy) & (df_q['冊編號'] == sb)]['課編號'].unique())
            sl = st.selectbox("課次", sl_opts, index=_idx(sl_opts, 's_l'), key="s_l")

            if st.button("🔍 確認範圍", use_container_width=True):
                st.session_state.range_confirmed = True
                st.session_state.pop('task_q_ids', None)
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

            task_q_ids = st.session_state.get('task_q_ids', None)
            if task_q_ids:
                df_scope = df_scope[df_scope['題目ID'].isin(task_q_ids)].copy()
                st.info(f"📋 任務模式（共 {len(df_scope)} 題）")

            q_mode = st.radio("🎯 模式：", ["1. 起始句", "2. 未練習", "3. 錯題"], horizontal=True, key="q_mode")
            all_sentences = sorted(df_scope['句編號'].unique(), key=lambda x: int(x) if str(x).isdigit() else 0)
            start_q = st.selectbox("起始句編號", all_sentences, key="q_start")
            nu_i    = st.number_input("題目數量", 1, 100, 10, key="q_nu")

            if "1." in q_mode:
                df_scope['_num'] = pd.to_numeric(df_scope['句編號'], errors='coerce').fillna(0)
                df_final = df_scope[df_scope['_num'] >= int(start_q)].sort_values('_num').copy()
            elif "2." in q_mode:
                done_ids = df_l[df_l['姓名'] == st.session_state.user_name]['題目ID'].unique() if not df_l.empty else []
                df_final = df_scope[~df_scope['題目ID'].isin(done_ids)].copy()
            else:
                wrong_ids = df_l[(df_l['姓名'] == st.session_state.user_name) & (df_l['結果'].str.contains('❌', na=False))]['題目ID'].unique() if not df_l.empty else []
                df_final  = df_scope[df_scope['題目ID'].isin(wrong_ids)].copy()

            st.caption(f"共 {len(df_final)} 題符合條件")

            if st.button("🚀 開始練習", type="primary", use_container_width=True):
                if not df_final.empty:
                    st.session_state.update({
                        "quiz_list": df_final.head(int(nu_i)).to_dict('records'),
                        "q_idx": 0, "quiz_loaded": True,
                        "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                    })
                    st.rerun()
                else:
                    st.error("❌ 無符合題目，請重新選擇")

    # ── Tab：朗讀 ─────────────────────────────────────────────────────────
    with tab_r:
        if df_r.empty:
            st.info("朗讀題庫尚無資料。")
        else:
            df_r2 = df_r.copy()
            if '題目ID' not in df_r2.columns:
                df_r2['題目ID'] = df_r2.apply(
                    lambda r: f"R_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                )
            df_r2['單元'] = df_r2['單元'].fillna('朗讀') if '單元' in df_r2.columns else '朗讀'

            with st.expander("⚙️ 篩選朗讀範圍", expanded=True):
                rr_v = st.selectbox("版本", sorted(df_r2['版本'].unique()), key="r_v")
                rr_u_src = df_r2[df_r2['版本'] == rr_v]
                rr_u = st.selectbox("單元", sorted(rr_u_src['單元'].unique()), key="r_u")
                rr_y_src = rr_u_src[rr_u_src['單元'] == rr_u]
                rr_y = st.selectbox("年度", sorted(rr_y_src['年度'].unique()), key="r_y")
                rr_b_src = rr_y_src[rr_y_src['年度'] == rr_y]
                rr_b = st.selectbox("冊別", sorted(rr_b_src['冊編號'].unique()), key="r_b")
                rr_l_src = rr_b_src[rr_b_src['冊編號'] == rr_b]
                rr_l = st.selectbox("課次", sorted(rr_l_src['課編號'].unique()), key="r_l")

            df_r_scope = rr_l_src[rr_l_src['課編號'] == rr_l].copy()
            rnu_i = st.number_input("題目數量", 1, max(len(df_r_scope), 1), min(10, max(len(df_r_scope), 1)), key="r_nu")
            st.caption(f"共 {len(df_r_scope)} 題")

            if st.button("🎤 開始朗讀練習", type="primary", use_container_width=True):
                if not df_r_scope.empty:
                    records = df_r_scope.head(int(rnu_i)).to_dict('records')
                    for r in records:
                        r['_type'] = 'reading'
                    st.session_state.update({
                        "quiz_list": records,
                        "q_idx": 0, "quiz_loaded": True,
                        "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                    })
                    st.rerun()
                else:
                    st.error("❌ 無朗讀題目，請重新選擇")

    # ── Tab：單字重組 ─────────────────────────────────────────────────────
    with tab_v:
        if df_v.empty:
            st.info("單字題庫（vocab 工作表）尚無資料。")
        else:
            df_v2 = df_v.copy()
            if '題目ID' not in df_v2.columns:
                df_v2['題目ID'] = df_v2.apply(
                    lambda r: f"V_{r.get('版本','')}_{r.get('年度','')}_{r.get('冊編號','')}_{r.get('單元','')}_{r.get('課編號','')}_{r.get('句編號','')}", axis=1
                )

            with st.expander("⚙️ 篩選單字範圍", expanded=True):
                vv = st.selectbox("版本", sorted(df_v2['版本'].unique()), key="v_v")
                vv_u_src = df_v2[df_v2['版本'] == vv]
                vu = st.selectbox("單元", sorted(vv_u_src['單元'].unique()) if '單元' in vv_u_src.columns else ['單字'], key="v_u")
                vv_y_src = vv_u_src[vv_u_src['單元'] == vu] if '單元' in vv_u_src.columns else vv_u_src
                vy = st.selectbox("年度", sorted(vv_y_src['年度'].unique()), key="v_y")
                vv_b_src = vv_y_src[vv_y_src['年度'] == vy]
                vb = st.selectbox("冊別", sorted(vv_b_src['冊編號'].unique()), key="v_b")
                vv_l_src = vv_b_src[vv_b_src['冊編號'] == vb]
                vl = st.selectbox("課次", sorted(vv_l_src['課編號'].unique()), key="v_l")

            df_v_scope = vv_l_src[vv_l_src['課編號'] == vl].copy()
            vnu_i = st.number_input("題目數量", 1, max(len(df_v_scope), 1), min(10, max(len(df_v_scope), 1)), key="v_nu")

            v_mode_sel = st.radio("模式", ["🔤 拆字母", "⌨️ 鍵盤", "學生自選"], horizontal=True, key="v_mode_sel")
            v_timer    = st.number_input("限時（秒，0=不限時）", 0, 300, 30, key="v_timer")
            v_extra    = st.number_input("干擾字母數量", 0, 10, 3, key="v_extra")

            st.caption(f"共 {len(df_v_scope)} 題")

            if st.button("🔤 開始單字練習", type="primary", use_container_width=True):
                if not df_v_scope.empty:
                    records = df_v_scope.head(int(vnu_i)).to_dict('records')
                    mode_map = {"🔤 拆字母": "拆字母", "⌨️ 鍵盤": "鍵盤", "學生自選": "自選"}
                    for rec in records:
                        rec['_type']        = 'vocab'
                        rec['_vocab_mode']  = mode_map.get(v_mode_sel, "自選")
                        rec['_vocab_timer'] = v_timer
                        rec['_vocab_extra'] = v_extra
                    st.session_state.update({
                        "quiz_list": records,
                        "q_idx": 0, "quiz_loaded": True,
                        "ans": [], "used_history": [], "shuf": [], "show_analysis": False
                    })
                    st.rerun()
                else:
                    st.error("❌ 無單字題目，請重新選擇")

    show_version_caption()

# ------------------------------------------------------------------------------
# 📦 【盒子 D：練習引擎】
# ------------------------------------------------------------------------------
if st.session_state.quiz_loaded:
    st.markdown(f"### 🔴 練習中 (第 {st.session_state.q_idx + 1} / {len(st.session_state.quiz_list)} 題)")
    q = st.session_state.quiz_list[st.session_state.q_idx]
    is_mcq     = "單選" in q.get("單元", "")
    is_reading = q.get("_type") == "reading" or "朗讀" in q.get("單元", "")
    is_vocab   = q.get("_type") == "vocab"

    # 題目標題
    if is_reading:
        st.markdown("#### 🎤 請朗讀以下英文句子：")
        read_text = str(q.get("朗讀句子") or q.get("英文句子") or q.get("英文答案") or "").strip()
        st.markdown(
            f"<div style='font-size:1.5rem; font-weight:600; padding:16px; "
            f"background:var(--color-background-secondary); border-radius:8px; "
            f"letter-spacing:0.03em;'>{read_text}</div>",
            unsafe_allow_html=True
        )
        st.write("")

        # 若已有評分，先顯示分數、TTS 和重錄提示
        if st.session_state.get('show_analysis') and is_reading:
            st.warning(st.session_state.current_res)

            # 播放學生版和標準版
            tts_stu = st.session_state.get('tts_student')
            tts_std = st.session_state.get('tts_standard')
            stt_shown = st.session_state.get('stt_text_shown', '')

            if tts_stu or tts_std:
                import base64, io
                if tts_stu:
                    st.markdown(f"**🎤 AI 認為你說的內容：** `{stt_shown}`")
                    st.audio(io.BytesIO(base64.b64decode(tts_stu)), format="audio/mpeg")
                if tts_std:
                    st.markdown("**📢 標準發音：**")
                    st.audio(io.BytesIO(base64.b64decode(tts_std)), format="audio/mpeg")

            if st.session_state.get('show_analysis') and is_reading:
                st.caption("👇 如想提高成績，可重新錄音再送出評分")
            else:
                st.caption("👇 點擊下方按鈕開始錄音")

        # 放大錄音按鈕的 CSS
        st.markdown("""
            <style>
            [data-testid="stAudioInput"] {
                margin: 8px 0 16px 0;
            }
            </style>
        """, unsafe_allow_html=True)

        # 麥克風一直顯示（不管有沒有評分過）
        audio_data = st.audio_input("🎙️ 錄音", key=f"audio_{st.session_state.q_idx}")

        if audio_data:
            if st.button("✅ 送出評分", type="primary", use_container_width=True):
                with st.spinner("🔄 評分中，請稍候..."):
                    try:
                        import openai
                        openai.api_key = st.secrets["OPENAI_API_KEY"]

                        # Step 1：Whisper STT
                        audio_data.seek(0)
                        transcript = openai.audio.transcriptions.create(
                            model="whisper-1",
                            file=("audio.wav", audio_data, "audio/wav"),
                            language="en"
                        )
                        stt_text = transcript.text.strip()

                        # Step 2：GPT-4o-mini 評分
                        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                        score_resp = client.chat.completions.create(
                            model="gpt-4o-mini",
                            max_tokens=10,
                            messages=[{
                                "role": "user",
                                "content": (
                                    f"You are an English pronunciation evaluator for students.\n"
                                    f"Standard sentence: \"{read_text}\"\n"
                                    f"Student said (transcribed): \"{stt_text}\"\n"
                                    f"Score accuracy and completeness from 0 to 100. "
                                    f"Reply with ONLY a single integer, nothing else."
                                )
                            }]
                        )
                        score_raw = score_resp.choices[0].message.content.strip()
                        score = max(0, min(100, int(re.sub(r'[^0-9]', '', score_raw) or '0')))

                        if score >= 90:
                            result_display = f"✅ 優秀！{score} 分"
                        elif score >= 70:
                            result_display = f"🟡 不錯！{score} 分"
                        elif score >= 50:
                            result_display = f"🟠 需加強 {score} 分"
                        else:
                            result_display = f"❌ 請再試試 {score} 分"

                        # TTS：產生學生版和標準版音檔，存為 base64 避免 rerun 後 bytes 失效
                        import base64
                        tts_stu_raw = client.audio.speech.create(
                            model="tts-1", voice="alloy", input=stt_text
                        ).content if stt_text else None

                        tts_std_raw = client.audio.speech.create(
                            model="tts-1", voice="nova", input=read_text
                        ).content if read_text else None

                        st.session_state.update({
                            "current_res":    result_display,
                            "show_analysis":  True,
                            "tts_student":    base64.b64encode(tts_stu_raw).decode() if tts_stu_raw else None,
                            "tts_standard":   base64.b64encode(tts_std_raw).decode() if tts_std_raw else None,
                            "stt_text_shown": stt_text
                        })

                        # 寫入 Log（每次送出都記一筆）
                        log_data = pd.DataFrame([{
                            "時間":    get_now().strftime("%Y-%m-%d %H:%M:%S"),
                            "姓名":    st.session_state.user_name,
                            "分組":    st.session_state.group_id,
                            "題目ID":  q.get('題目ID', 'N/A'),
                            "結果":    "🎤 朗讀",
                            "學生答案": stt_text,
                            "分數":    score
                        }])
                        append_to_sheet("logs", log_data)
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ 評分失敗：{e}")

    elif is_vocab:
        # ── 單字重組題型 ──────────────────────────────────────────────────
        import random as _random, string as _string

        word     = str(q.get("英文單字") or "").strip()
        meaning  = str(q.get("中文意思") or "").strip()
        task_mode    = q.get("_vocab_mode", "自選")
        use_timer    = int(q.get("_vocab_timer", 0) or 0)
        extra_letters= int(q.get("_vocab_extra", 3) or 3)

        st.markdown(f"<div style=\'font-size:1.3rem;font-weight:600;padding:12px;background:var(--color-background-secondary);border-radius:8px;\'>📖 {meaning}</div>", unsafe_allow_html=True)
        st.write("")

        # 限時倒數
        if use_timer > 0:
            if st.session_state.get("vocab_q_idx") != st.session_state.q_idx:
                st.session_state["vocab_start_time"] = get_now().timestamp()
                st.session_state["vocab_q_idx"] = st.session_state.q_idx
            elapsed = get_now().timestamp() - st.session_state.get("vocab_start_time", get_now().timestamp())
            remain  = max(0, use_timer - int(elapsed))
            st.markdown(f"⏱️ 剩餘時間：**{remain} 秒**")
            if remain == 0 and not st.session_state.get("show_analysis"):
                st.session_state.update({"current_res": f"⏰ 時間到！答案是：{word}", "show_analysis": True})
                append_to_sheet("logs", pd.DataFrame([{"時間": get_now().strftime("%Y-%m-%d %H:%M:%S"), "姓名": st.session_state.user_name, "分組": st.session_state.group_id, "題目ID": q.get("題目ID","N/A"), "結果": "❌"}]))
                st.rerun()

        # 模式切換
        if task_mode in ("自選", "學生自選"):
            # 學生可隨時切換，用全域 key 保持狀態（不綁定題目 index）
            vocab_mode = st.radio(
                "輸入模式",
                ["🔤 拆字母", "⌨️ 鍵盤"],
                horizontal=True,
                key="vocab_mode_global",
                disabled=st.session_state.get("show_analysis", False)
            )
        else:
            vocab_mode = "🔤 拆字母" if task_mode == "拆字母" else "⌨️ 鍵盤"
            # 老師鎖定模式，不顯示切換

        # 初始化字母池
        pool_key = f"vocab_pool_{st.session_state.q_idx}"
        if pool_key not in st.session_state:
            letters = list(word.upper())
            _random.shuffle(letters)
            candidates = [c for c in _string.ascii_uppercase if c not in word.upper()]
            extra = _random.sample(candidates, min(extra_letters, len(candidates)))
            all_letters = letters + extra
            _random.shuffle(all_letters)
            st.session_state[pool_key] = all_letters
        letter_pool = st.session_state[pool_key]

        ans_key_v = f"vocab_ans_{st.session_state.q_idx}"
        if ans_key_v not in st.session_state:
            st.session_state[ans_key_v] = []

        # ── 拆字母模式 ────────────────────────────────────────────────────
        if "拆字母" in vocab_mode:
            current_ans = st.session_state[ans_key_v]
            if current_ans:
                letters_html = "".join([
                    f"<span style='display:inline-block;padding:4px 10px;margin:2px;background:#4a90d9;color:white;border-radius:6px;font-size:1.3rem;font-weight:700;letter-spacing:0.05em;'>{c.lower()}</span>"
                    for c in current_ans
                ])
                ans_display = letters_html
            else:
                ans_display = "<span style='color:#aaa;font-size:1rem;'>點選下方字母</span>"
            st.markdown(f"<div style='padding:10px;min-height:50px;background:#f0f4ff;border-radius:8px;'>{ans_display}</div>", unsafe_allow_html=True)
            bc1, bc2 = st.columns(2)
            if bc1.button("⬅️ 退回一步", use_container_width=True, key=f"vb_back_{st.session_state.q_idx}"):
                if current_ans:
                    st.session_state[ans_key_v].pop()
                    st.rerun()
            if bc2.button("🗑️ 全部清除", use_container_width=True, key=f"vb_clear_{st.session_state.q_idx}"):
                st.session_state[ans_key_v] = []
                st.rerun()
            if not st.session_state.get("show_analysis"):
                used_indices = st.session_state.get(f"vocab_used_{st.session_state.q_idx}", [])
                avail = [(i, ltr) for i, ltr in enumerate(letter_pool) if i not in used_indices]
                cols_v = st.columns(min(len(avail), 8))
                for ci, (i, ltr) in enumerate(avail):
                    if cols_v[ci % 8].button(ltr.lower(), key=f"vl_{st.session_state.q_idx}_{i}", use_container_width=True):
                        st.session_state[ans_key_v].append(ltr)  # 仍存大寫供比對
                        used_st = st.session_state.get(f"vocab_used_{st.session_state.q_idx}", [])
                        used_st.append(i)
                        st.session_state[f"vocab_used_{st.session_state.q_idx}"] = used_st
                        st.rerun()
            if len(current_ans) == len(word) and not st.session_state.get("show_analysis"):
                if st.button("✅ 檢查答案", type="primary", use_container_width=True, key=f"vb_check_{st.session_state.q_idx}"):
                    is_ok = "".join(current_ans).upper() == word.upper()
                    st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{word}", "show_analysis": True})
                    append_to_sheet("logs", pd.DataFrame([{"時間": get_now().strftime("%Y-%m-%d %H:%M:%S"), "姓名": st.session_state.user_name, "分組": st.session_state.group_id, "題目ID": q.get("題目ID","N/A"), "結果": "✅" if is_ok else "❌", "學生答案": "".join(current_ans)}]))
                    st.rerun()

        # ── 鍵盤模式 ──────────────────────────────────────────────────────
        else:
            if not st.session_state.get("show_analysis"):
                kb_ans = st.session_state.get(f"vocab_kb_{st.session_state.q_idx}", "")
                st.markdown(f"<div style=\'font-size:1.4rem;letter-spacing:0.1em;padding:10px;min-height:50px;background:#f0f4ff;border-radius:8px;\'>{kb_ans if kb_ans else '（點選鍵盤輸入）'}</div>", unsafe_allow_html=True)
                if st.button("🗑️ 清除", key=f"kb_clear_{st.session_state.q_idx}"):
                    st.session_state[f"vocab_kb_{st.session_state.q_idx}"] = ""
                    st.rerun()
                keyboard_rows = [list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm")]
                for row in keyboard_rows:
                    kb_cols = st.columns(len(row))
                    for i, k in enumerate(row):
                        if kb_cols[i].button(k, key=f"kb_{st.session_state.q_idx}_{k}{i}", use_container_width=True):
                            st.session_state[f"vocab_kb_{st.session_state.q_idx}"] = st.session_state.get(f"vocab_kb_{st.session_state.q_idx}", "") + k.upper()
                            st.rerun()
                kb_current = st.session_state.get(f"vocab_kb_{st.session_state.q_idx}", "")
                if len(kb_current) >= len(word):
                    if st.button("✅ 檢查答案", type="primary", use_container_width=True, key=f"kb_check_{st.session_state.q_idx}"):
                        is_ok = kb_current.upper() == word.upper()
                        st.session_state.update({"current_res": "✅ 正確！" if is_ok else f"❌ 錯誤！正確答案：{word}", "show_analysis": True})
                        append_to_sheet("logs", pd.DataFrame([{"時間": get_now().strftime("%Y-%m-%d %H:%M:%S"), "姓名": st.session_state.user_name, "分組": st.session_state.group_id, "題目ID": q.get("題目ID","N/A"), "結果": "✅" if is_ok else "❌", "學生答案": kb_current}]))
                        st.rerun()

        # 答對後播放 TTS
        if st.session_state.get("show_analysis") and is_vocab:
            res = st.session_state.get("current_res", "")
            tts_key = f"vocab_tts_{st.session_state.q_idx}"
            if "✅" in res:
                st.success(res)
                if not st.session_state.get(tts_key):
                    try:
                        import openai as _oai, base64 as _b64, io as _io
                        _client = _oai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                        tts_raw = _client.audio.speech.create(model="tts-1", voice="nova", input=word).content
                        st.session_state[tts_key] = _b64.b64encode(tts_raw).decode()
                        st.rerun()
                    except:
                        pass
                if st.session_state.get(tts_key):
                    import base64 as _b64, io as _io
                    st.markdown(f"**🔊 {word}**")
                    st.audio(_io.BytesIO(_b64.b64decode(st.session_state[tts_key])), format="audio/mpeg")
            else:
                st.warning(res)


    elif is_mcq:
        # 題目標題
        st.markdown(f"#### 題目：{q.get('單選題目') or q.get('中文題目') or '【無資料】'}")
        ans_key = str(q.get("單選答案") or "").strip()

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
        # 題目標題（重組題）
        st.markdown(f"#### 題目：{q.get('重組中文題目') or q.get('中文題目') or '【無資料】'}")
        ans_key = str(q.get("重組英文答案") or q.get("英文答案") or "").strip()

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

    if st.session_state.get('show_analysis') and not is_reading:
        st.warning(st.session_state.current_res)
        # 朗讀題的分數已在麥克風上方顯示，不在此重複
    st.divider()
    c_nav = st.columns(2)

    def _clear_q():
        q_idx = st.session_state.q_idx
        st.session_state.update({
            "ans": [], "used_history": [], "shuf": [], "show_analysis": False,
            "tts_student": None, "tts_standard": None, "stt_text_shown": "",
            "vocab_start_time": None, "vocab_q_idx": None
        })
        for k in [f"vocab_pool_{q_idx}", f"vocab_ans_{q_idx}",
                  f"vocab_used_{q_idx}", f"vocab_kb_{q_idx}",
                  f"vocab_tts_{q_idx}"]:
            st.session_state.pop(k, None)

    if st.session_state.q_idx > 0:
        if c_nav[0].button("⬅️ 🔵 上一題", use_container_width=True):
            st.session_state.q_idx -= 1
            _clear_q()
            st.rerun()

    nxt_label = "下一題 ➡️" if st.session_state.q_idx + 1 < len(st.session_state.quiz_list) else "🏁 結束練習"
    if c_nav[1].button(nxt_label, type="primary", use_container_width=True):
        if st.session_state.q_idx + 1 < len(st.session_state.quiz_list):
            st.session_state.q_idx += 1
            _clear_q()
            st.rerun()
        else:
            st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
            st.rerun()

    if st.button("🏁 🔴 結束作答 (返回主選單)", use_container_width=True):
        st.session_state.update({"quiz_loaded": False, "range_confirmed": False})
        st.rerun()

    show_version_caption()
