# ==============================================================================
# 🧩 程式版本資訊 (VERSION HISTORY)
# ==============================================================================
# 版本編號: 1.6.0
# 更新日期: 2026-03-07
# 功能說明:
# 1. 介面進化：參考日文版版面，優化拼湊空格區與單字按鈕排列。
# 2. 導覽強化：底部四功能鍵（退回、重填、上一題、下一題）採等寬併排，符合手機操作。
# 3. 邏輯修正：確保上一題/下一題在切換時能精確重置當前題目狀態。
# 4. 數據篩選：保留「年度、冊別、單元、課次」多階層下拉選單。
# ==============================================================================

import streamlit as st
import pandas as pd
import random
import re

VERSION = "1.6.0"

st.set_page_config(page_title=f"英文重組 V{VERSION}", layout="centered")

# CSS 強制仿製截圖版面
st.markdown(f"""
    <style>
    /* 全域字體優化 */
    html, body, [class*="css"] {{
        font-family: "Microsoft JhengHei", sans-serif;
    }}
    /* 中文提示區塊 */
    .hint-box {{
        background-color: #e3f2fd;
        padding: 15px;
        border-radius: 10px;
        color: #1565c0;
        font-weight: bold;
        font-size: 18px;
        margin-bottom: 10px;
        border: 1px solid #bbdefb;
    }}
    /* 拼湊空格區塊 */
    .answer-display {{
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        border: 2px solid #e0e0e0;
        min-height: 80px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        color: #333;
        margin-bottom: 20px;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
    }}
    /* 功能鍵列按鈕 */
    .stButton > button {{
        border-radius: 8px;
        font-weight: normal;
        height: 45px;
        font-size: 14px !important;
        padding: 0px;
        border: 1px solid #d1d5db;
        background-color: #ffffff;
        color: #374151;
    }}
    /* 單字按鈕樣式 */
    .word-btn > div > button {{
        background-color: #ffffff !important;
        border: 2px solid #e5e7eb !important;
        color: #111827 !important;
        font-size: 18px !important;
        height: 50px !important;
        border-radius: 12px !important;
    }}
    /* 隱藏預設元件間距 */
    .block-container {{ padding-top: 1rem; }}
    </style>
""", unsafe_allow_html=True)

# 1. 資料讀取
SHEET_ID = "1zVUNGboZALvK3val1RSbCQvEESLRSNEulqpNSzsPJ14"
GID = "176577556"
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ['年度', '冊編號', '課編號', '句編號']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except: return None

def reset_all_state():
    st.session_state.q_idx = 0
    st.session_state.ans = []
    st.session_state.used_history = []
    st.session_state.shuf = []
    st.session_state.history = {}
    st.session_state.finished = False
    st.session_state.is_correct = False
    st.session_state.check_clicked = False

if 'q_idx' not in st.session_state: reset_all_state()

df = load_data()

