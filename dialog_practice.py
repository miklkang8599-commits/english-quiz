# ==============================================================================
# 🗣️ 對話練習（替換字＋圖卡）模組 — 英文全能練習系統 V2.9.555 起
# ==============================================================================
# 一段固定對話，句中 {欄位} 換成不同單字（每個單字一張圖卡）反覆練習。
# 學生：跟讀 → 看圖說 → 角色對話，每句可錄音，自己勾「說對了／再練」（不自動評分）。
# 老師：圖卡管理（上傳圖片／AI 產生）、指派（選對話、勾圖卡、輪數）、學生紀錄（抽聽錄音）。
#
# 資料：
#   Google Sheets「對話範本」：對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文
#   Google Sheets「替換字」  ：對話ID｜欄位｜英文｜中文｜圖｜圖片描述
#   （兩張表不存在也能用：程式內建「D00 天氣示範」）
#   Supabase：dialog_cards（圖卡圖片）、dialog_assignments（指派）、dialog_logs（練習紀錄）
#   Supabase Storage：flashcards（圖卡，公開）、dialog_audio（學生錄音，不公開）
# ==============================================================================

import html
import hashlib
import io
import json
import random
import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

# ------------------------------------------------------------------------------
# 內建示範對話
# ------------------------------------------------------------------------------
DEMO_ID = "D00"
DEMO_DIALOG = {
    "title": "天氣（示範）",
    "level": "國小",
    "names": {"A": "Amy", "B": "Ben"},
    "turns": [
        {"turn": 1, "role": "A", "en": "Hi, Ben! How's the weather today?", "zh": "嗨，Ben！今天天氣如何？"},
        {"turn": 2, "role": "B", "en": "It's {weather} today.", "zh": "今天{weather}。"},
        {"turn": 3, "role": "A", "en": "Do you want to {activity}?", "zh": "你想要{activity}嗎？"},
        {"turn": 4, "role": "B", "en": "Sure! Let's {activity} together.", "zh": "好啊！我們一起{activity}吧。"},
    ],
    "cards": {
        "weather": [
            {"en": "sunny", "zh": "晴天", "img": "☀️", "desc": "a bright smiling sun"},
            {"en": "cloudy", "zh": "陰天", "img": "☁️", "desc": "grey clouds covering the sky"},
            {"en": "rainy", "zh": "下雨", "img": "🌧️", "desc": "a cloud with rain drops"},
            {"en": "windy", "zh": "刮風", "img": "🌬️", "desc": "strong wind blowing leaves"},
            {"en": "snowy", "zh": "下雪", "img": "❄️", "desc": "snow falling, a snowman"},
            {"en": "hot", "zh": "很熱", "img": "🥵", "desc": "a child sweating under a hot sun"},
            {"en": "cold", "zh": "很冷", "img": "🥶", "desc": "a child shivering in a scarf"},
        ],
        "activity": [
            {"en": "play basketball", "zh": "打籃球", "img": "🏀", "desc": "a child playing basketball"},
            {"en": "fly a kite", "zh": "放風箏", "img": "🪁", "desc": "a child flying a kite"},
            {"en": "go swimming", "zh": "去游泳", "img": "🏊", "desc": "a child swimming in a pool"},
            {"en": "watch TV", "zh": "看電視", "img": "📺", "desc": "a child watching TV on a sofa"},
            {"en": "ride a bike", "zh": "騎腳踏車", "img": "🚲", "desc": "a child riding a bicycle"},
        ],
    },
}

STAGES = ["① 跟讀", "② 看圖說", "③ 角色對話"]
STAGE_HELP = {
    "① 跟讀": "句子完整顯示，替換字有顏色。先聽示範，再錄音跟讀。",
    "② 看圖說": "替換字變成圖卡，看圖自己說出完整句子，錄完按「看答案」對照。",
    "③ 角色對話": "對方只出聲音；輪到你時只看中文提示和圖卡，說出英文。",
}
AVATARS = ["🧒", "👧", "👦", "🧑", "🐶", "🐱", "🐼", "🦊", "🐰", "🐯", "🐸", "🤖"]
VOICE = {"A": "nova", "B": "onyx"}
IMG_STYLE = ("A cute, simple cartoon flashcard illustration for young English learners. "
             "Single clear subject, centered, thick clean outlines, bright friendly colors, "
             "plain white background. No text, no letters, no words, no numbers.")

_SLOT_RE = re.compile(r"\{([^{}]+)\}")

