import streamlit as st
import pandas as pd
import random
import re

st.set_page_config(page_title="英文重組練習 - 完整紀錄版", layout="wide")

# CSS 樣式
st.markdown("""
    <style>
    .stButton > button { border-radius: 8px; font-weight: bold; }
    .answer-box {
        font-size: 24px; color: #1e40af; background-color: #eff6ff;
        padding: 20px; border-radius: 12px; border: 2px dashed #3b82f6;
        margin-bottom: 20px; min-height: 80px;
    }
    .status-pass { color: #28a745; font-weight: bold; }
    .status-fail { color: #dc3545; font-weight: bold; }
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
        for col in ['冊編號', '課編號', '句編號']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except:
        return None

# 初始化 Session State
if 'q_idx' not in st.session_state: st.session_state.q_idx = 0
if 'ans' not in st.session_state: st.session_state.ans = []
if 'used_history' not in st.session_state: st.session_state.used_history = []
if 'shuf' not in st.session_state: st.session_state.shuf = []
if 'history' not in st.session_state: st.session_state.history = {} # 改用字典存，方便更新題號紀錄
if 'finished' not in st.session_state: st.session_state.finished = False

df = load_data()

if df is not None:
    # --- 側邊欄設定 ---
    st.sidebar.header("⚙️ 練習範圍設定")
    b_vals = sorted(df['冊編號'].unique().astype(int).tolist())
    sel_b = st.sidebar.selectbox("1. 選擇冊別", b_vals)
    
    l_vals = sorted(df[df['冊編號']==sel_b]['課編號'].unique().astype(int).tolist())
    sel_l = st.sidebar.selectbox("2. 選擇課次", l_vals)
    
    base_df = df[(df['冊編號']==sel_b) & (df['課編號']==sel_l)].sort_values('句編號')
    
    if not base_df.empty:
        min_id = int(base_df['句編號'].min())
        max_id = int(base_df['句編號'].max())
        start_id = st.sidebar.number_input(f"3. 起始句編號", min_id, max_id, min_id)
        
        filtered_df = base_df[base_df['句編號'] >= start_id]
        total_available = len(filtered_df)
        num_q = st.sidebar.slider("4. 練習題數", 1, total_available, min(5, total_available))
        
        quiz_list = filtered_df.head(num_q).to_dict('records')

        # 預習開關
        st.sidebar.write("---")
        is_study_mode = st.sidebar.checkbox("📖 開啟預習模式", value=False)
        
        # 重置邏輯
        key = f"{sel_b}-{sel_l}-{start_id}-{num_q}"
        if 'last_k' not in st.session_state or st.session_state.last_k != key:
            st.session_state.last_k = key
            st.session_state.q_idx = 0
            st.session_state.ans = []
            st.session_state.used_history = []
            st.session_state.shuf = []
            st.session_state.history = {}
            st.session_state.finished = False
            st.rerun()

        # --- 預習模式 ---
        if is_study_mode:
            st.header("📖 課文預習")
            for item in quiz_list:
                with st.container():
                    col_t, col_s = st.columns([5, 1])
                    col_t.markdown(f"**[{item['句編號']}] {item['英文']}**")
                    col_t.caption(f"中文：{item['中文']}")
                    if col_s.button("🔊 發音", key=f"sp_{item['句編號']}"):
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={str(item['英文']).replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    st.write("---")

        # --- 測驗模式 ---
        elif not st.session_state.finished and st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            eng_raw = str(q['英文']).strip()
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", eng_raw)

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            st.title(f"Question {st.session_state.q_idx + 1} / {len(quiz_list)}")
            st.info(f"💡 中文提示：{q['中文']}")

            st.write("### 拼湊結果：")
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div class="answer-box">{res_str if res_str else "請點選下方單字..."}</div>', unsafe_allow_html=True)

            # 按鈕列
            c1, c2, c3 = st.columns([1, 1, 2])
            if c1.button("🔄 全部重填", use_container_width=True):
                st.session_state.ans = []
                st.session_state.used_history = []
                st.rerun()
            
            if c2.button("⬅️ 退回一步", use_container_width=True):
                if st.session_state.used_history:
                    st.session_state.used_history.pop()
                    st.session_state.ans.pop()
                    st.rerun()

            if c3.button("⏭️ 跳過此題", help="直接進入下一題"):
                # 跳過也要存紀錄
                st.session_state.history[st.session_state.q_idx] = {
                    "題號": st.session_state.q_idx + 1,
                    "中文提示": q['中文'],
                    "正確答案": eng_raw,
                    "你的拼湊": " ".join(st.session_state.ans) if st.session_state.ans else "(未作答)",
                    "狀態": "❌ 跳過"
                }
                st.session_state.q_idx += 1
                st.session_state.ans = []
                st.session_state.used_history = []
                st.session_state.shuf = []
                st.rerun()

            st.write("---")
            # 顯示單字按鈕
            cols = st.columns(6)
            for i, t in enumerate(st.session_state.shuf):
                if i not in st.session_state.used_history:
                    with cols[i % 6]:
                        if st.button(t, key=f"b_{i}", use_container_width=True):
                            st.session_state.ans.append(t)
                            st.session_state.used_history.append(i)
                            st.rerun()

            st.write("---")
            # 檢查答案：一按就紀錄
            if len(st.session_state.ans) == len(correct_tokens):
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    is_correct = (st.session_state.ans == correct_tokens)
                    
                    # 不管對錯，點擊檢查就存入紀錄
                    st.session_state.history[st.session_state.q_idx] = {
                        "題號": st.session_state.q_idx + 1,
                        "中文提示": q['中文'],
                        "正確答案": eng_raw,
                        "你的拼湊": " ".join(st.session_state.ans),
                        "狀態": "✅ 正確" if is_correct else "❌ 錯誤"
                    }

                    if is_correct:
                        st.success("完全正確！🎉")
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={eng_raw.replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                        if st.button("下一題 Next ➡️", type="primary"):
                            st.session_state.q_idx += 1
                            st.session_state.ans = []
                            st.session_state.used_history = []
                            st.session_state.shuf = []
                            st.rerun()
                    else:
                        st.error("順序不對喔！紀錄已更新。")

            if st.sidebar.button("🛑 提前結束並查看結果"):
                st.session_state.finished = True
                st.rerun()

        # --- 成果回顧 ---
        else:
            st.header("🎊 練習成果回顧")
            if st.session_state.history:
                # 將字典轉為清單並排序
                final_history = [v for k, v in sorted(st.session_state.history.items())]
                report_df = pd.DataFrame(final_history)
                st.table(report_df)
            else:
                st.write("沒有任何作答紀錄（需點擊「檢查答案」或「跳過」）。")

            if st.button("🔄 重新開始練習"):
                st.session_state.q_idx = 0
                st.session_state.history = {}
                st.session_state.finished = False
                st.rerun()
    else:
        st.warning("查無題目內容。")
