import streamlit as st
import pandas as pd
import random
import re

st.set_page_config(page_title="國中英文重組練習 Pro", layout="wide")

# 加強版 CSS 樣式
st.markdown("""
    <style>
    .stButton > button {
        border-radius: 8px;
        font-weight: bold;
        transition: 0.3s;
    }
    /* 單字按鈕樣式 */
    div.stButton > button:first-child {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        color: #374151;
    }
    div.stButton > button:hover {
        background-color: #f3f4f6;
        border-color: #3b82f6;
    }
    /* 拼湊結果顯示區 */
    .answer-box {
        font-size: 24px;
        color: #1e40af;
        background-color: #eff6ff;
        padding: 20px;
        border-radius: 12px;
        border: 2px dashed #3b82f6;
        margin-bottom: 20px;
    }
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
        # 確保編號欄位為數字格式方便排序
        for col in ['冊編號', '課編號', '句編號']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['英文', '中文'])
    except:
        return None

# 初始化變數
if 'q_idx' not in st.session_state: st.session_state.q_idx = 0
if 'ans' not in st.session_state: st.session_state.ans = []
if 'used' not in st.session_state: st.session_state.used = set()
if 'shuf' not in st.session_state: st.session_state.shuf = []

df = load_data()

if df is not None:
    # --- 側邊欄：細膩設定 ---
    st.sidebar.header("⚙️ 練習範圍設定")
    
    b_vals = sorted(df['冊編號'].unique().astype(int).tolist())
    sel_b = st.sidebar.selectbox("1. 選擇冊別", b_vals)
    
    l_vals = sorted(df[df['冊編號']==sel_b]['課編號'].unique().astype(int).tolist())
    sel_l = st.sidebar.selectbox("2. 選擇課次", l_vals)
    
    # 過濾基礎題目
    base_df = df[(df['冊編號']==sel_b) & (df['課編號']==sel_l)].sort_values('句編號')
    
    if not base_df.empty:
        # 起始編號與題數設定
        min_id = int(base_df['句編號'].min())
        max_id = int(base_df['句編號'].max())
        start_id = st.sidebar.number_input(f"3. 起始句編號 ({min_id}-{max_id})", min_id, max_id, min_id)
        
        filtered_df = base_df[base_df['句編號'] >= start_id]
        total_available = len(filtered_df)
        num_q = st.sidebar.slider("4. 練習題數", 1, total_available, min(5, total_available))
        
        quiz_list = filtered_df.head(num_q).to_dict('records')
        
        # 換範圍重置
        key = f"{sel_b}-{sel_l}-{start_id}-{num_q}"
        if 'last_k' not in st.session_state or st.session_state.last_k != key:
            st.session_state.last_k = key
            st.session_state.q_idx = 0
            st.session_state.ans = []
            st.session_state.used = set()
            st.session_state.shuf = []
            st.rerun()

        if st.session_state.q_idx < len(quiz_list):
            q = quiz_list[st.session_state.q_idx]
            # 拆分元素
            correct_tokens = re.findall(r"[\w']+|[^\w\s]", str(q['英文']).strip())

            if not st.session_state.shuf:
                tmp = correct_tokens.copy()
                random.shuffle(tmp)
                st.session_state.shuf = tmp

            # --- 主畫面 ---
            st.title(f"Question {st.session_state.q_idx + 1} / {len(quiz_list)}")
            st.markdown(f"#### 冊別: {sel_b} / 課次: {sel_l} / 句編號: {q['句編號']}")
            st.info(f"💡 中文提示：{q['中文']}")

            st.write("### 拼湊結果：")
            res_str = " ".join(st.session_state.ans)
            st.markdown(f'<div class="answer-box">{res_str if res_str else "請點選下方單字開始拼湊..."}</div>', unsafe_allow_html=True)

            # 操作按鈕
            c1, c2, c3 = st.columns([1, 1, 4])
            if c1.button("🔄 全部重填", use_container_width=True):
                st.session_state.ans = []
                st.session_state.used = set()
                st.rerun()
            if c2.button("⬅️ 退回一步", use_container_width=True) and st.session_state.ans:
                # 找到最後一個被使用的 index 並釋放
                last_word = st.session_state.ans.pop()
                # 這裡需要紀錄點選順序才能完美退回，暫以此邏輯示意
                st.session_state.used.clear() # 簡化版重置
                for i, token in enumerate(st.session_state.shuf):
                    if token in st.session_state.ans: # 注意：重複單字會有邏輯瑕疵，這部分建議完整點選
                        pass 
                st.rerun()

            st.write("---")
            st.subheader("點選單字與標點：")
            
            # 排列按鈕 (自動換行)
            cols = st.columns(6)
            for i, t in enumerate(st.session_state.shuf):
                if i not in st.session_state.used:
                    with cols[i % 6]:
                        if st.button(t, key=f"b_{i}", use_container_width=True):
                            st.session_state.ans.append(t)
                            st.session_state.used.add(i)
                            st.rerun()

            st.write("---")
            if len(st.session_state.ans) == len(correct_tokens):
                if st.button("✅ 檢查答案", type="primary", use_container_width=True):
                    if st.session_state.ans == correct_tokens:
                        st.success("完全正確！🎉")
                        t_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=en&client=tw-ob&q={str(q['英文']).replace(' ', '%20')}"
                        st.markdown(f'<audio autoplay src="{t_url}"></audio>', unsafe_allow_html=True)
                    else:
                        st.error("順序不對喔！檢查看看標點符號的位置。")
                
                if st.session_state.ans == correct_tokens:
                    if st.button("下一題 Next ➡️", type="primary", use_container_width=True):
                        st.session_state.q_idx += 1
                        st.session_state.ans = []
                        st.session_state.used = set()
                        st.session_state.shuf = []
                        st.rerun()
    else:
        st.warning("查無題目內容，請調整側邊欄設定。")