SETUP_SQL = """-- 🗣️ 對話練習（V2.9.555）Supabase 設定：在 Supabase → SQL Editor 貼上整段執行一次
create table if not exists dialog_cards (
  card_id text primary key,
  dialog_id text, slot text, word text,
  image_url text,
  updated_at timestamptz default now()
);
create table if not exists dialog_assignments (
  id bigserial primary key,
  created_at timestamptz default now(),
  dialog_id text, title text,
  cards text,            -- JSON：{"weather": ["sunny","windy"], ...}
  rounds int default 5,
  stages text,           -- 例如 ① 跟讀,② 看圖說,③ 角色對話
  students text,         -- 學生姓名，逗號分隔
  end_date date,
  status text default '進行中',
  created_by text
);
create table if not exists dialog_logs (
  id bigserial primary key,
  created_at timestamptz default now(),
  name text, user_id text, group_id text,
  assign_id bigint, dialog_id text,
  stage text, round_no int, turn_no int,
  words text, self_check text, audio_path text
);
create index if not exists dialog_logs_assign_idx on dialog_logs(assign_id, created_at);
alter table dialog_cards disable row level security;
alter table dialog_assignments disable row level security;
alter table dialog_logs disable row level security;
-- 有些 Supabase 專案會自動把新資料表的 RLS 打開，所以再加上允許讀寫的規則
create policy "dlg_cards_rw" on dialog_cards for all to anon, authenticated using (true) with check (true);
create policy "dlg_assign_rw" on dialog_assignments for all to anon, authenticated using (true) with check (true);
create policy "dlg_logs_rw" on dialog_logs for all to anon, authenticated using (true) with check (true);

-- Storage：flashcards 圖卡（公開讀取）、dialog_audio 學生錄音（不公開，老師用簽名網址抽聽）
insert into storage.buckets (id, name, public) values ('flashcards', 'flashcards', true)
  on conflict (id) do nothing;
insert into storage.buckets (id, name, public) values ('dialog_audio', 'dialog_audio', false)
  on conflict (id) do nothing;
create policy "dlg_flashcards_rw" on storage.objects for all to anon, authenticated
  using (bucket_id = 'flashcards') with check (bucket_id = 'flashcards');
create policy "dlg_audio_rw" on storage.objects for all to anon, authenticated
  using (bucket_id = 'dialog_audio') with check (bucket_id = 'dialog_audio');
"""

_CSS = """<style>
.dlg-row{display:flex;margin:.35rem 0;align-items:flex-end;gap:.45rem}
.dlg-row.mine{flex-direction:row-reverse}
.dlg-av{font-size:2.1rem;line-height:1}
.dlg-bub{max-width:82%;padding:.55rem .8rem;border-radius:14px;background:#f1f3f5;color:#111;
  font-size:1.15rem;line-height:1.6}
.dlg-row.mine .dlg-bub{background:#dbeeff}
.dlg-name{font-size:.8rem;color:#666;margin-bottom:.1rem}
.dlg-zh{font-size:.92rem;color:#555;margin-top:.15rem}
.dlg-mark{background:#ffe066;color:#111;border-radius:5px;padding:0 .25rem;font-weight:600}
.dlg-blank{display:inline-block;border:2px dashed #339af0;border-radius:8px;padding:0 .3rem;
  margin:0 .1rem;background:#fff;vertical-align:middle}
.dlg-hidden{color:#999;font-style:italic}
.dlg-cards{display:flex;flex-wrap:wrap;gap:.6rem;margin:.3rem 0 .6rem}
.dlg-card{border:1px solid #dee2e6;border-radius:12px;padding:.4rem .6rem;text-align:center;
  background:#fff;color:#111;min-width:96px}
.dlg-card .w{font-weight:600;font-size:1rem}
.dlg-card .z{font-size:.8rem;color:#666}
</style>"""


# ------------------------------------------------------------------------------
# 資料載入
# ------------------------------------------------------------------------------
def _s(v):
    v = "" if v is None else str(v)
    return "" if v.lower() == "nan" else v.strip()