if df is not None:
    # --- 頂部範圍下拉選單 ---
    with st.expander("🎯 練習範圍設定", expanded=not st.session_state.get('history')):
        c1, c2 = st.columns(2)
        years = sorted(df['年度'].unique().astype(int).tolist()) if '年度' in df.columns else [0]
        sel_y = c1.selectbox("年度", years)
        df_y = df[df['年度'] == sel_y]
        
        books = sorted(df_y['冊編號'].unique().astype(int).tolist())
        sel_b = c2.selectbox("冊別", books)
        df_b = df_y[df_y['冊編號'] == sel_b]
        
        c3, c4 = st.columns(2)
        units = sorted(df_b['單元'].unique().tolist()) if '單元' in df.columns else ["預設"]
        sel_u = c3.selectbox("單元", units)
        df_u = df_b[df_b['單元'] == sel_u]
        
        lessons = sorted(df_u['課編號'].unique().astype(int).tolist())
        sel_l = c4.selectbox("課次", lessons)
        
        base_df = df_u[df_u['課編號'] == sel_l].sort_values('句編號')
        
        if not base_df.empty:
            start_id = st.number_input(f"起始句號", int(base_df['句編號'].min()), int(base_df['句編號'].max()))
            num_q = st.slider("題數", 1, len(base_df[base_df['句編號']>=start_id]), 5)
            quiz_list = base_df[base_df['句編號']>=start_id].head(num_q).to_dict('records')

            key = f"{sel_y}-{sel_b}-{sel_u}-{sel_l}-{start_id}-{num_q}"
            if st.session_state.get('last_key') != key:
                st.session_state.last_key = key
                reset_all_state()
                st.rerun()

    if not base_df.empty and not st.session_state.finished:
        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            # 1. 中文提示區
            st.markdown(f'<div class="hint-box">第 {q.get("單元","")} 章 | Q{st.session_state.q_idx + 1} | {q["中文"]}</div>', unsafe_allow_html=True)

            # 2. 拼湊顯示區
            res_str = " ".join(st.session_state.ans)
            display_text = res_str if res_str else "——"
            st.markdown(f'<div class="answer-display">{display_text}</div>', unsafe_allow_html=True)

            # 3. 單字按鈕區 (點選單字按鈕提示)
            st.caption("▼ 請點選單字按鈕")
            btn_cols = st.columns(2) # 手機版改為兩列大按鈕
            for idx, token in enumerate(st.session_state.shuf):
                if idx not in st.session_state.used_history:
                    with btn_cols[idx % 2]:
                        st.markdown('<div class="word-btn">', unsafe_allow_html=True)
                        if st.button(token, key=f"t_{idx}", use_container_width=True):
                            st.session_state.ans.append(token)
                            st.session_state.used_history.append(idx)
                            st.session_state.check_clicked = False
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

            st.write("---")
            
            # 4. 底部功能鍵 (等寬四列)
            nav_cols = st.columns(4)
            
            # 退回
            if nav_cols[0].button("⬅ 退回", key="f_undo"):
                if st.session_state.used_history:
                    st.session_state.used_history.pop()
                    st.session_state.ans.pop()
                    st.session_state.check_clicked = False
                    st.rerun()
            
            # 重填
            if nav_cols[1].button("🔄 重填", key="f_clear"):
                st.session_state.ans, st.session_state.used_history, st.session_state.check_clicked = [], [], False
                st.rerun()
            
            # 上一題
            if nav_cols[2].button("⏮ 上一題", key="f_prev", disabled=(st.session_state.q_idx == 0)):
                st.session_state.q_idx -= 1
                st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                st.rerun()
                
            # 下一題
            next_label = "⏭ 下一題" if st.session_state.q_idx + 1 < len(quiz_list) else "🏁 完成"
            if nav_cols[3].button(next_label, key="f_next"):
                if st.session_state.q_idx + 1 < len(quiz_list):
                    st.session_state.q_idx += 1
                    st.session_state.ans, st.session_state.used_history, st.session_state.shuf, st.session_state.is_correct, st.session_state.check_clicked = [], [], [], False, False
                    st.rerun()
                else:
                    st.session_state.finished = True
                    st.rerun()

            # 5. 檢查答案 (置中大按鈕)
            if len(st.session_state.ans) == len(correct_tokens) and not st.session_state.is_correct:
                st.write("")
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    st.session_state.check_clicked = True
                    user_f = "".join(st.session_state.ans).lower()
                    target_f = eng_raw.replace(" ", "").lower()
                    st.session_state.is_correct = (user_f == target_f)
                    st.session_state.history[st.session_state.q_idx] = {
                        "題號": q['句編號'], "正確答案": eng_raw, "狀態": "✅" if st.session_state.is_correct else "❌"
                    }
                    if st.session_state.is_correct:
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={eng_raw.replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    st.rerun()
            
            if st.session_state.is_correct:
                st.success("Correct! 🎉")

        else:
            st.session_state.finished = True

    if st.session_state.finished:
        st.header("🎊 練習成果回顧")
        if st.session_state.history:
            st.table(pd.DataFrame([v for k, v in sorted(st.session_state.history.items())]))
        if st.button("🔄 重新開始練習"): reset_all_state(); st.rerun()

st.caption(f"Ver {VERSION}")