@st.cache_data(ttl=300, show_spinner=False)
def _read_sheet(_conn, name):
    try:
        return _conn.read(worksheet=name, ttl=300).fillna("").astype(str).replace(r"\.0$", "", regex=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def _load_card_images(_sb_factory):
    try:
        res = _sb_factory().table("dialog_cards").select("card_id,image_url").execute()
        return {r["card_id"]: r.get("image_url") or "" for r in (res.data or [])}
    except Exception:
        return {}


def card_id(dialog_id, slot, en):
    return f"{dialog_id}|{slot}|{en}"


def load_dialogs(ctx):
    """回傳 {對話ID: {title, level, names, turns, cards{slot:[card]}}}，內建示範在最前面"""
    dialogs = {DEMO_ID: json.loads(json.dumps(DEMO_DIALOG, ensure_ascii=False))}
    df_t = _read_sheet(ctx["conn"], "對話範本")
    df_c = _read_sheet(ctx["conn"], "替換字")
    if not df_t.empty and "對話ID" in df_t.columns:
        for _, r in df_t.iterrows():
            did = _s(r.get("對話ID"))
            if not did or not _s(r.get("英文")):
                continue
            d = dialogs.setdefault(did, {"title": "", "level": "", "names": {}, "turns": [], "cards": {}})
            if did == DEMO_ID and d.get("_from_demo", True):
                # 試算表自己寫了 D00：整段改用試算表
                d.update({"title": "", "level": "", "names": {}, "turns": [], "cards": {}, "_from_demo": False})
            if _s(r.get("標題")):
                d["title"] = _s(r.get("標題"))
            if _s(r.get("程度")):
                d["level"] = _s(r.get("程度"))
            role = (_s(r.get("角色")) or "A").upper()[:1]
            if _s(r.get("角色名稱")):
                d["names"][role] = _s(r.get("角色名稱"))
            try:
                tno = int(float(_s(r.get("回合")) or 0))
            except ValueError:
                tno = 0
            d["turns"].append({"turn": tno or len(d["turns"]) + 1, "role": role,
                               "en": _s(r.get("英文")), "zh": _s(r.get("中文"))})
    if not df_c.empty and "對話ID" in df_c.columns:
        seen_sheet_cards = set()
        for _, r in df_c.iterrows():
            did, slot, en = _s(r.get("對話ID")), _s(r.get("欄位")), _s(r.get("英文"))
            if not did or not slot or not en or did not in dialogs:
                continue
            d = dialogs[did]
            if (did, slot) not in seen_sheet_cards:
                d["cards"][slot] = []          # 試算表有這個欄位就整組取代示範
                seen_sheet_cards.add((did, slot))
            d["cards"][slot].append({"en": en, "zh": _s(r.get("中文")),
                                     "img": _s(r.get("圖")), "desc": _s(r.get("圖片描述"))})
    imgs = _load_card_images(ctx["sb"])
    for did, d in dialogs.items():
        d.pop("_from_demo", None)
        d["turns"].sort(key=lambda t: t["turn"])
        d["title"] = d["title"] or did
        for slot, cards in d["cards"].items():
            for c in cards:
                c["slot"] = slot
                c["id"] = card_id(did, slot, c["en"])
                if imgs.get(c["id"]):
                    c["img"] = imgs[c["id"]]
    return dialogs


def _slots_in(dialog):
    out = []
    for t in dialog["turns"]:
        for m in _SLOT_RE.finditer(t["en"] + " " + t["zh"]):
            s = m.group(1).strip()
            if s not in out:
                out.append(s)
    return out


# ------------------------------------------------------------------------------
# 顯示小工具
# ------------------------------------------------------------------------------
def _img_html(card, px=40):
    src = _s(card.get("img"))
    if src.startswith("http"):
        return (f"<img src='{html.escape(src, quote=True)}' alt='{html.escape(card.get('en',''))}' "
                f"style='height:{px}px;max-width:{int(px*1.6)}px;object-fit:contain;vertical-align:middle;border-radius:6px'>")
    if src:
        return f"<span style='font-size:{int(px*0.8)}px;vertical-align:middle'>{html.escape(src)}</span>"
    return f"<span style='font-size:{int(px*0.6)}px;vertical-align:middle'>🖼️</span>"


def _fill(tpl, combo, field="en", mode="plain"):
    """mode: plain（純文字，給語音）／mark（替換字上色）／blank（替換字換成圖卡）"""
    out, pos = [], 0
    for m in _SLOT_RE.finditer(tpl):
        seg = tpl[pos:m.start()]
        out.append(seg if mode == "plain" else html.escape(seg))
        card = combo.get(m.group(1).strip())
        if card is None:
            out.append(m.group(0) if mode == "plain" else html.escape(m.group(0)))
        else:
            val = card["en"] if field == "en" else (card.get("zh") or card["en"])
            if mode == "plain":
                out.append(val)
            elif mode == "mark":
                out.append(f"<span class='dlg-mark'>{html.escape(val)}</span>")
            else:
                out.append(f"<span class='dlg-blank'>{_img_html(card, 34)}</span>")
        pos = m.end()
    tail = tpl[pos:]
    out.append(tail if mode == "plain" else html.escape(tail))
    return "".join(out)


def _bubble(avatar, name, body, zh="", mine=False):
    zh_html = f"<div class='dlg-zh'>{zh}</div>" if zh else ""
    st.markdown(
        f"<div class='dlg-row{' mine' if mine else ''}'><div class='dlg-av'>{avatar}</div>"
        f"<div class='dlg-bub'><div class='dlg-name'>{html.escape(name)}</div>{body}{zh_html}</div></div>",
        unsafe_allow_html=True)


def _cards_strip(cards, px=64, show_text=True):
    items = []
    for c in cards:
        txt = (f"<div class='w'>{html.escape(c['en'])}</div><div class='z'>{html.escape(c.get('zh',''))}</div>"
               if show_text else "")
        items.append(f"<div class='dlg-card'>{_img_html(c, px)}{txt}</div>")
    st.markdown(f"<div class='dlg-cards'>{''.join(items)}</div>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=600)
def _tts(text, voice, speed):
    # 失敗會丟例外（不快取失敗結果），由 _play 接住
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    return cl.audio.speech.create(model="tts-1", voice=voice, input=text, speed=speed).content


def _play(text, role, speed):
    try:
        audio = _tts(text, VOICE.get(role, "nova"), speed)
    except Exception:
        audio = None
    if audio:
        st.audio(audio, format="audio/mp3")
    else:
        st.caption("（語音暫時無法產生）")


# ------------------------------------------------------------------------------
# Supabase 存取
# ------------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def _load_assignments(_sb_factory, ver=0):
    try:
        res = (_sb_factory().table("dialog_assignments").select("*")
               .neq("status", "已刪除").order("created_at", desc=True).execute())
        return res.data or [], ""
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def _assign_ver():
    return st.session_state.get("_dlg_assign_ver", 0)


def _bump_assign():
    st.session_state["_dlg_assign_ver"] = _assign_ver() + 1


def _setup_hint(err=""):
    st.warning("⚠️ 對話練習的 Supabase 資料表／儲存空間還沒建立。請老師到「🗣️ 對話練習 → ⚙️ 設定說明」"
               "複製 SQL，貼到 Supabase 的 SQL Editor 執行一次。")
    if err:
        with st.expander("🔍 錯誤詳情"):
            st.code(err)


def _signed_url(sb, path, secs=3600):
    try:
        r = sb.storage.from_("dialog_audio").create_signed_url(path, secs)
        if isinstance(r, dict):
            return r.get("signedURL") or r.get("signedUrl") or r.get("signed_url") or ""
        return getattr(r, "signed_url", "") or ""
    except Exception:
        return ""


def _save_log(ctx, run, stage, rno, tno, combo_words, check, audio_bytes):
    sb = ctx["sb"]()
    path = ""
    if audio_bytes:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        path = f"{ctx['user_id']}/{run.get('assign_id') or 'trial'}/{ts}_s{STAGES.index(stage)+1}_r{rno}_t{tno}.wav"
        try:
            sb.storage.from_("dialog_audio").upload(path, audio_bytes, {"content-type": "audio/wav"})
        except Exception as e:
            # V2.9.557：錯誤留在畫面上（toast 會被 st.rerun 蓋掉）
            st.session_state["dlg_last_err"] = f"錄音上傳失敗（紀錄仍會存）：{type(e).__name__}: {e}"
            path = ""
    aid = run.get("assign_id")
    try:
        sb.table("dialog_logs").insert({
            "name": str(ctx.get("user_name") or ""), "user_id": str(ctx.get("user_id") or ""),
            "group_id": str(ctx.get("group_id") or ""),
            "assign_id": int(aid) if aid not in (None, "") else None, "dialog_id": str(run["dialog_id"]),
            "stage": str(stage), "round_no": int(rno), "turn_no": int(tno),
            "words": ";".join(f"{k}={v}" for k, v in combo_words.items()),
            "self_check": str(check), "audio_path": path,
        }).execute()
        return True
    except Exception as e:
        st.session_state["dlg_last_err"] = f"紀錄寫入失敗：{type(e).__name__}: {e}"
        return False


# ------------------------------------------------------------------------------
# 學生端
# ------------------------------------------------------------------------------
def _make_combos(sel, n):
    cols = {}
    for slot, words in sel.items():
        words = list(words)
        if not words:
            continue
        seq = []
        while len(seq) < n:
            w = words[:]
            random.shuffle(w)
            if seq and len(w) > 1 and w[0] == seq[-1]:
                w.append(w.pop(0))
            seq += w
        cols[slot] = seq[:n]
    return [{s: cols[s][i] for s in cols} for i in range(n)]


def _start_run(dialog_id, dialog, sel, rounds, stages, assign_id=None, title=""):
    allc = {s: [c["en"] for c in dialog["cards"].get(s, [])] for s in _slots_in(dialog)}
    sel = {s: (sel.get(s) or allc.get(s, [])) for s in allc}
    for k in [k for k in st.session_state.keys() if str(k).startswith(("dlg_rec_", "dlg_stage"))]:
        st.session_state.pop(k, None)
    st.session_state["dlg_run"] = {
        "assign_id": assign_id, "dialog_id": dialog_id, "title": title or dialog["title"],
        "sel": sel, "rounds": max(1, int(rounds)), "stages": [x for x in STAGES if x in stages] or STAGES[:],
        "combos": _make_combos(sel, max(1, int(rounds))), "avatar": None, "role": None,
        "round": 0, "checks": {}, "reveal": {},
    }


def render_student_entry(ctx):
    """放在學生任務列表最前面。若正在練對話，畫練習畫面並 st.stop()。"""
    st.markdown(_CSS, unsafe_allow_html=True)
    if st.session_state.get("dlg_run"):
        _render_run(ctx)
        st.stop()

    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    today = ctx["today"]
    mine = []
    for a in rows:
        try:
            if a.get("end_date") and datetime.strptime(str(a["end_date"])[:10], "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            pass
        names = [x.strip() for x in str(a.get("students") or "").split(",") if x.strip()]
        if ctx["is_admin"] or ctx["user_name"] in names:
            mine.append(a)
    if not mine and not ctx["is_admin"]:
        return

    dialogs = load_dialogs(ctx)
    st.markdown("<h2 style='margin-bottom:0'>🗣️ 對話練習</h2>", unsafe_allow_html=True)
    if err and ctx["is_admin"]:
        _setup_hint(err)
    for a in mine:
        d = dialogs.get(a.get("dialog_id"))
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{html.escape(a.get('title') or '對話練習')}**  \n"
                    f"<span style='color:#888;font-size:.85rem'>{a.get('rounds', 5)} 輪｜截止 {str(a.get('end_date') or '')[:10]}</span>",
                    unsafe_allow_html=True)
        if d is None:
            c2.caption("找不到對話")
            continue
        if c2.button("▶️ 開始", key=f"dlg_go_{a['id']}", use_container_width=True, type="primary"):
            try:
                sel = json.loads(a.get("cards") or "{}")
            except ValueError:
                sel = {}
            _start_run(a["dialog_id"], d, sel, a.get("rounds") or 5,
                       [x.strip() for x in str(a.get("stages") or "").split(",")], a["id"], a.get("title"))
            st.rerun()
    if ctx["is_admin"]:
        with st.expander("🧪 老師試玩（不需指派、全部圖卡）"):
            ids = list(dialogs.keys())
            pick = st.selectbox("對話", ids, format_func=lambda i: f"{i}｜{dialogs[i]['title']}", key="dlg_trial_pick")
            n = st.number_input("輪數", 1, 30, 5, key="dlg_trial_n")
            if st.button("▶️ 開始試玩", key="dlg_trial_go"):
                _start_run(pick, dialogs[pick], {}, n, STAGES)
                st.rerun()
    st.divider()


def _render_run(ctx):
    run = st.session_state["dlg_run"]
    dialogs = load_dialogs(ctx)
    d = dialogs.get(run["dialog_id"])
    top1, top2 = st.columns([4, 1])
    top1.markdown(f"### 🗣️ {html.escape(run['title'])}")
    _err = st.session_state.pop("dlg_last_err", "")
    if _err:
        st.error("⚠️ " + _err)
    if top2.button("⬅️ 返回", key="dlg_back", use_container_width=True):
        st.session_state.pop("dlg_run", None)
        st.rerun()
    if d is None:
        st.error("找不到這段對話（可能已從試算表刪除）。")
        return
    names = {"A": d["names"].get("A", "A"), "B": d["names"].get("B", "B")}
    by_en = {s: {c["en"]: c for c in d["cards"].get(s, [])} for s in d["cards"]}

    # ── 第一步：選角色 ──
    if not run["avatar"] or not run["role"]:
        st.markdown("#### 1️⃣ 選一個你的頭像")
        av = st.radio("頭像", AVATARS, horizontal=True, key="dlg_av_pick", label_visibility="collapsed")
        st.markdown("#### 2️⃣ 你要演誰？")
        role = st.radio("角色", ["A", "B"], horizontal=True, key="dlg_role_pick",
                        format_func=lambda r: f"{r}：{names[r]}" + ("（先開口）" if d["turns"] and d["turns"][0]["role"] == r else ""),
                        label_visibility="collapsed")
        with st.expander("👀 先看看整段對話"):
            for t in d["turns"]:
                st.markdown(f"**{names.get(t['role'], t['role'])}**：{html.escape(t['en'])}　<span style='color:#888'>{html.escape(t['zh'])}</span>",
                            unsafe_allow_html=True)
        if st.button("🚀 開始練習", type="primary", key="dlg_setup_ok", use_container_width=True):
            run["avatar"], run["role"] = av, role
            st.rerun()
        return

    me = run["role"]
    partner_av = AVATARS[(AVATARS.index(run["avatar"]) + 4) % len(AVATARS)] if run["avatar"] in AVATARS else "🧑"
    avatars = {me: run["avatar"], ("B" if me == "A" else "A"): partner_av}
    disp = {me: f"{ctx['user_name']}（{names[me]}）", ("B" if me == "A" else "A"): names["B" if me == "A" else "A"]}

    if run.get("goto_stage"):
        # 不能在 radio 畫出來之後才改它的值，所以下一關的切換放在這裡（畫 radio 之前）
        st.session_state["dlg_stage"] = run.pop("goto_stage")
    if st.session_state.get("dlg_stage") not in run["stages"]:
        st.session_state["dlg_stage"] = run["stages"][0]
    c1, c2 = st.columns([3, 2])
    stage = c1.radio("關卡", run["stages"], horizontal=True, key="dlg_stage")
    speed_lbl = c2.radio("語速", ["正常", "慢速"], horizontal=True, key="dlg_speed")
    speed = 1.0 if speed_lbl == "正常" else 0.75
    st.caption("💡 " + STAGE_HELP[stage])

    n = run["rounds"]
    rno = min(run["round"], n - 1)
    combo_words = run["combos"][rno]
    combo = {s: by_en.get(s, {}).get(w, {"en": w, "zh": "", "img": "", "slot": s}) for s, w in combo_words.items()}

    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪")
    st.markdown("**這一輪的圖卡**")
    _cards_strip(list(combo.values()), px=72, show_text=(stage == STAGES[0]))

    for t in d["turns"]:
        role, tno = t["role"], t["turn"]
        mine = role == me
        k = f"{stage}|{rno}|{tno}"
        revealed = run["reveal"].get(k, False)
        plain = _fill(t["en"], combo, "en", "plain")
        if stage == STAGES[0]:
            body = _fill(t["en"], combo, "en", "mark")
            zh = _fill(t["zh"], combo, "zh", "mark") if t["zh"] else ""
        elif stage == STAGES[1]:
            if mine and not revealed:
                body = _fill(t["en"], combo, "en", "blank")
            else:
                body = _fill(t["en"], combo, "en", "mark")
            zh = ""
        else:
            if mine:
                body = (_fill(t["en"], combo, "en", "mark") if revealed
                        else "<span class='dlg-hidden'>（輪到你說）</span>")
                zh = _fill(t["zh"], combo, "zh", "blank") if t["zh"] else ""
            else:
                body = (_fill(t["en"], combo, "en", "mark") if revealed
                        else "<span class='dlg-hidden'>🔊 聽聽看</span>")
                zh = ""
        _bubble(avatars.get(role, "🧑"), disp.get(role, role), body, zh, mine)

        if not mine:
            _play(plain, role, speed)
            if stage == STAGES[2] and not revealed:
                if st.button("📝 顯示文字", key=f"dlg_rv_{k}"):
                    run["reveal"][k] = True
                    st.rerun()
            continue

        # 學生自己的句子
        if stage == STAGES[0] or revealed:
            _play(plain, role, speed)
        rec = st.audio_input("🎙️ 錄音", key=f"dlg_rec_{k}")
        if stage != STAGES[0] and not revealed:
            if st.button("👀 看答案", key=f"dlg_ans_{k}"):
                run["reveal"][k] = True
                st.rerun()
        done = run["checks"].get(k)
        b1, b2, b3 = st.columns([1, 1, 2])
        if b1.button("✅ 說對了", key=f"dlg_ok_{k}", use_container_width=True,
                     type="primary" if done == "✅" else "secondary"):
            if _save_log(ctx, run, stage, rno + 1, tno, combo_words, "✅", rec.getvalue() if rec else None):
                run["checks"][k] = "✅"
            st.rerun()
        if b2.button("🔁 再練", key=f"dlg_again_{k}", use_container_width=True,
                     type="primary" if done == "🔁" else "secondary"):
            if _save_log(ctx, run, stage, rno + 1, tno, combo_words, "🔁", rec.getvalue() if rec else None):
                run["checks"][k] = "🔁"
            st.rerun()
        if done:
            b3.caption(f"已記錄：{done}" + ("（含錄音）" if rec else ""))

    st.divider()
    n1, n2, n3 = st.columns(3)
    if n1.button("⬅️ 上一輪", key="dlg_prev", disabled=rno == 0, use_container_width=True):
        run["round"] = rno - 1
        st.rerun()
    if rno < n - 1:
        if n3.button("下一輪 ➡️", key="dlg_next", type="primary", use_container_width=True):
            run["round"] = rno + 1
            st.rerun()
    else:
        mine_checks = [v for kk, v in run["checks"].items() if kk.startswith(stage + "|")]
        n2.success(f"🎉 這一關完成！✅ {mine_checks.count('✅')}　🔁 {mine_checks.count('🔁')}")
        nxt = run["stages"].index(stage) + 1
        if nxt < len(run["stages"]):
            if n3.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_next_stage", type="primary", use_container_width=True):
                run["goto_stage"] = run["stages"][nxt]
                run["round"] = 0
                st.rerun()


# ------------------------------------------------------------------------------
# 老師端
# ------------------------------------------------------------------------------
def _gen_image(prompt):
    import base64
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    last = None
    for model, kw in (("gpt-image-1-mini", {"quality": "low"}),
                      ("gpt-image-1", {"quality": "low"}),
                      ("dall-e-3", {"quality": "standard", "response_format": "b64_json"})):
        try:
            r = cl.images.generate(model=model, prompt=prompt, size="1024x1024", n=1, **kw)
            b64 = r.data[0].b64_json
            if b64:
                return base64.b64decode(b64), model
        except Exception as e:
            last = e
    raise RuntimeError(f"{type(last).__name__}: {last}")


def _to_png(raw):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    im.thumbnail((512, 512))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _save_card_image(ctx, dialog_id, card, raw):
    sb = ctx["sb"]()
    png = _to_png(raw)
    path = f"{re.sub(r'[^A-Za-z0-9_-]', '_', dialog_id)}/{hashlib.md5(card['id'].encode('utf-8')).hexdigest()}.png"
    sb.storage.from_("flashcards").upload(path, png, {"content-type": "image/png", "upsert": "true"})
    url = sb.storage.from_("flashcards").get_public_url(path)
    if isinstance(url, dict):
        url = url.get("publicUrl") or url.get("publicURL") or ""
    url = str(url).rstrip("?") + f"?v={int(datetime.utcnow().timestamp())}"
    sb.table("dialog_cards").upsert({
        "card_id": card["id"], "dialog_id": dialog_id, "slot": card["slot"], "word": card["en"],
        "image_url": url, "updated_at": datetime.utcnow().isoformat(),
    }).execute()
    _load_card_images.clear()
    return url


def render_teacher(ctx):
    st.markdown(_CSS, unsafe_allow_html=True)
    dialogs = load_dialogs(ctx)
    tabs = st.tabs(["🖼️ 對話與圖卡", "📌 指派", "🎧 學生紀錄", "⚙️ 設定說明"])
    with tabs[0]:
        _teacher_cards(ctx, dialogs)
    with tabs[1]:
        _teacher_assign(ctx, dialogs)
    with tabs[2]:
        _teacher_records(ctx, dialogs)
    with tabs[3]:
        _teacher_setup()


def _pick_dialog(dialogs, key):
    ids = list(dialogs.keys())
    return st.selectbox("對話", ids, key=key,
                        format_func=lambda i: f"{i}｜{dialogs[i]['title']}" + (f"（{dialogs[i]['level']}）" if dialogs[i]["level"] else ""))


def _teacher_cards(ctx, dialogs):
    c1, c2 = st.columns([5, 1])
    with c1:
        did = _pick_dialog(dialogs, "dlg_t_pick")
    if c2.button("🔄", key="dlg_t_reload", help="重新讀取試算表與圖卡"):
        _read_sheet.clear()
        _load_card_images.clear()
        st.rerun()
    d = dialogs[did]
    with st.expander("📜 對話內容", expanded=True):
        for t in d["turns"]:
            st.markdown(f"**{t['turn']}. {html.escape(d['names'].get(t['role'], t['role']))}**："
                        f"{html.escape(t['en'])}　<span style='color:#888'>{html.escape(t['zh'])}</span>",
                        unsafe_allow_html=True)
    missing_slots = [s for s in _slots_in(d) if not d["cards"].get(s)]
    if missing_slots:
        st.warning("這些欄位在「替換字」表還沒有單字：" + "、".join(missing_slots))

    all_cards = [c for s in d["cards"] for c in d["cards"][s]]
    no_img = [c for c in all_cards if not _s(c.get("img")).startswith("http")]
    st.markdown(f"**圖卡：{len(all_cards)} 張，其中 {len(no_img)} 張還沒有圖片檔**（emoji 只是暫代）")
    if no_img and st.button(f"🎨 一次 AI 產生 {len(no_img)} 張缺圖", key="dlg_gen_all"):
        bar = st.progress(0.0)
        ok = 0
        for i, c in enumerate(no_img):
            try:
                raw, _m = _gen_image(f"{IMG_STYLE} Subject: {c.get('desc') or c['en']}.")
                _save_card_image(ctx, did, c, raw)
                ok += 1
            except Exception as e:
                st.error(f"{c['en']}：{e}")
            bar.progress((i + 1) / len(no_img), text=f"{i + 1}/{len(no_img)}")
        st.success(f"完成 {ok} 張")
        st.rerun()

    ncol = 2 if ctx.get("is_phone") else 4
    for slot, cards in d["cards"].items():
        st.markdown(f"##### 欄位 `{{{slot}}}`")
        for i in range(0, len(cards), ncol):
            cols = st.columns(ncol)
            for col, c in zip(cols, cards[i:i + ncol]):
                with col:
                    _card_editor(ctx, did, c)


def _card_editor(ctx, did, c):
    st.markdown(f"<div class='dlg-card'>{_img_html(c, 88)}<div class='w'>{html.escape(c['en'])}</div>"
                f"<div class='z'>{html.escape(c.get('zh', ''))}</div></div>", unsafe_allow_html=True)
    hk = hashlib.md5(c["id"].encode("utf-8")).hexdigest()[:10]
    with st.popover("✏️ 換圖", use_container_width=True):
        up = st.file_uploader("上傳圖片", type=["png", "jpg", "jpeg", "webp"], key=f"dlg_up_{hk}")
        if up is not None and st.button("💾 使用上傳的圖", key=f"dlg_upok_{hk}"):
            try:
                _save_card_image(ctx, did, c, up.getvalue())
                st.success("已儲存")
                st.rerun()
            except Exception as e:
                st.error(f"儲存失敗：{type(e).__name__}: {e}")
        st.markdown("---")
        desc = st.text_input("AI 圖片描述（英文較準）", value=c.get("desc") or c["en"], key=f"dlg_desc_{hk}")
        pend_key = f"dlg_pending_{hk}"
        if st.button("🎨 AI 產生", key=f"dlg_gen_{hk}"):
            with st.spinner("產生中（約 10–30 秒）…"):
                try:
                    raw, model = _gen_image(f"{IMG_STYLE} Subject: {desc}.")
                    st.session_state[pend_key] = raw
                except Exception as e:
                    st.error(f"產生失敗：{e}")
        raw = st.session_state.get(pend_key)
        if raw:
            st.image(raw, width=200)
            a1, a2 = st.columns(2)
            if a1.button("✅ 使用這張", key=f"dlg_genok_{hk}"):
                try:
                    _save_card_image(ctx, did, c, raw)
                    st.session_state.pop(pend_key, None)
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存失敗：{type(e).__name__}: {e}")
            if a2.button("🗑️ 不要", key=f"dlg_gendel_{hk}"):
                st.session_state.pop(pend_key, None)
                st.rerun()


def _teacher_assign(ctx, dialogs):
    did = _pick_dialog(dialogs, "dlg_a_pick")
    d = dialogs[did]
    sel = {}
    for slot in _slots_in(d):
        cards = d["cards"].get(slot, [])
        opts = [c["en"] for c in cards]
        lab = {c["en"]: f"{c['en']}｜{c.get('zh', '')}" for c in cards}
        sel[slot] = st.multiselect(f"欄位 {{{slot}}} 要練的圖卡", opts, default=opts, key=f"dlg_a_sel_{did}_{slot}",
                                   format_func=lambda x, lab=lab: lab.get(x, x))
        chosen = [c for c in cards if c["en"] in sel[slot]]
        if chosen:
            _cards_strip(chosen, px=44)
    longest = max([len(v) for v in sel.values()] or [5])
    c1, c2 = st.columns(2)
    rounds = c1.number_input("練幾輪（每輪換一組圖卡）", 1, 30, max(3, min(longest, 10)), key=f"dlg_a_n_{did}")
    end = c2.date_input("截止日期", value=ctx["today"] + timedelta(days=7), key="dlg_a_end")
    stages = st.multiselect("關卡", STAGES, default=STAGES, key="dlg_a_stages")

    df_s = ctx["df_s"]
    stu = df_s[~df_s["分組"].isin(["ADMIN", "TEACHER"])] if "分組" in df_s.columns else df_s
    groups = sorted([g for g in stu["分組"].unique().tolist() if g]) if "分組" in stu.columns else []
    g_pick = st.multiselect("指派班級（整班）", groups, key="dlg_a_groups",
                            format_func=lambda g: f"{g}（{'、'.join(sorted(stu[stu['分組'] == g]['姓名'].tolist()))}）")
    s_pick = st.multiselect("或指定學生", sorted(stu["姓名"].unique().tolist()) if "姓名" in stu.columns else [],
                            key="dlg_a_stus")
    targets = sorted(set(stu[stu["分組"].isin(g_pick)]["姓名"].tolist() if g_pick else []) | set(s_pick))
    words_txt = "、".join(w for v in sel.values() for w in v)
    title = st.text_input("任務名稱", value=f"🗣️ {d['title']}：{words_txt[:40]}", key=f"dlg_a_title_{did}")
    st.caption(f"將指派給 {len(targets)} 位學生")
    if st.button("📤 發布對話練習", type="primary", key="dlg_a_publish",
                 disabled=not targets or any(not v for v in sel.values()) or not stages):
        try:
            ctx["sb"]().table("dialog_assignments").insert({
                "dialog_id": did, "title": title, "cards": json.dumps(sel, ensure_ascii=False),
                "rounds": int(rounds), "stages": ",".join(stages), "students": ",".join(targets),
                "end_date": end.strftime("%Y-%m-%d"), "status": "進行中", "created_by": ctx["user_name"],
            }).execute()
            _bump_assign()
            st.success(f"🎉 已發布，指派給 {len(targets)} 位學生")
        except Exception as e:
            _setup_hint(f"{type(e).__name__}: {e}")

    st.divider()
    st.markdown("#### 📋 已發布的對話練習")
    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    if err:
        _setup_hint(err)
    for a in rows:
        c1, c2 = st.columns([5, 1])
        n_stu = len([x for x in str(a.get("students") or "").split(",") if x.strip()])
        c1.markdown(f"**{html.escape(a.get('title') or '')}**  \n"
                    f"<span style='color:#888;font-size:.85rem'>#{a['id']}｜{a.get('rounds')} 輪｜{n_stu} 人｜截止 {str(a.get('end_date') or '')[:10]}</span>",
                    unsafe_allow_html=True)
        if c2.button("🗑️", key=f"dlg_a_del_{a['id']}", help="刪除這個指派"):
            ctx["sb"]().table("dialog_assignments").update({"status": "已刪除"}).eq("id", a["id"]).execute()
            _bump_assign()
            st.rerun()


def _teacher_records(ctx, dialogs):
    rows, err = _load_assignments(ctx["sb"], _assign_ver())
    if err:
        _setup_hint(err)
        return
    opts = [None] + [a["id"] for a in rows]
    titles = {a["id"]: a.get("title") or f"#{a['id']}" for a in rows}
    aid = st.selectbox("指派", opts, key="dlg_r_pick",
                       format_func=lambda i: "🧪 老師試玩紀錄" if i is None else f"#{i}｜{titles.get(i, '')}")
    if st.button("🔄 重新整理", key="dlg_r_reload"):
        st.session_state.pop("dlg_r_urls", None)
    sb = ctx["sb"]()
    try:
        q = sb.table("dialog_logs").select("*").order("created_at", desc=True).limit(2000)
        q = q.is_("assign_id", "null") if aid is None else q.eq("assign_id", aid)
        data = q.execute().data or []
    except Exception as e:
        _setup_hint(f"{type(e).__name__}: {e}")
        return
    if not data:
        st.info("還沒有練習紀錄。")
        return
    df = pd.DataFrame(data)
    df["有錄音"] = df["audio_path"].fillna("").astype(str).str.len() > 0
    summ = df.groupby("name").agg(
        練習句數=("id", "count"),
        說對了=("self_check", lambda s: int((s == "✅").sum())),
        再練=("self_check", lambda s: int((s == "🔁").sum())),
        錄音=("有錄音", "sum"),
        最後練習=("created_at", "max"),
    ).reset_index().rename(columns={"name": "姓名"}).sort_values("再練", ascending=False)
    summ["最後練習"] = summ["最後練習"].astype(str).str[:16].str.replace("T", " ")
    st.markdown("#### 👩‍🎓 每位學生")
    st.dataframe(summ, use_container_width=True, hide_index=True)

    wrows = []
    for _, r in df.iterrows():
        for kv in str(r.get("words") or "").split(";"):
            if "=" in kv:
                wrows.append({"圖卡": kv.split("=", 1)[1], "self_check": r["self_check"]})
    if wrows:
        wdf = pd.DataFrame(wrows)
        ws = wdf.groupby("圖卡").agg(說對了=("self_check", lambda s: int((s == "✅").sum())),
                                     再練=("self_check", lambda s: int((s == "🔁").sum()))).reset_index()
        st.markdown("#### 🖼️ 哪張圖卡最常「再練」")
        st.dataframe(ws.sort_values("再練", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("#### 🎧 抽聽錄音")
    names = sorted(df["name"].dropna().unique().tolist())
    who = st.selectbox("學生", names, key="dlg_r_who")
    only_again = st.checkbox("只看「再練」", key="dlg_r_again")
    sub = df[(df["name"] == who) & df["有錄音"]]
    if only_again:
        sub = sub[sub["self_check"] == "🔁"]
    sub = sub.head(30)
    d_map = {did: dd for did, dd in dialogs.items()}
    if sub.empty:
        st.caption("沒有錄音")
        return
    if st.button(f"▶️ 載入 {len(sub)} 段錄音", key="dlg_r_load"):
        st.session_state["dlg_r_urls"] = {r["audio_path"]: _signed_url(sb, r["audio_path"]) for _, r in sub.iterrows()}
    urls = st.session_state.get("dlg_r_urls", {})
    for _, r in sub.iterrows():
        dd = d_map.get(r.get("dialog_id"))
        line = ""
        if dd:
            t = next((t for t in dd["turns"] if t["turn"] == r.get("turn_no")), None)
            if t:
                combo = {}
                for kv in str(r.get("words") or "").split(";"):
                    if "=" in kv:
                        s, w = kv.split("=", 1)
                        combo[s] = {"en": w, "zh": ""}
                line = _fill(t["en"], combo, "en", "plain")
        st.markdown(f"{r['self_check']} **{html.escape(str(r.get('stage','')))}** 第 {r.get('round_no')} 輪｜"
                    f"{html.escape(line)}　<span style='color:#888;font-size:.8rem'>{str(r['created_at'])[:16].replace('T',' ')}</span>",
                    unsafe_allow_html=True)
        u = urls.get(r["audio_path"])
        if u:
            st.audio(u)


def _teacher_setup():
    st.markdown("""
**一次性設定（只要做一次）**
1. 到 Supabase 專案 → 左邊 **SQL Editor** → **New query**，把下面整段貼上，按 **Run**。
2. 會建立 3 張資料表（圖卡、指派、練習紀錄）和 2 個儲存空間（`flashcards` 圖卡、`dialog_audio` 錄音）。

**自己加對話（Google 試算表，可選）**
- 新增工作表 **對話範本**，欄位：`對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文`
  - 一列一句；要替換的地方寫 `{欄位名}`，例如 `It's {weather} today.`、中文 `今天{weather}。`
  - 角色填 A 或 B；角色名稱（例如 Amy）同一段寫一次就好。
- 新增工作表 **替換字**，欄位：`對話ID｜欄位｜英文｜中文｜圖｜圖片描述`
  - 英文寫放進句子後的完整片語（`an apple`、`apples`），a/an、單複數才會對。
  - 圖：可留空、填 emoji、或貼圖片網址；之後在「🖼️ 對話與圖卡」上傳或 AI 產生會覆蓋。
  - 圖片描述：給 AI 畫圖用的英文說明（例如 `a dad holding a child`），留空就用英文單字。
- 沒建這兩張表也能用內建的 **D00 天氣示範**。
""")
    st.code(SETUP_SQL, language="sql")
