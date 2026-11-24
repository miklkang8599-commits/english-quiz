# ==============================================================================
# 🗣️ 對話練習（替換字＋圖卡）模組 — 英文全能練習系統 V2.9.555 起
# ==============================================================================
# 一段固定對話，句中 {欄位} 換成不同單字（每個單字一張圖卡）反覆練習。
# 學生：測驗 → 全文示範 → 看圖練習說，每句可錄音，自己勾「說對了／再練」（不自動評分）。
# 老師：圖卡管理（上傳圖片／AI 產生）、指派（選對話、勾圖卡、輪數）、學生紀錄（抽聽錄音）。
#
# 資料：
#   Google Sheets「對話範本」：對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文
#                            （選填 V2.9.558：情境｜角色描述 → 給 AI 畫背景與角色立繪）
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

DLG_VERSION = "2.9.578"   # 只改這個模組時，老師端「🗣️ 對話練習」最上面會顯示這個版本

# ------------------------------------------------------------------------------
# 內建示範對話
# ------------------------------------------------------------------------------
DEMO_ID = "D00"
DEMO_DIALOG = {
    "title": "天氣（示範）",
    "level": "國小",
    "names": {"A": "Amy", "B": "Ben"},
    # V2.9.558 情境畫面：背景（不含人物）＋兩位角色立繪
    "scene_desc": "the front gate of a Taiwanese elementary school on a weekday morning, "
                  "trees, a wide sidewalk, school building behind the gate, open sky",
    "char_desc": {
        "A": "Amy, a cheerful elementary school girl with a black ponytail, white school shirt, "
             "navy blue skirt, red backpack",
        "B": "Ben, a friendly elementary school boy with short black hair, white school T-shirt, "
             "navy blue shorts, blue backpack",
    },
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

# V2.9.565 關卡順序：先測驗，再看全文示範，最後看圖練習說
STAGE_TEST, STAGE_DEMO, STAGE_PIC = "① 測驗", "② 全文示範", "③ 看圖練習說"
STAGES = [STAGE_TEST, STAGE_DEMO, STAGE_PIC]
_OLD_STAGE = {"① 跟讀": STAGE_DEMO, "① 全文示範": STAGE_DEMO, "② 看圖說": STAGE_PIC, "③ 角色對話": STAGE_TEST}


def _norm_stage(s):
    """舊指派／舊練習裡的關卡名稱換成目前的名稱"""
    s = str(s).strip()
    return _OLD_STAGE.get(s, s)


STAGE_HELP = {
    STAGE_TEST: "測驗：對方只出聲音；輪到你時只看中文提示，說出英文。",
    STAGE_DEMO: "按場景裡的 ▶️，兩位角色把整段對話演一遍；點下面任一句可以單獨再聽。換下一輪會換一組單字。",
    STAGE_PIC: "看圖練習說：替換字變成圖卡，看圖自己說出完整句子，錄完按「看答案」對照。",
}
# V2.9.564 ② ③ 的進行方式：整篇連播（簡單）＝從頭播放，輪到你就停下來錄音，按「繼續」播到下一個錄音點
FLOWS = ["🎬 整篇連播（簡單）", "🧩 逐句練習"]
AVATARS = ["🧒", "👧", "👦", "🧑", "🐶", "🐱", "🐼", "🦊", "🐰", "🐯", "🐸", "🤖"]
VOICE = {"A": "nova", "B": "onyx"}
IMG_STYLE = ("A cute, simple cartoon flashcard illustration for young English learners. "
             "Single clear subject, centered, thick clean outlines, bright friendly colors, "
             "plain white background. No text, no letters, no words, no numbers.")
# V2.9.558 情境畫面：半寫實繪本／動畫電影風（比照片級寫實更能維持同一角色長相）
SCENE_STYLE = ("A semi-realistic illustration in the style of a modern animated film or picture book, "
               "soft natural lighting, warm friendly colors, detailed but clean, eye-level wide view. "
               "No text, no letters, no signs with words.")
SCENE_TAIL = (" Background scene only: no people, no animals. Leave open ground on the lower left "
              "and lower right for characters to stand.")
CHAR_STYLE = ("A semi-realistic character illustration in the style of a modern animated film, "
              "soft lighting, friendly natural expression. Full body, standing, whole figure visible "
              "from head to shoes, three-quarter view with the body turned toward the viewer's right. "
              "Transparent background, no ground, no shadow, no other objects. No text.")
# V2.9.559 卡通畫風（預設）：鮮豔、生動，像兒童動畫影集
SCENE_CARTOON = ("A vibrant 2D cartoon background illustration in the style of a modern kids' animated TV series, "
                 "bold clean outlines, bright saturated colors, playful simple shapes, cheerful mood, eye-level wide view. "
                 "No text, no letters, no signs with words.")
CHAR_CARTOON = ("A cute, lively 2D cartoon character in the style of a modern kids' animated TV series, "
                "big expressive eyes, big friendly smile, bold clean outlines, bright saturated colors, "
                "energetic pose with one hand waving. Full body, standing, whole figure visible from head to shoes, "
                "three-quarter view with the body turned toward the viewer's right. "
                "Transparent background, no ground, no shadow, no other objects. No text.")
STYLE_SETS = {"🎨 卡通（生動）": (SCENE_CARTOON, CHAR_CARTOON), "🖼️ 半寫實": (SCENE_STYLE, CHAR_STYLE)}

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
.dlg-stage{position:relative;width:100%;aspect-ratio:3/2;max-height:380px;border-radius:16px;overflow:hidden;
  margin:.3rem 0 .7rem;background:#cfe8ff center/cover no-repeat}
.dlg-ch{position:absolute;bottom:0;height:86%;width:38%;display:flex;justify-content:center;align-items:flex-end}
.dlg-ch.l{left:2%}
.dlg-ch.r{right:2%}
.dlg-ch .fig{height:82%;display:flex;align-items:flex-end;justify-content:center;
  transform-origin:50% 100%;animation:dlg-idle 2.6s ease-in-out infinite}
.dlg-ch.r .fig{animation-delay:-1.3s}
.dlg-ch.act .fig{animation:dlg-talk .55s ease-in-out infinite alternate}
.dlg-ch.dim .fig{filter:brightness(.82) saturate(.85)}
.dlg-ch img{height:100%;width:auto;max-width:100%;object-fit:contain;object-position:bottom;
  filter:drop-shadow(0 6px 8px rgba(0,0,0,.35))}
.dlg-ch.r img{transform:scaleX(-1)}
.dlg-ch .emo{font-size:5rem;line-height:1;margin-bottom:12%}
@keyframes dlg-idle{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-2%) scale(1.01)}}
@keyframes dlg-talk{from{transform:translateY(0) scale(1.04)}to{transform:translateY(-5%) scale(1.07)}}
.dlg-say{position:absolute;top:4%;max-width:56%;background:#fff;color:#111;border:3px solid #222;border-radius:18px;
  padding:.35rem .7rem;font-size:1.02rem;line-height:1.45;font-weight:600;z-index:3;
  box-shadow:0 3px 0 rgba(0,0,0,.25);animation:dlg-pop .35s ease-out}
.dlg-say.l{left:22%}
.dlg-say.r{right:22%}
.dlg-say:after{content:"";position:absolute;bottom:-14px;width:0;height:0;border:8px solid transparent;border-top:12px solid #222}
.dlg-say.l:after{left:14px}
.dlg-say.r:after{right:14px}
@keyframes dlg-pop{from{transform:scale(.6);opacity:0}to{transform:scale(1);opacity:1}}
.dlg-say .dlg-zh{font-weight:400}
.dlg-rec{position:absolute;top:44%;z-index:4;background:#e03131;color:#fff;font-weight:800;border:3px solid #fff;
  border-radius:999px;padding:.25rem .8rem;font-size:1rem;white-space:nowrap;box-shadow:0 3px 0 rgba(0,0,0,.25);
  animation:dlg-blink 1s ease-in-out infinite}
.dlg-rec.l{left:3%}
.dlg-rec.r{right:3%}
.dlg-rec.ok{background:#2f9e44;animation:none}
@keyframes dlg-blink{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}
.dlg-say.prev{opacity:.72;font-size:.85rem;max-width:40%;font-weight:500;border-width:2px;animation:none;z-index:2}
.dlg-stage.nobg{background:linear-gradient(#a9dcff 0%,#e3f4ff 58%,#9be37f 58%,#6fc257 100%)}
.dlg-stage.wp{border-radius:16px 16px 0 0;margin-bottom:0}
.st-key-dlg_panel{background:linear-gradient(#3d5a73,#2c3e50);border-radius:0 0 16px 16px;
  padding:.55rem .75rem .75rem;margin-top:-1rem;box-shadow:0 4px 10px rgba(0,0,0,.18)}
.st-key-dlg_panel .dlg-ph{color:#fff;font-weight:700;font-size:1rem}
.st-key-dlg_panel label p,.st-key-dlg_panel [data-testid="stCaptionContainer"],
.st-key-dlg_panel [data-testid="stCaptionContainer"] p{color:#e9eef3 !important}
.st-key-dlg_panel [data-testid="stAlert"] p{color:inherit !important}
.dlg-fx{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:2}
.dlg-fx .p{position:absolute;top:-12%;animation:dlg-fall linear infinite}
.dlg-fx .drop{width:2px;height:16px;border-radius:2px;background:linear-gradient(rgba(255,255,255,0),rgba(70,130,255,.85))}
.dlg-fx .flake{color:#fff;font-size:15px;text-shadow:0 0 3px rgba(0,0,0,.25)}
.dlg-fx .leaf{position:absolute;left:-12%;font-size:18px;animation:dlg-blow linear infinite}
.dlg-fx .cloud{position:absolute;left:-30%;font-size:46px;opacity:.9;animation:dlg-drift linear infinite}
.dlg-fx .sun{position:absolute;top:3%;left:3%;font-size:46px;animation:dlg-glow 2.4s ease-in-out infinite}
.dlg-fx .tint{position:absolute;inset:0}
@keyframes dlg-fall{from{top:-12%}to{top:108%}}
@keyframes dlg-blow{from{left:-12%;transform:rotate(0)}to{left:112%;transform:rotate(720deg)}}
@keyframes dlg-drift{from{left:-30%}to{left:110%}}
@keyframes dlg-glow{0%,100%{transform:scale(1);filter:drop-shadow(0 0 6px #ffd43b)}50%{transform:scale(1.12);filter:drop-shadow(0 0 18px #ffd43b)}}
.dlg-tag{position:absolute;bottom:6px;left:50%;transform:translateX(-50%);white-space:nowrap;
  background:rgba(0,0,0,.6);color:#fff;border-radius:8px;padding:0 .45rem;font-size:.82rem}
.dlg-sign{position:absolute;bottom:4%;left:50%;transform:translateX(-50%);display:flex;gap:.35rem;z-index:3;
  background:rgba(255,255,255,.9);border-radius:12px;padding:.3rem .5rem;box-shadow:0 2px 6px rgba(0,0,0,.2)}
.dlg-sign .it{text-align:center;color:#111;font-size:.8rem;font-weight:600;line-height:1.2}
.dlg-face{width:2.9rem;height:2.9rem;border-radius:50%;flex:0 0 auto;background:#e7f1ff no-repeat;
  background-size:230%;background-position:50% 3%;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}
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
            # V2.9.558 選填欄：情境（背景描述）、角色描述（立繪描述）
            if _s(r.get("情境")):
                d["scene_desc"] = _s(r.get("情境"))
            if _s(r.get("角色描述")):
                d.setdefault("char_desc", {})[role] = _s(r.get("角色描述"))
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
    # V2.9.566 剛用「AI 產生對話」存檔、試算表快取還沒更新的對話，先放進清單
    for pid, pdlg in (st.session_state.get("dlg_pending") or {}).items():
        if pid not in dialogs:
            dialogs[pid] = json.loads(json.dumps(pdlg, ensure_ascii=False))
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
        # V2.9.558 情境畫面（背景＋兩位角色立繪），圖存在 dialog_cards（欄位 _scene／_char）
        sid = card_id(did, "_scene", "bg")
        d["scene"] = {"id": sid, "slot": "_scene", "en": "bg", "zh": "情境背景", "img": imgs.get(sid, ""),
                      "desc": d.pop("scene_desc", "") or f"an everyday scene for a dialogue about {d['title']}"}
        cdesc = d.pop("char_desc", {}) or {}
        d["chars"] = {}
        for role in ("A", "B"):
            cid = card_id(did, "_char", role)
            nm = d["names"].get(role, role)
            d["chars"][role] = {"id": cid, "slot": "_char", "en": role, "zh": nm, "img": imgs.get(cid, ""),
                                "desc": cdesc.get(role) or f"{nm}, a friendly elementary school student"}
    return dialogs


def _slots_in(dialog):
    """對話裡用到的替換字欄位（{?day} 算在 day 裡）"""
    out = []
    for t in dialog["turns"]:
        for m in _SLOT_RE.finditer(t["en"] + " " + t["zh"]):
            s = _base_slot(m.group(1))
            if s and s not in out:
                out.append(s)
    return out


# V2.9.567 是非問句：
#   問句寫 {?day}：從 {day} 的圖卡裡抽；「是」的輪和 {day} 同一個字，「不是」的輪一定是不同的字（程式篩選）
#   回答用「 || 」分開兩種說法：Yes, it is. || No, it isn't. It's {day}.（中文也一樣）
#   每輪輪流出「是」和「不是」，兩種回答都會練到
def _base_slot(s):
    return str(s).strip().lstrip("?").strip()


def _ask_slots(dialog):
    out = []
    for t in dialog["turns"]:
        for m in _SLOT_RE.finditer(t["en"] + " " + t["zh"]):
            s = m.group(1).strip()
            if s.startswith("?") and s not in out:
                out.append(s)
    return out


def _is_yes(combo_words):
    return all(w == combo_words.get(_base_slot(s)) for s, w in combo_words.items() if str(s).startswith("?"))


def _pick_branch(text, yes):
    if "||" not in (text or ""):
        return text
    a, b = text.split("||", 1)
    if yes:
        return a.strip()
    # 「不是」的說法裡要講真正的答案：寫成 {?day} 也當作 {day}（V2.9.568）
    return re.sub(r"\{\s*\?", "{", b).strip()


def _resolve_turns(turns, combo_words):
    """依這一輪的字，選出「是」或「不是」那一種說法"""
    yes = _is_yes(combo_words)
    return [dict(t, en=_pick_branch(t["en"], yes), zh=_pick_branch(t["zh"], yes)) for t in turns]


def _sign_cards(combo):
    """場景看板只放真正答案的卡（不放問句 {?…} 的卡，免得學生混淆）"""
    return [c for s, c in combo.items() if not str(s).startswith("?")]


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
            # V2.9.572 替換字在句首時第一個字母大寫（his → His）
            if field == "en" and val and re.search(r"(^|[.?!]\s*)$", tpl[:m.start()].strip()):
                val = val[0].upper() + val[1:]
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


# ── V2.9.558 情境畫面 ──
def _url(card):
    v = _s((card or {}).get("img"))
    return v if v.startswith("http") else ""


def has_scene(d):
    return bool(_url(d.get("scene")) or any(_url(c) for c in d.get("chars", {}).values()))


def _face_html(d, role, fallback="🧑"):
    """對話泡泡旁的大頭：有立繪就裁頭部，沒有就用 emoji"""
    u = _url(d.get("chars", {}).get(role))
    if u:
        return f"<div class='dlg-face' style=\"background-image:url('{html.escape(u, quote=True)}')\"></div>"
    return html.escape(fallback)


_FX_WORDS = [  # V2.9.559 天氣特效：單字比對 → 特效
    (r"\brain", "rain"), (r"\bstorm", "rain"), (r"\bsnow", "snow"), (r"\bwind(y|s)?\b", "wind"),
    (r"\bcloud", "cloud"), (r"\bfog", "cloud"), (r"\bsun(ny|shine)?\b", "sun"),
    (r"\bhot\b", "hot"), (r"\bcold\b", "cold"),
]


def _fx_kinds(cards):
    out = []
    for c in cards or []:
        w = str(c.get("en", "")).lower()
        for pat, fx in _FX_WORDS:
            if re.search(pat, w) and fx not in out:
                out.append(fx)
    return out


def _fx_html(kinds):
    if not kinds:
        return ""
    p = []
    for fx in kinds:
        if fx == "rain":
            for i in range(28):
                p.append(f"<span class='p drop' style='left:{(i * 37) % 100}%;"
                         f"animation-duration:{0.55 + (i % 5) * 0.08:.2f}s;animation-delay:-{(i * 0.13) % 1:.2f}s'></span>")
            p.append("<span class='tint' style='background:rgba(40,60,90,.18)'></span>")
        elif fx in ("snow", "cold"):
            n = 22 if fx == "snow" else 10
            for i in range(n):
                p.append(f"<span class='p flake' style='left:{(i * 41) % 100}%;"
                         f"animation-duration:{3 + (i % 4) * 0.7:.1f}s;animation-delay:-{(i * 0.37) % 4:.2f}s'>❄</span>")
            if fx == "cold":
                p.append("<span class='tint' style='background:rgba(120,180,255,.18)'></span>")
        elif fx == "wind":
            for i in range(7):
                p.append(f"<span class='leaf' style='top:{12 + (i * 23) % 60}%;"
                         f"animation-duration:{2.2 + (i % 3) * 0.6:.1f}s;animation-delay:-{i * 0.5:.1f}s'>🍃</span>")
        elif fx == "cloud":
            for i in range(3):
                p.append(f"<span class='cloud' style='top:{2 + i * 9}%;"
                         f"animation-duration:{18 + i * 6}s;animation-delay:-{i * 7}s'>☁️</span>")
            p.append("<span class='tint' style='background:rgba(90,100,110,.12)'></span>")
        elif fx in ("sun", "hot"):
            p.append("<span class='sun'>☀️</span>")
            if fx == "hot":
                p.append("<span class='tint' style='background:rgba(255,120,40,.14)'></span>")
    return f"<div class='dlg-fx'>{''.join(p)}</div>"


def _stage_html(d, cards=None, tags=None, show_text=True, emo=None, active=None, say="",
                prev_role=None, prev_say="", panel=False, rec_role=None, rec_html=""):
    """情境舞台：背景圖＋左右兩位角色立繪（說話的人會動）＋場景內對話泡泡（含上一句）＋天氣特效＋本輪圖卡看板"""
    bg = _url(d.get("scene"))
    style = f" style=\"background-image:url('{html.escape(bg, quote=True)}')\"" if bg else ""
    cls = "dlg-stage" + ("" if bg else " nobg") + (" wp" if panel else "")
    parts = [f"<div class='{cls}'{style}>", _fx_html(_fx_kinds(cards))]
    if prev_role and prev_say:
        parts.append(f"<div class='dlg-say prev {'l' if prev_role == 'A' else 'r'}'>{prev_say}</div>")
    if rec_role and rec_html:   # V2.9.563 輪到學生時，場景裡提示「請錄音」
        parts.append(f"<div class='dlg-rec {'l' if rec_role == 'A' else 'r'}{' ok' if '✅' in rec_html else ''}'>{rec_html}</div>")
    tags = tags or {}
    emo = emo or {"A": "👧", "B": "👦"}
    for role, side in (("A", "l"), ("B", "r")):
        u = _url(d.get("chars", {}).get(role))
        fig = (f"<img src='{html.escape(u, quote=True)}' alt=''>" if u
               else f"<span class='emo'>{html.escape(emo.get(role, '🧑'))}</span>")
        tag = tags.get(role) or d["names"].get(role, role)
        st_cls = "" if not active else (" act" if role == active else " dim")
        parts.append(f"<div class='dlg-ch {side}{st_cls}'><div class='fig'>{fig}</div>"
                     f"<span class='dlg-tag'>{html.escape(tag)}</span></div>")
    if active and say:
        parts.append(f"<div class='dlg-say {'l' if active == 'A' else 'r'}'>{say}</div>")
    if cards:
        its = []
        for c in cards:
            txt = f"<div>{html.escape(c['en'])}</div>" if show_text else ""
            its.append(f"<div class='it'>{_img_html(c, 46)}{txt}</div>")
        parts.append(f"<div class='dlg-sign'>{''.join(its)}</div>")
    parts.append("</div>")
    return "".join(parts)


@st.cache_data(show_spinner=False, max_entries=600)
def _tts(text, voice, speed):
    # 失敗會丟例外（不快取失敗結果），由 _play 接住
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    return cl.audio.speech.create(model="tts-1", voice=voice, input=text, speed=speed).content


def _play(text, role, speed, autoplay=False):
    try:
        audio = _tts(text, VOICE.get(role, "nova"), speed)
    except Exception:
        audio = None
    if audio:
        try:
            st.audio(audio, format="audio/mp3", autoplay=autoplay)
        except TypeError:          # 舊版 Streamlit 沒有 autoplay
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
def _make_combos(sel, n, asks=()):
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
    combos = [{s: cols[s][i] for s in cols} for i in range(n)]
    # V2.9.567 不同欄位但圖卡重疊時（例如 {day} 和 {day2}），同一輪不要抽到同一個字
    for cb in combos:
        used = []
        for s in list(cb):
            if cb[s] in used:
                left = [w for w in sel.get(s, []) if w not in used]
                if left:
                    cb[s] = random.choice(left)
            used.append(cb[s])
    # 是非問句 {?x}：輪流出「是」（同一個字）和「不是」（一定不同的字）
    off = random.randint(0, 1)
    for i, cb in enumerate(combos):
        for q in asks:
            b = _base_slot(q)
            if b not in cb:
                continue
            others = [w for w in sel.get(b, []) if w != cb[b]]
            cb[q] = cb[b] if (i + off) % 2 == 0 or not others else random.choice(others)
    return combos


def _start_run(dialog_id, dialog, sel, rounds, stages, assign_id=None, title=""):
    stages = [_norm_stage(x) for x in stages]  # 舊指派相容
    allc = {s: [c["en"] for c in dialog["cards"].get(s, [])] for s in _slots_in(dialog)}
    sel = {s: (sel.get(s) or allc.get(s, [])) for s in allc}
    for k in [k for k in st.session_state.keys() if str(k).startswith(("dlg_rec_", "dlg_stage"))]:
        st.session_state.pop(k, None)
    st.session_state["dlg_run"] = {
        "assign_id": assign_id, "dialog_id": dialog_id, "title": title or dialog["title"],
        "sel": sel, "rounds": max(1, int(rounds)), "stages": [x for x in STAGES if x in stages] or STAGES[:],
        "combos": _make_combos(sel, max(1, int(rounds)), _ask_slots(dialog)), "avatar": None, "role": None,
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

    # V2.9.562：更新前就開始的練習可能還記著舊關卡名稱（① 跟讀），換成目前的名稱
    run["stages"] = [x for x in STAGES if x in [_norm_stage(s) for s in run["stages"]]] or STAGES[:]
    if st.session_state.get("dlg_stage") in _OLD_STAGE:
        st.session_state["dlg_stage"] = _norm_stage(st.session_state["dlg_stage"])
    if run.get("goto_stage"):
        # 不能在 radio 畫出來之後才改它的值，所以下一關的切換放在這裡（畫 radio 之前）
        st.session_state["dlg_stage"] = run.pop("goto_stage")
    if st.session_state.get("dlg_stage") not in run["stages"]:
        st.session_state["dlg_stage"] = run["stages"][0]
    c1, c2 = st.columns([3, 2])
    stage = c1.radio("關卡", run["stages"], horizontal=True, key="dlg_stage")
    speed_lbl = c2.radio("語速", ["正常", "慢速"], horizontal=True, key="dlg_speed")
    speed = 1.0 if speed_lbl == "正常" else 0.75
    st.caption("💡 " + STAGE_HELP.get(stage, ""))

    n = run["rounds"]
    rno = min(run["round"], n - 1)
    combo_words = run["combos"][rno]
    combo = {s: by_en.get(_base_slot(s), {}).get(w, {"en": w, "zh": "", "img": "", "slot": _base_slot(s)})
             for s, w in combo_words.items()}
    d = dict(d, turns=_resolve_turns(d["turns"], combo_words))   # V2.9.567 是非問句選「是／不是」的說法
    turns = d["turns"]

    # V2.9.563：① 全文示範不用選角色，一開始就直接看示範
    if stage == STAGE_DEMO:
        _render_demo(d, run, combo, run.get("role"), names, speed, rno, n, ctx, combo_words)
        return

    # ── ② ③ 才選角色 ──
    both_chars = all(_url(d.get("chars", {}).get(r)) for r in ("A", "B"))
    if not run.get("avatar") or not run.get("role"):
        st.markdown(_stage_html(d), unsafe_allow_html=True)
        if both_chars:
            av = "🧑"   # 兩位角色都有立繪：不用另外選頭像
        else:
            st.markdown("#### 1️⃣ 選一個你的頭像")
            av = st.radio("頭像", AVATARS, horizontal=True, key="dlg_av_pick", label_visibility="collapsed")
        st.markdown("#### 👇 點選你要演的角色" if both_chars else "#### 2️⃣ 點選你要演的角色")
        for col, r in zip(st.columns(2), ("A", "B")):
            lbl = f"🙋 我演 {names[r]}" + ("（先開口）" if turns and turns[0]["role"] == r else "")
            if col.button(lbl, key=f"dlg_pick_{r}", type="primary", use_container_width=True):
                run["avatar"], run["role"] = av, r
                st.rerun()
        return

    me = run["role"]
    other = "B" if me == "A" else "A"
    partner_av = AVATARS[(AVATARS.index(run["avatar"]) + 4) % len(AVATARS)] if run["avatar"] in AVATARS else "🧑"
    f1, f2, f3 = st.columns([3, 1.4, 1.4])
    flow = f1.radio("進行方式", FLOWS, horizontal=True, key="dlg_flow")
    for col, r in ((f2, "A"), (f3, "B")):    # V2.9.565 角色直接點選切換
        if col.button(("✅ " if r == me else "") + f"演 {names[r]}", key=f"dlg_role_{r}", disabled=r == me,
                      type="primary" if r == me else "secondary", use_container_width=True):
            run["role"] = r
            run["step"], run["fpos"] = {}, {}
            st.rerun()

    # V2.9.560 場景播放器：一次演一句，A／B 的對話都出現在場景裡，操作按鈕在場景下方的面板
    sk = f"{stage}|{rno}"
    steps = run.setdefault("step", {})
    i = max(0, min(int(steps.get(sk, 0)), len(turns)))      # i == len(turns)：這一輪演完

    def line_html(t):
        k_ = f"{stage}|{rno}|{t['turn']}"
        mine_ = t["role"] == me
        if stage == STAGE_DEMO or run["reveal"].get(k_):
            out = _fill(t["en"], combo, "en", "mark")
            if stage == STAGE_DEMO and t["zh"]:
                out += f"<div class='dlg-zh'>{_fill(t['zh'], combo, 'zh', 'mark')}</div>"
            return out
        if stage == STAGE_PIC:
            return _fill(t["en"], combo, "en", "blank" if mine_ else "mark")
        if mine_:
            zh_ = _fill(t["zh"], combo, "zh", "blank") if t["zh"] else ""
            return "🎤 換你說！" + (f"<div class='dlg-zh'>{zh_}</div>" if zh_ else "")
        return "🔊 ……"

    if flow == FLOWS[0]:
        _render_flow(ctx, d, run, stage, combo, combo_words, me, names, speed, rno, n, line_html,
                     tags={me: f"{names[me]}（你）", other: names[other]},
                     emo={me: run["avatar"], other: partner_av})
        return
    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪")

    cur = turns[i] if i < len(turns) else None
    if cur is not None:
        active, say = cur["role"], line_html(cur)
    else:
        active, say = me, "🎉 這一輪完成！"
    prev = turns[i - 1] if i >= 1 and cur is not None else None
    prev_role = prev["role"] if prev and prev["role"] != active else None
    rec_html = ""
    if cur is not None and cur["role"] == me:
        _k = f"{stage}|{rno}|{cur['turn']}"
        if st.session_state.get(f"dlg_rec_{_k}") is not None:
            rec_html = "✅ 錄好了！按下面自評 ⬇"
        else:
            rec_html = "🎙️ 請錄音 ⬇"
    st.markdown(_stage_html(d, _sign_cards(combo),
                            tags={me: f"{names[me]}（你）", other: names[other]},
                            show_text=(stage == STAGE_DEMO),
                            emo={me: run["avatar"], other: partner_av},
                            active=active, say=say,
                            prev_role=prev_role, prev_say=line_html(prev) if prev_role else "",
                            panel=True, rec_role=me if rec_html else None, rec_html=rec_html),
                unsafe_allow_html=True)

    def go(step):
        steps[sk] = max(0, min(step, len(turns)))
        st.rerun()

    with st.container(key="dlg_panel"):
        if cur is not None:
            k = f"{stage}|{rno}|{cur['turn']}"
            mine = cur["role"] == me
            revealed = run["reveal"].get(k, False)
            plain = _fill(cur["en"], combo, "en", "plain")
            played = run.setdefault("played", [])
            first_show = k not in played
            if first_show:
                played.append(k)
            who = "🎤 輪到你說" if mine else f"👂 聽 {names[cur['role']]} 說"
            st.markdown(f"<div class='dlg-ph'>第 {i + 1} / {len(turns)} 句｜{html.escape(who)}</div>",
                        unsafe_allow_html=True)
            if not mine:
                _play(plain, cur["role"], speed, autoplay=first_show)
                c1, c2, c3 = st.columns(3)
                if c1.button("⬅️ 上一句", key=f"dlg_pv_{k}", disabled=i == 0, use_container_width=True):
                    go(i - 1)
                if stage == STAGE_TEST and not revealed:
                    if c2.button("📝 顯示文字", key=f"dlg_rv_{k}", use_container_width=True):
                        run["reveal"][k] = True
                        st.rerun()
                if c3.button("下一句 ➡️", key=f"dlg_nx_{k}", type="primary", use_container_width=True):
                    go(i + 1)
            else:
                if stage == STAGE_DEMO or revealed:
                    _play(plain, cur["role"], speed, autoplay=first_show and stage == STAGE_DEMO)
                rec = st.audio_input("🎙️ 錄下你說的這一句", key=f"dlg_rec_{k}")
                done = run["checks"].get(k)
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("⬅️ 上一句", key=f"dlg_pv_{k}", disabled=i == 0, use_container_width=True):
                    go(i - 1)
                if stage != STAGE_DEMO and not revealed:
                    if c2.button("👀 看答案", key=f"dlg_ans_{k}", use_container_width=True):
                        run["reveal"][k] = True
                        st.rerun()
                if c3.button("✅ 說對了", key=f"dlg_ok_{k}", use_container_width=True,
                             type="primary" if done == "✅" else "secondary"):
                    if _save_log(ctx, run, stage, rno + 1, cur["turn"], combo_words, "✅", rec.getvalue() if rec else None):
                        run["checks"][k] = "✅"
                        go(i + 1)
                    st.rerun()
                if c4.button("🔁 再練", key=f"dlg_again_{k}", use_container_width=True,
                             type="primary" if done == "🔁" else "secondary"):
                    if _save_log(ctx, run, stage, rno + 1, cur["turn"], combo_words, "🔁", rec.getvalue() if rec else None):
                        run["checks"][k] = "🔁"
                        go(i + 1)
                    st.rerun()
                if done:
                    st.caption(f"已記錄：{done}（再按一次會再記一筆）")
        else:
            rk = [v for kk, v in run["checks"].items() if kk.startswith(f"{sk}|")]
            st.markdown(f"<div class='dlg-ph'>🎉 第 {rno + 1} 輪完成！✅ {rk.count('✅')}　🔁 {rk.count('🔁')}</div>",
                        unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if c1.button("🔁 這一輪再演一次", key=f"dlg_again_round_{sk}", use_container_width=True):
                go(0)
            if c2.button("⬅️ 上一句", key=f"dlg_pv_end_{sk}", use_container_width=True):
                go(len(turns) - 1)
            if rno < n - 1:
                if c3.button("下一輪 ➡️", key="dlg_next", type="primary", use_container_width=True):
                    run["round"] = rno + 1
                    st.rerun()
            else:
                nxt = run["stages"].index(stage) + 1
                if nxt < len(run["stages"]):
                    if c3.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_next_stage", type="primary",
                                 use_container_width=True):
                        run["goto_stage"] = run["stages"][nxt]
                        run["round"] = 0
                        st.rerun()
                else:
                    sc = [v for kk, v in run["checks"].items()]
                    c3.success(f"🏁 全部完成！✅ {sc.count('✅')}　🔁 {sc.count('🔁')}")

    with st.expander("📜 這一輪的整段對話"):
        for j, t in enumerate(turns):
            mark = "▶️ " if j == i else ""
            st.markdown(f"{mark}**{html.escape(names.get(t['role'], t['role']))}**："
                        f"{line_html(t) if j < i or stage == STAGE_DEMO else '……'}", unsafe_allow_html=True)
    if rno > 0:
        if st.button("⬅️ 回上一輪", key="dlg_prev"):
            run["round"] = rno - 1
            st.rerun()


# ── V2.9.561 ① 全文示範：場景自動演完整段對話（瀏覽器端播放，控制鈕在場景裡） ──
_DEMO_CSS = """<style>
html,body{margin:0;padding:0;background:transparent;font-family:"Source Sans Pro",system-ui,sans-serif}
.dlg-stage{margin:0 !important}
.dm-start{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:6;
  background:rgba(0,0,0,.18);cursor:pointer}
.dm-start span{background:#ff922b;color:#fff;font-size:1.25rem;font-weight:800;padding:.6rem 1.3rem;border-radius:999px;
  border:3px solid #fff;box-shadow:0 4px 0 rgba(0,0,0,.25);animation:dm-pulse 1.2s ease-in-out infinite}
@keyframes dm-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
.dm-ctrl{position:absolute;right:8px;top:8px;display:flex;gap:6px;z-index:5}
.dm-ctrl button{border:2px solid #222;background:#fff;border-radius:999px;width:38px;height:38px;font-size:17px;
  cursor:pointer;box-shadow:0 2px 0 rgba(0,0,0,.25);padding:0}
.dm-ctrl button.main{background:#ffd43b;width:46px}
.dm-cnt{position:absolute;left:8px;top:8px;z-index:5;background:rgba(0,0,0,.55);color:#fff;border-radius:999px;
  padding:.1rem .6rem;font-size:.85rem}
.dlg-say.mid{left:30%}
.dm-tr{margin-top:.5rem}
.dm-row{display:flex;gap:.5rem;align-items:flex-start;padding:.35rem .5rem;border-radius:10px;cursor:pointer;
  font-size:1.02rem;line-height:1.5;color:#222}
.dm-row:hover{background:#f1f3f5}
.dm-row.on{background:#fff3bf}
.dm-row .nm{font-weight:700;min-width:3.2rem;color:#1c7ed6}
.dm-row .nm.B{color:#e8590c}
.dm-row .zh{font-size:.88rem;color:#666}
</style>"""


def _demo_html(d, combo, tags, emo, speed):
    import base64
    lines, rows = [], []
    for j, t in enumerate(d["turns"]):
        plain = _fill(t["en"], combo, "en", "plain")
        try:
            a = "data:audio/mp3;base64," + base64.b64encode(_tts(plain, VOICE.get(t["role"], "nova"), speed)).decode()
        except Exception:
            a = ""
        en_html = _fill(t["en"], combo, "en", "mark")
        zh_html = _fill(t["zh"], combo, "zh", "mark") if t["zh"] else ""
        bub = en_html + (f"<div class='dlg-zh'>{zh_html}</div>" if zh_html else "")
        lines.append({"r": t["role"], "h": bub, "a": a})
        nm = html.escape(d["names"].get(t["role"], t["role"]))
        rows.append(f"<div class='dm-row' id='r{j}' onclick='one({j})'><span class='nm {t['role']}'>{nm}</span>"
                    f"<div><div>{en_html}</div><div class='zh'>{zh_html}</div></div></div>")
    stage = _stage_html(d, _sign_cards(combo), tags=tags, show_text=True, emo=emo)
    data = json.dumps(lines, ensure_ascii=False).replace("</", "<\\/")
    js = """<script>
const L=__DATA__;
const S=document.querySelector('.dlg-stage');
const CH={A:S.querySelector('.dlg-ch.l'),B:S.querySelector('.dlg-ch.r')};
const say=document.createElement('div');say.style.display='none';S.appendChild(say);
const pv=document.createElement('div');pv.style.display='none';S.appendChild(pv);
const cnt=document.createElement('div');cnt.className='dm-cnt';cnt.textContent='全文示範';S.appendChild(cnt);
const ctl=document.createElement('div');ctl.className='dm-ctrl';
ctl.innerHTML="<button title='重來' onclick='restart()'>⏮</button><button title='上一句' onclick='one(Math.max(0,i-1))'>⏪</button>"+
 "<button class='main' id='pp' title='播放／暫停' onclick='toggle()'>▶️</button><button title='下一句' onclick='one(Math.min(L.length-1,i+1))'>⏩</button>";
S.appendChild(ctl);
const st=document.createElement('div');st.className='dm-start';st.innerHTML='<span>▶️ 播放全文示範</span>';
st.onclick=()=>{st.remove();restart();};S.appendChild(st);
const au=new Audio();let i=-1,playing=false,tm=null;
function pop(el){el.style.animation='none';void el.offsetWidth;el.style.animation='';}
function show(k){
  i=k;
  for(const r of ['A','B']){CH[r].classList.remove('act','dim');if(k>=0&&k<L.length)CH[r].classList.add(L[k].r===r?'act':'dim');}
  document.querySelectorAll('.dm-row').forEach((e,n)=>e.classList.toggle('on',n===k));
  if(k>=L.length){say.className='dlg-say mid';say.innerHTML='🎉 示範完畢！再按 ⏮ 可以重看';say.style.display='';pv.style.display='none';pop(say);cnt.textContent='全文示範';return;}
  const side=L[k].r==='A'?'l':'r';
  say.className='dlg-say '+side;say.innerHTML=L[k].h;say.style.display='';pop(say);
  if(k>0&&L[k-1].r!==L[k].r){pv.className='dlg-say prev '+(L[k-1].r==='A'?'l':'r');pv.innerHTML=L[k-1].h;pv.style.display='';}
  else pv.style.display='none';
  cnt.textContent='第 '+(k+1)+' / '+L.length+' 句';
}
function upd(){document.getElementById('pp').textContent=playing?'⏸':'▶️';}
function sound(k){clearTimeout(tm);au.pause();if(L[k].a){au.src=L[k].a;au.play().catch(()=>{});}else{tm=setTimeout(()=>au.onended(),2500);}}
function play(k){show(k);if(k>=L.length){playing=false;upd();return;}sound(k);}
au.onended=()=>{if(playing)tm=setTimeout(()=>play(i+1),450);};
function restart(){const s=document.querySelector('.dm-start');if(s)s.remove();playing=true;upd();play(0);}
function one(k){const s=document.querySelector('.dm-start');if(s)s.remove();playing=false;upd();show(k);sound(k);}
function toggle(){const s=document.querySelector('.dm-start');if(s)s.remove();
  if(playing){playing=false;au.pause();clearTimeout(tm);}
  else{playing=true;if(i<0||i>=L.length)play(0);else if(au.src&&au.paused&&!au.ended&&au.currentTime>0)au.play();else play(i);}
  upd();}
</script>""".replace("__DATA__", data)
    return (_CSS + _DEMO_CSS + stage + f"<div class='dm-tr'>{''.join(rows)}</div>" + js)


def _demo_log(ctx, run, rno, combo_words):
    """V2.9.574 ② 全文示範看完一輪 → 記一筆「🎬」（回合 0，每輪只記一次）"""
    if ctx is None:
        return
    done = run.setdefault("demo_logged", [])
    if rno in done:
        return
    if _save_log(ctx, run, STAGE_DEMO, rno + 1, 0, combo_words or {}, "🎬", None):
        done.append(rno)


def _render_demo(d, run, combo, me, names, speed, rno, n, ctx=None, combo_words=None):
    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪（每輪換一組單字）")
    tags = {r: names[r] + ("（你）" if r == me else "") for r in ("A", "B")}
    page = _demo_html(d, combo, tags=tags, emo=None, speed=speed)
    try:
        import streamlit.components.v1 as components
        components.html(page, height=410 + 64 * len(d["turns"]), scrolling=False)
    except Exception as e:
        st.error(f"示範畫面無法顯示：{type(e).__name__}: {e}")
    c1, c2, c3 = st.columns(3)
    if c1.button("⬅️ 上一輪", key="dlg_demo_prev", disabled=rno == 0, use_container_width=True):
        run["round"] = rno - 1
        st.rerun()
    if rno < n - 1 and c2.button("🔀 換一組單字（下一輪）", key="dlg_demo_next", use_container_width=True):
        _demo_log(ctx, run, rno, combo_words)
        run["round"] = rno + 1
        st.rerun()
    nxt = run["stages"].index(STAGE_DEMO) + 1 if STAGE_DEMO in run["stages"] else len(run["stages"])
    if nxt < len(run["stages"]) and c3.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_demo_stage", type="primary", use_container_width=True):
        _demo_log(ctx, run, rno, combo_words)
        run["goto_stage"] = run["stages"][nxt]
        run["round"] = 0
        st.rerun()



# ── V2.9.564 整篇連播：從頭播放，輪到學生就停下來錄音，按「繼續」播到下一個錄音點 ──
_FLOW_CSS = """<style>
.dm-tap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:6;
  background:rgba(0,0,0,.18);cursor:pointer}
.dm-tap span{background:#ff922b;color:#fff;font-size:1.2rem;font-weight:800;padding:.55rem 1.2rem;border-radius:999px;
  border:3px solid #fff;box-shadow:0 4px 0 rgba(0,0,0,.25)}
</style>"""


def _flow_html(d, tags, emo, cards, show_text, seg, prev0, stop, pill, play, nonce):
    """seg：這一段要播的對方句子 [{r,h,a}]；prev0：段落開始前的上一句；stop：停下來要學生說的那句 {r,h}"""
    stage = _stage_html(d, cards, tags=tags, show_text=show_text, emo=emo)
    data = json.dumps({"L": seg, "P": prev0, "S": stop, "pill": pill, "play": bool(play), "n": nonce},
                      ensure_ascii=False).replace("</", "<\\/")
    js = """<script>
const D=__DATA__,L=D.L;
const S=document.querySelector('.dlg-stage');
const CH={A:S.querySelector('.dlg-ch.l'),B:S.querySelector('.dlg-ch.r')};
const say=document.createElement('div');say.style.display='none';S.appendChild(say);
const pv=document.createElement('div');pv.style.display='none';S.appendChild(pv);
const cnt=document.createElement('div');cnt.className='dm-cnt';S.appendChild(cnt);
const au=new Audio();let i=-1,tm=null;
function pop(el){el.style.animation='none';void el.offsetWidth;el.style.animation='';}
function act(r){for(const x of ['A','B']){CH[x].classList.remove('act','dim');if(r)CH[x].classList.add(x===r?'act':'dim');}}
function line(cur,prev){
  act(cur.r);say.className='dlg-say '+(cur.r==='A'?'l':'r');say.innerHTML=cur.h;say.style.display='';pop(say);
  if(prev&&prev.r!==cur.r){pv.className='dlg-say prev '+(prev.r==='A'?'l':'r');pv.innerHTML=prev.h;pv.style.display='';}
  else pv.style.display='none';
}
function stopNow(){
  const last=L.length?L[L.length-1]:D.P;
  if(!D.S){act(null);say.className='dlg-say mid';say.innerHTML='🎉 這一輪演完了！';say.style.display='';
    pv.style.display='none';pop(say);cnt.textContent='整篇連播';return;}
  line(D.S,last);
  const rc=document.createElement('div');rc.className='dlg-rec '+(D.S.r==='A'?'l':'r')+(D.pill.indexOf('✅')>=0?' ok':'');
  rc.innerHTML=D.pill;S.appendChild(rc);cnt.textContent='換你說';
}
function tap(){if(document.querySelector('.dm-tap'))return;const t=document.createElement('div');t.className='dm-tap';
  t.innerHTML='<span>▶️ 繼續播放</span>';t.onclick=()=>{t.remove();au.play().catch(()=>{});};S.appendChild(t);}
function next(){
  i++;if(i>=L.length){stopNow();return;}
  line(L[i],i>0?L[i-1]:D.P);cnt.textContent='🔊 播放中';
  if(L[i].a){au.src=L[i].a;au.play().catch(tap);}else{tm=setTimeout(next,2200);}
}
au.onended=()=>{tm=setTimeout(next,450);};
if(D.play&&L.length)next();else stopNow();
</script>""".replace("__DATA__", data)
    return _CSS + _DEMO_CSS + _FLOW_CSS + stage + js


def _render_flow(ctx, d, run, stage, combo, combo_words, me, names, speed, rno, n, line_html, tags, emo):
    import base64
    turns = d["turns"]
    sk = f"{stage}|{rno}"
    fpos = run.setdefault("fpos", {})
    mine_idx = [j for j, t in enumerate(turns) if t["role"] == me]
    q = max(0, min(int(fpos.get(sk, 0)), len(mine_idx)))
    s = mine_idx[q - 1] + 1 if q > 0 else 0
    e = mine_idx[q] if q < len(mine_idx) else len(turns)
    stop_t = turns[e] if e < len(turns) else None
    k = f"{stage}|{rno}|{stop_t['turn']}" if stop_t else ""
    rec_key = f"dlg_frec_{k}"
    has_rec = bool(k) and st.session_state.get(rec_key) is not None
    revealed = bool(k) and run["reveal"].get(k, False)
    want = st.session_state.pop("dlg_fplay", None) == sk
    play = want or not (has_rec or revealed)   # 錄完／看答案後重畫時停在錄音點，不會又從段落開頭播

    st.progress((rno + 1) / n, text=f"第 {rno + 1} / {n} 輪｜錄音點 {min(q + 1, len(mine_idx))} / {len(mine_idx)}")
    seg = []
    for t in turns[s:e]:
        plain = _fill(t["en"], combo, "en", "plain")
        try:
            a = "data:audio/mp3;base64," + base64.b64encode(_tts(plain, VOICE.get(t["role"], "nova"), speed)).decode()
        except Exception:
            a = ""
        seg.append({"r": t["role"], "h": line_html(t), "a": a})
    prev0 = {"r": turns[s - 1]["role"], "h": line_html(turns[s - 1])} if s > 0 else None
    stop = {"r": stop_t["role"], "h": line_html(stop_t)} if stop_t else None
    pill = "✅ 錄好了！按「繼續」⬇" if has_rec else "🎙️ 請錄音 ⬇"
    nonce = run.setdefault("fnonce", 0)
    page = _flow_html(d, tags, emo, _sign_cards(combo), False, seg, prev0, stop, pill, play, nonce)
    try:
        import streamlit.components.v1 as components
        components.html(page, height=395, scrolling=False)
    except Exception as ex:
        st.error(f"場景畫面無法顯示：{type(ex).__name__}: {ex}")

    def replay(new_q):
        run["fnonce"] = nonce + 1
        fpos[sk] = new_q
        st.session_state["dlg_fplay"] = sk
        st.rerun()

    def restart():
        for kk in [x for x in list(st.session_state.keys()) if str(x).startswith(f"dlg_frec_{sk}|")]:
            del st.session_state[kk]
        for kk in [x for x in list(run["reveal"].keys()) if x.startswith(f"{sk}|")]:
            run["reveal"].pop(kk, None)
        replay(0)

    with st.container(key="dlg_panel"):
        if stop_t is not None:
            st.markdown(f"<div class='dlg-ph'>🎙️ 錄音點 {q + 1} / {len(mine_idx)}｜換你說，錄好按「繼續」</div>",
                        unsafe_allow_html=True)
            if revealed:
                _play(_fill(stop_t["en"], combo, "en", "plain"), me, speed)
            rec = st.audio_input("🎙️ 錄下你說的這一句", key=rec_key)
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("⏮ 從頭開始", key=f"dlg_f_top_{k}", use_container_width=True):
                restart()
            if c2.button("🔁 重聽這段", key=f"dlg_f_re_{k}", use_container_width=True):
                replay(q)
            if not revealed and c3.button("👀 看答案", key=f"dlg_f_ans_{k}", use_container_width=True):
                run["reveal"][k] = True
                st.rerun()
            if c4.button("▶️ 繼續", key=f"dlg_f_go_{k}", type="primary", use_container_width=True,
                         disabled=rec is None):
                _save_log(ctx, run, stage, rno + 1, stop_t["turn"], combo_words, "🎙️", rec.getvalue() if rec else None)
                run["checks"][k] = "🎙️"
                replay(q + 1)
            if rec is None:
                st.caption("錄好音，「▶️ 繼續」才會亮起來。沒有麥克風可以按下面略過。")
                if st.button("⏭ 這句先不錄，直接繼續", key=f"dlg_f_skip_{k}"):
                    # V2.9.574 略過也記一筆（沒錄音），學習報告才看得到有練
                    _save_log(ctx, run, stage, rno + 1, stop_t["turn"], combo_words, "⏭", None)
                    replay(q + 1)
        else:
            got = sum(1 for kk in run["checks"] if kk.startswith(f"{sk}|"))
            st.markdown(f"<div class='dlg-ph'>🎉 第 {rno + 1} 輪演完了！錄了 {got} / {len(mine_idx)} 句</div>",
                        unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("⏮ 從頭再來一次", key=f"dlg_f_again_{sk}", use_container_width=True):
                restart()
            if rno < n - 1:
                if c2.button("下一輪 ➡️", key="dlg_f_next", type="primary", use_container_width=True):
                    run["round"] = rno + 1
                    st.session_state["dlg_fplay"] = f"{stage}|{rno + 1}"
                    st.rerun()
            else:
                nxt = run["stages"].index(stage) + 1
                if nxt < len(run["stages"]):
                    if c2.button(f"進入 {run['stages'][nxt]} ➡️", key="dlg_f_next_stage", type="primary",
                                 use_container_width=True):
                        run["goto_stage"] = run["stages"][nxt]
                        run["round"] = 0
                        st.rerun()
                else:
                    sc = list(run["checks"].values())
                    c2.success(f"🏁 全部完成！共錄了 {len(sc)} 句")
    if rno > 0 and st.button("⬅️ 回上一輪", key="dlg_f_prev"):
        run["round"] = rno - 1
        st.rerun()


# ------------------------------------------------------------------------------
# 老師端
# ------------------------------------------------------------------------------
def _gen_image(prompt, size="1024x1024", transparent=False, quality="low", api_key=None):
    import base64
    import openai
    cl = openai.OpenAI(api_key=api_key or st.secrets["OPENAI_API_KEY"])
    last = None
    gkw = {"quality": quality, "size": size}
    if transparent:
        gkw["background"] = "transparent"
    dsize = {"1536x1024": "1792x1024", "1024x1536": "1024x1792"}.get(size, size)
    for model, kw in (("gpt-image-1-mini", gkw),
                      ("gpt-image-1", gkw),
                      ("dall-e-3", {"quality": "standard", "response_format": "b64_json", "size": dsize})):
        try:
            r = cl.images.generate(model=model, prompt=prompt, n=1, **kw)
            b64 = r.data[0].b64_json
            if b64:
                return base64.b64decode(b64), model
        except Exception as e:
            last = e
    raise RuntimeError(f"{type(last).__name__}: {last}")


# V2.9.570 圖卡提示＋中文字卡
_NO_TEXT = " No text, no letters, no words, no numbers."


def _card_prompt(desc, hint=""):
    """老師的額外要求放最後、優先；有要求時不加「不要文字」，老師才能要求在圖上寫中文"""
    hint = _s(hint)
    if not hint:
        return f"{IMG_STYLE} Subject: {desc}."
    return (f"{IMG_STYLE.replace(_NO_TEXT, '')} Subject: {desc}. "
            f"Teacher's extra requirements (follow these exactly; they override the style above): {hint}")


_TC_COLORS = ["#FFE08A", "#BDE7FF", "#C8F2C2", "#FFD1DC", "#E3D4FF", "#FFD8B0", "#D6F0EE", "#F5F0C8"]


def _text_card_svg(text, i=0):
    """中文字卡（不用 AI）：彩色圓角卡片中間寫大大的字，學生一看就懂，又不會看到英文答案"""
    s = _s(text) or "?"
    rows = [s] if len(s) <= 4 else [s[:(len(s) + 1) // 2], s[(len(s) + 1) // 2:]]
    fs = int(min(190, 440 / max(len(r) for r in rows)))
    body = "".join(
        f"<text x='256' y='{256 + (j - (len(rows) - 1) / 2) * fs * 1.15:.0f}' font-size='{fs}' font-weight='700' "
        f"text-anchor='middle' dominant-baseline='central' fill='#222' font-family=\"'Noto Sans TC','Microsoft JhengHei',"
        f"'PingFang TC','Heiti TC',sans-serif\">{html.escape(r)}</text>" for j, r in enumerate(rows))
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512' viewBox='0 0 512 512'>"
            f"<rect x='16' y='16' width='480' height='480' rx='56' fill='{_TC_COLORS[i % len(_TC_COLORS)]}' "
            f"stroke='#333' stroke-width='10'/>{body}</svg>").encode("utf-8")


def _to_png(raw):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    im.thumbnail((512, 512))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _prep_image(raw, kind):
    """回傳 (bytes, 副檔名, content-type)。背景 → JPG 寬 1024；立繪 → 保留透明的 PNG；圖卡 → PNG 512；中文字卡 → SVG"""
    if raw[:5] == b"<svg ":
        return raw, "svg", "image/svg+xml"
    if kind == "scene":
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((1024, 1024))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue(), "jpg", "image/jpeg"
    if kind == "char":
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGBA")
        bb = im.getbbox()          # 裁掉透明留白，人物在舞台上才站得大
        if bb:
            im = im.crop(bb)
        im.thumbnail((420, 640))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png", "image/png"
    return _to_png(raw), "png", "image/png"


def _kind(card):
    return {"_scene": "scene", "_char": "char"}.get(card.get("slot"), "card")


def _gen_spec(card, desc, hint=""):
    """依種類（圖卡／背景／立繪）組出 (prompt, 參數)；hint＝老師的額外要求"""
    k = _kind(card)
    if k != "card" and _s(hint):
        desc = f"{desc}. {_s(hint)}"
    scene_style, char_style = STYLE_SETS.get(st.session_state.get("dlg_style"), next(iter(STYLE_SETS.values())))
    if k == "scene":
        return f"{scene_style} Scene: {desc}.{SCENE_TAIL}", {"size": "1536x1024", "quality": "medium"}
    if k == "char":
        return f"{char_style} Character: {desc}.", {"size": "1024x1536", "transparent": True, "quality": "medium"}
    return _card_prompt(desc, hint), {}


def _gen_for(card, desc, hint=""):
    p, kw = _gen_spec(card, desc, hint)
    return _gen_image(p, **kw)


def _gen_many(ctx, did, items, workers=4):
    """V2.9.575 多張圖同時產生（最多 4 張一起畫），畫好一張就存一張。items＝[(card, desc, hint)]。回傳成功張數"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not items:
        return 0
    key = st.secrets["OPENAI_API_KEY"]
    specs = [(c,) + _gen_spec(c, d, h) for c, d, h in items]   # prompt 在主執行緒組好（要讀畫面狀態）
    bar = st.progress(0.0, text=f"0/{len(specs)}（{min(workers, len(specs))} 張同時畫）")
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_gen_image, p, api_key=key, **kw): c for c, p, kw in specs}
        for i, f in enumerate(as_completed(futs), 1):
            c = futs[f]
            try:
                _save_card_image(ctx, did, c, f.result()[0])
                ok += 1
            except Exception as e:
                st.error(f"{c.get('zh') or c['en']}：{type(e).__name__}: {e}")
            bar.progress(i / len(specs), text=f"{i}/{len(specs)}")
    return ok


def _rerun_frag():
    """V2.9.575 只重畫目前這個分頁（fragment）；不支援時才整頁重跑"""
    from streamlit.errors import StreamlitAPIException
    try:
        st.rerun(scope="fragment")
    except (TypeError, StreamlitAPIException):
        st.rerun()


def _save_card_image(ctx, dialog_id, card, raw):
    sb = ctx["sb"]()
    png, ext, ctype = _prep_image(raw, _kind(card))
    path = f"{re.sub(r'[^A-Za-z0-9_-]', '_', dialog_id)}/{hashlib.md5(card['id'].encode('utf-8')).hexdigest()}.{ext}"
    sb.storage.from_("flashcards").upload(path, png, {"content-type": ctype, "upsert": "true"})
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


# ── V2.9.566 AI 產生對話：貼上課文句型＋單字 → AI 擬一段替換字對話 → 老師修改 → 存進試算表 ──
_GEN_SYS = """You design short dialogue-practice tasks for Taiwanese EFL students.
Given a lesson's target sentence patterns and vocabulary, write ONE natural two-person dialogue (A and B)
that practises the patterns, with swappable words written as {slot} placeholders. Return JSON only:
{"title": "short title in Traditional Chinese",
 "names": {"A": "English first name", "B": "English first name"},
 "scene_desc": "English description of a background place (no people) that fits the dialogue",
 "char_desc": {"A": "English appearance of A: name, age, hair, clothes", "B": "..."},
 "turns": [{"role": "A", "en": "...", "zh": "Traditional Chinese translation"}],
 "slots": {"slot_name": [{"en": "word", "zh": "Traditional Chinese", "img": "one emoji",
                          "desc": "English description of a flashcard picture for this word"}]}}
Rules:
- 4 to 8 turns (unless the user gives a number), A and B alternate, A speaks first. Use the given sentence
  patterns as exactly as possible; every pattern should appear at least once. Keep sentences short and at the
  students' level. No extra small talk beyond the patterns.
- If the user gives a FIXED DIALOGUE, keep exactly those turns (same roles, same English, same order); only
  add "zh", the slots/cards, title, names, scene_desc and char_desc.
- A and B each have at least 2 lines (students may play either role).
- Write {slot_name} (lowercase ascii, e.g. {day}) where a vocabulary word can be swapped. The same
  placeholder must appear in both "en" and "zh" of that turn ("zh" shows the Chinese meaning there).
- Cards for each slot come from the given vocabulary (add closely related words only if fewer than 3 fit).
  Each slot needs at least 3 cards. Each vocabulary line is ONE item, even with a space (e.g. "social studies",
  "ice cream" is one card). Use EVERY vocabulary item that fits a slot; do not leave any out. Words that cannot be swapped (e.g. "today") just stay in the sentences.
- One card is chosen at random for each slot, and the same placeholder always shows the same word in every
  turn. The dialogue must make sense for ANY choice. Different slots never get the same word in one round.
- A slot may start a sentence: write its cards in lowercase (e.g. "his"); the program capitalizes it there.
- If patterns differ only in a pronoun/person word (e.g. his / her, he / she), make that word ONE slot
  (e.g. {who}) whose cards are those words, each with a picture desc showing who it means ("a boy", "a girl"),
  instead of repeating near-identical turns.
- YES/NO QUESTIONS about a swappable word: write the question with {?slot} and the answer as two versions
  joined by " || " (YES version first) in BOTH "en" and "zh". Example:
  {"role": "A", "en": "Is it {?day} today?", "zh": "今天是{?day}嗎？"},
  {"role": "B", "en": "Yes, it is. || No, it isn't. It's {day}.", "zh": "是的，沒錯。 || 不，不是。今天是{day}。"}
  {day} is the real answer (shown to students as a picture); the program makes {?day} the same word in
  "yes" rounds and a DIFFERENT word in "no" rounds, and shows the matching version. {?day} needs no cards
  of its own. If the lesson has yes/no answers like "Yes, it is. / No, it isn't.", practise them this way.
- JSON only, no markdown."""

_GEN_MODELS = ["gpt-4o", "gpt-4o-mini"]


_FIX_RE = re.compile(r"^\s*([ABab])(?:\s*[:：｜]\s*|\s+)(.+?)\s*$")


def _parse_fixed(text):
    """老師直接貼的對話：每行「A⇥句子」或「A: 句子」→ [{role, en}]（V2.9.568）"""
    out = []
    for ln in (text or "").splitlines():
        m = _FIX_RE.match(ln)
        if m:
            en = re.sub(r"\s+", " ", m.group(2))
            if "||" in en:
                a, b = en.split("||", 1)
                en = f"{a.strip()} || {_pick_branch('||' + b, False)}"
            out.append({"role": m.group(1).upper(), "en": en})
    return out


def _apply_fixed(g, fixed):
    """AI 回來後，句子一律換回老師貼的原句（中文照 AI 翻的，句數不同就留空讓老師補）"""
    if not fixed:
        return g
    zh = [t["zh"] for t in g["turns"]] if len(g["turns"]) == len(fixed) else []
    g["turns"] = [{"role": f["role"], "en": f["en"], "zh": zh[i] if zh else ""} for i, f in enumerate(fixed)]
    return g


def _vocab_items(words):
    """V2.9.573 單字表 → 項目（一行一個；同一行用逗號、頓號、分號隔開也可以；「social studies」算一個）"""
    out = []
    for ln in (words or "").splitlines():
        for w in re.split(r"[,，、;；/]", ln):
            w = re.sub(r"\s+", " ", w).strip()
            if w and w.lower() not in [x.lower() for x in out]:
                out.append(w)
    return out


def _missing_vocab(words, slots, turns):
    """V2.9.573 單字表裡、沒做成圖卡也沒出現在句子裡的字"""
    cards = {c["en"].strip().lower() for cs in slots.values() for c in cs}
    text = " ".join(t["en"] for t in turns).lower()
    return [w for w in _vocab_items(words)
            if w.lower() not in cards and not re.search(r"(?<![a-z])" + re.escape(w.lower()) + r"(?![a-z])", text)]


def _ai_dialog(lesson, patterns, words, level, n_turns=0, fixed_text=""):
    import openai
    cl = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    fixed = _parse_fixed(fixed_text)
    user = (f"Lesson: {lesson or '(not given)'}\nStudent level: {level or '國小'}\n\n"
            f"Target sentence patterns:\n{patterns.strip()}\n\nVocabulary (one item per line):\n"
            + "\n".join(f"- {w}" for w in _vocab_items(words)))
    if fixed:
        user += "\n\nFIXED DIALOGUE (keep exactly these turns):\n" + "\n".join(f"{f['role']}: {f['en']}" for f in fixed)
    elif n_turns:
        user += f"\n\nWrite EXACTLY {int(n_turns)} turns."
    last = None
    for model in _GEN_MODELS:
        try:
            r = cl.chat.completions.create(
                model=model, temperature=0.7, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _GEN_SYS}, {"role": "user", "content": user}])
            return _apply_fixed(_norm_gen(json.loads(r.choices[0].message.content)), fixed)
        except Exception as e:
            last = e
    raise RuntimeError(f"{type(last).__name__}: {last}")


def _norm_gen(g):
    """把 AI 回傳的 JSON 整理成固定格式（缺的欄位補空）"""
    g = g if isinstance(g, dict) else {}
    names = g.get("names") or {}
    cdesc = g.get("char_desc") or {}
    out = {"title": _s(g.get("title")),
           "names": {"A": _s(names.get("A")) or "Amy", "B": _s(names.get("B")) or "Ben"},
           "scene_desc": _s(g.get("scene_desc")),
           "char_desc": {"A": _s(cdesc.get("A")), "B": _s(cdesc.get("B"))},
           "turns": [], "slots": {}}
    for t in g.get("turns") or []:
        if isinstance(t, dict) and _s(t.get("en")):
            role = (_s(t.get("role")) or "A").upper()[:1]
            out["turns"].append({"role": role if role in ("A", "B") else "A",
                                 "en": _s(t.get("en")), "zh": _s(t.get("zh"))})
    for slot, cards in (g.get("slots") or {}).items():
        slot = re.sub(r"[^a-z0-9_]", "", str(slot).lower())
        cs = [{"en": _s(c.get("en")), "zh": _s(c.get("zh")), "img": _s(c.get("img")), "desc": _s(c.get("desc"))}
              for c in (cards or []) if isinstance(c, dict) and _s(c.get("en"))]
        if slot and cs:
            out["slots"][slot] = cs
    return out


def _check_gen(g):
    """檢查 AI 擬的對話能不能用，回傳要提醒老師的問題"""
    warn = []
    used = set()
    for n, t in enumerate(g["turns"], 1):
        en_s = set(re.findall(r"\{(\??\w+)\}", t["en"]))
        zh_s = set(re.findall(r"\{(\??\w+)\}", t["zh"]))
        used |= {_base_slot(x) for x in en_s}
        for s in {_base_slot(x) for x in en_s} - set(g["slots"]):
            warn.append(f"第 {n} 句用了 {{{s}}}，但替換字裡沒有這個欄位")
        if t["zh"] and en_s != zh_s:
            warn.append(f"第 {n} 句英文和中文的 {{欄位}} 不一致")
        if t["zh"] and ("||" in t["en"]) != ("||" in t["zh"]):
            warn.append(f"第 {n} 句英文和中文都要用「||」分開「是／不是」兩種說法")
    for s, cs in g["slots"].items():
        if s not in used:
            warn.append(f"替換字欄位 {{{s}}} 沒有出現在對話裡")
        if len(cs) < 2:
            warn.append(f"欄位 {{{s}}} 只有 {len(cs)} 張圖卡，至少要 2 張才能替換")
    if any("||" in t["en"] for t in g["turns"]) and not any("{?" in t["en"] for t in g["turns"]):
        warn.append("有「是／不是」兩種回答（||），但問句沒有用 {?欄位}，程式不知道要比對哪個字")
    roles = [t["role"] for t in g["turns"]]
    if roles.count("A") < 1 or roles.count("B") < 1:
        warn.append("A、B 兩個角色都要有台詞")
    return warn


def _gen_rows(did, level, g):
    """產生要寫進「對話範本」「替換字」兩張表的列"""
    rows_t, seen = [], set()
    for n, t in enumerate(g["turns"], 1):
        first_role = t["role"] not in seen
        seen.add(t["role"])
        rows_t.append({"對話ID": did, "標題": g["title"] if n == 1 else "", "程度": level if n == 1 else "",
                       "回合": n, "角色": t["role"], "角色名稱": g["names"].get(t["role"], t["role"]),
                       "英文": t["en"], "中文": t["zh"], "情境": g["scene_desc"] if n == 1 else "",
                       "角色描述": g["char_desc"].get(t["role"], "") if first_role else ""})
    rows_c = [{"對話ID": did, "欄位": s, "英文": c["en"], "中文": c["zh"], "圖": c["img"], "圖片描述": c["desc"]}
              for s, cs in g["slots"].items() for c in cs]
    return rows_t, rows_c


def _gen_as_dialog(level, g):
    """存檔後、試算表快取還沒更新前，先用這份資料讓對話出現在清單裡"""
    return {"title": g["title"], "level": level, "names": dict(g["names"]),
            "scene_desc": g["scene_desc"], "char_desc": dict(g["char_desc"]),
            "turns": [{"turn": n, "role": t["role"], "en": t["en"], "zh": t["zh"]} for n, t in enumerate(g["turns"], 1)],
            "cards": {s: [dict(c) for c in cs] for s, cs in g["slots"].items()}}


def _gspread_book():
    import gspread
    from google.oauth2.service_account import Credentials
    gs = st.secrets["connections"]["gsheets"]
    info = {"type": "service_account", "project_id": gs["project_id"], "private_key_id": gs["private_key_id"],
            "private_key": gs["private_key"], "client_email": gs["client_email"], "client_id": gs["client_id"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": gs.get("client_x509_cert_url", "")}
    gc = gspread.authorize(Credentials.from_service_account_info(
        info, scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]))
    ref = str(gs["spreadsheet"])
    return gc.open_by_url(ref) if ref.startswith("http") else gc.open_by_key(ref)


def _append_rows(book, title, rows, headers):
    """把 rows（dict）接在工作表最後面；工作表不存在就建立；缺的標題欄補在最右邊"""
    try:
        ws = book.worksheet(title)
    except Exception:
        ws = book.add_worksheet(title=title, rows=200, cols=max(12, len(headers)))
        ws.append_row(headers, value_input_option="RAW")
    head = [str(h).strip() for h in ws.row_values(1)]
    if not any(head):
        head = []
    miss = [h for h in headers if h not in head]
    if miss:
        head = head + miss
        if ws.col_count < len(head):
            ws.add_cols(len(head) - ws.col_count)
        ws.update(values=[head], range_name="A1")
    ws.append_rows([[r.get(h, "") for h in head] for r in rows], value_input_option="RAW")


def _teacher_gen(ctx, dialogs):
    st.markdown("#### 🪄 貼上課文的句型和單字，AI 幫你擬一段替換字對話")
    st.caption("AI 會自己判斷哪些單字可以替換、怎麼排成 A／B 對話，並寫好情境和角色描述（之後可以一鍵畫圖）。產生後可以先修改再存。")
    if st.session_state.get("dlg_gen_msg"):
        st.success(st.session_state.pop("dlg_gen_msg"))
    c1, c2, c3 = st.columns([3, 2, 1])
    lesson = c1.text_input("課名／單元", key="dlg_g_lesson", placeholder="例：Wonder World B05 L03")
    auto_id = re.sub(r"[^A-Za-z0-9]+", "-", lesson).strip("-").upper()[:30]
    did = (c2.text_input("對話ID（空白＝用課名）", key="dlg_g_id", placeholder=auto_id or "例：WW-B05-L03").strip()
           or auto_id)
    level = c3.text_input("程度", value="國小", key="dlg_g_level")
    p1, p2 = st.columns(2)
    pats = p1.text_area("課文句型（一行一句）", height=170, key="dlg_g_pats",
                        placeholder="What day is today?\nIt's Sunday.\nIs it Monday today?\nYes, it is.\nNo, it isn't. It's Tuesday.")
    words = p2.text_area("課文單字（一行一個）", height=170, key="dlg_g_words",
                         placeholder="Sunday\nMonday\nTuesday\n…\nday\ntoday")
    f1, f2 = st.columns([3, 1])
    fixed_text = f1.text_area(
        "指定對話（可空白；有填就照這幾句，AI 只補中文、圖卡和情境）", height=120, key="dlg_g_fixed",
        placeholder="A\tWhat day is today?\nB\tIt's {day}.\nA\tIs it {?day} today?\nB\tYes, it is. || No, it isn't. It's {day}.")
    fixed = _parse_fixed(fixed_text)
    n_turns = f2.number_input("句數（0＝AI 決定）", 0, 12, 4, key="dlg_g_nturns", disabled=bool(fixed))
    if fixed:
        f2.caption(f"照指定對話：{len(fixed)} 句")
    # V2.9.576 按鈕不再「沒填就變灰」：剛打完字直接按，字還沒送出時按鈕是灰的，第一下會被吃掉（看起來沒反應）
    go = st.button("🪄 AI 產生對話" if not st.session_state.get("dlg_gen") else "🔁 重新產生一版",
                   type="primary", key="dlg_g_go")
    if go and not (pats.strip() or fixed):
        st.warning("請先填「課文句型」或「指定對話」。")
    elif go:
        with st.spinner("AI 正在擬對話…（約 10～20 秒）"):
            try:
                st.session_state["dlg_gen"] = _ai_dialog(lesson, pats, words, level, n_turns, fixed_text)
                st.session_state["dlg_gen_n"] = st.session_state.get("dlg_gen_n", 0) + 1
            except Exception as e:
                st.error(f"AI 產生失敗：{type(e).__name__}: {e}")
    g0 = st.session_state.get("dlg_gen")
    if not g0:
        return
    gn = st.session_state.get("dlg_gen_n", 0)

    st.markdown("---")
    st.markdown("##### ✏️ 檢查／修改（表格可以直接改字、加列、刪列）")
    a1, a2, a3 = st.columns([2, 1, 1])
    title = a1.text_input("標題", value=g0["title"] or lesson, key=f"dlg_g_title_{gn}")
    na = a2.text_input("A 角色名字", value=g0["names"]["A"], key=f"dlg_g_na_{gn}")
    nb = a3.text_input("B 角色名字", value=g0["names"]["B"], key=f"dlg_g_nb_{gn}")
    st.caption("對話（句子裡的 {欄位} 會換成下面的替換字；是非問句：問句寫 {?day}，回答寫「Yes, it is. || No, it isn't. It's {day}.」）")
    df_t = st.data_editor(pd.DataFrame(g0["turns"], columns=["role", "en", "zh"]), num_rows="dynamic",
                          use_container_width=True, key=f"dlg_g_turns_{gn}",
                          column_config={"role": st.column_config.SelectboxColumn("角色", options=["A", "B"], required=True, width="small"),
                                         "en": st.column_config.TextColumn("英文", width="large"),
                                         "zh": st.column_config.TextColumn("中文", width="large")})
    st.caption("替換字（每個欄位至少 2～3 張圖卡；「圖」可以放 emoji，之後也能 AI 產生圖片）")
    cards0 = [{"slot": s, **c} for s, cs in g0["slots"].items() for c in cs]
    df_c = st.data_editor(pd.DataFrame(cards0, columns=["slot", "en", "zh", "img", "desc"]), num_rows="dynamic",
                          use_container_width=True, key=f"dlg_g_cards_{gn}",
                          column_config={"slot": st.column_config.TextColumn("欄位", width="small"),
                                         "en": st.column_config.TextColumn("英文"),
                                         "zh": st.column_config.TextColumn("中文"),
                                         "img": st.column_config.TextColumn("圖", width="small"),
                                         "desc": st.column_config.TextColumn("圖片描述（英文，給 AI 畫圖卡）", width="large")})
    with st.expander("🎬 情境與角色描述（給 AI 畫背景和角色立繪，英文）"):
        scene = st.text_area("情境（背景，不含人物）", value=g0["scene_desc"], key=f"dlg_g_scene_{gn}", height=80)
        da = st.text_area(f"A 角色描述", value=g0["char_desc"]["A"], key=f"dlg_g_da_{gn}", height=70)
        db = st.text_area(f"B 角色描述", value=g0["char_desc"]["B"], key=f"dlg_g_db_{gn}", height=70)

    slots = {}
    for r in df_c.to_dict("records"):
        s = re.sub(r"[^a-z0-9_]", "", _s(r.get("slot")).lower())
        if s and _s(r.get("en")):
            slots.setdefault(s, []).append({"en": _s(r.get("en")), "zh": _s(r.get("zh")),
                                            "img": _s(r.get("img")), "desc": _s(r.get("desc"))})
    g = {"title": _s(title) or did, "names": {"A": _s(na) or "A", "B": _s(nb) or "B"},
         "scene_desc": _s(scene), "char_desc": {"A": _s(da), "B": _s(db)}, "slots": slots,
         "turns": [{"role": (_s(r.get("role")) or "A").upper()[:1], "en": _s(r.get("en")), "zh": _s(r.get("zh"))}
                   for r in df_t.to_dict("records") if _s(r.get("en"))]}
    miss = _missing_vocab(words, slots, g["turns"])
    if miss:
        st.warning("⚠️ 單字表裡這些字沒有做成圖卡、也沒出現在句子裡：**" + "、".join(miss)
                   + "**。要練的話，請在上面「替換字」表格最下面加一列（欄位填 subject 之類的欄位名，"
                     "英文、中文填好）；同一組字有兩個欄位（例如 subject、subject2）就兩個欄位都要加。")

    st.markdown("##### 👀 預覽（隨機抽兩輪替換字；有是非問句時，一輪「是」、一輪「不是」）")
    by_w = {s: {c["en"]: c for c in cs} for s, cs in slots.items()}
    asks = _ask_slots({"turns": g["turns"]})
    for pi, cw in enumerate(_make_combos({s: [c["en"] for c in cs] for s, cs in slots.items()}, 2, asks), 1):
        combo = {s: by_w.get(_base_slot(s), {}).get(w, {"en": w, "zh": ""}) for s, w in cw.items()}
        st.caption(f"範例 {pi}" + ("" if not asks else ("（是）" if _is_yes(cw) else "（不是）")))
        for t in _resolve_turns(g["turns"], cw):
            nm = html.escape(g["names"].get(t["role"], t["role"]))
            zh = _fill(t["zh"], combo, "zh", "mark") if t["zh"] else ""
            st.markdown(f"**{t['role']}｜{nm}**：{_fill(t['en'], combo, 'en', 'mark')}"
                        + (f"<span style='color:#888'>　{zh}</span>" if zh else ""), unsafe_allow_html=True)
    warn = _check_gen(g)
    for w in warn:
        st.warning("⚠️ " + w)

    exists = did in dialogs
    if not did:
        st.info("請填「課名／單元」或「對話ID」。")
    elif exists:
        st.error(f"對話ID「{did}」已經存在，請換一個 ID（例如加 -2）。")
    rows_t, rows_c = _gen_rows(did, level, g)
    save = st.button(f"💾 存進試算表（對話ID：{did or '—'}）", type="primary", key="dlg_g_save")   # V2.9.576 不變灰
    if save and (not did or exists or not g["turns"]):
        st.warning("還不能存：" + ("請填「課名／單元」或「對話ID」。" if not did else
                                   f"對話ID「{did}」已經存在。" if exists else "對話至少要有一句。"))
    elif save:
        try:
            book = _gspread_book()
            _append_rows(book, "對話範本", rows_t, ["對話ID", "標題", "程度", "回合", "角色", "角色名稱", "英文", "中文", "情境", "角色描述"])
            _append_rows(book, "替換字", rows_c, ["對話ID", "欄位", "英文", "中文", "圖", "圖片描述"])
            st.session_state.setdefault("dlg_pending", {})[did] = _gen_as_dialog(level, g)
            for _k in ("dlg_t_pick", "dlg_a_pick"):   # V2.9.569 其他分頁直接選到剛存的對話
                st.session_state[_k] = did
            _read_sheet.clear()
            st.session_state.pop("dlg_gen", None)
            st.session_state["dlg_gen_msg"] = (f"✅ 已存進試算表：{did}。接著到「🖼️ 對話與圖卡」選它，"
                                               "一鍵產生情境畫面和圖卡圖片，再到「📌 指派」。")
            st.rerun()   # V2.9.575 整頁重跑一次，其他分頁才看得到新對話
        except Exception as e:
            if type(e).__name__ in ("StopException", "RerunException", "RerunData"):
                raise
            st.error(f"寫入試算表失敗：{type(e).__name__}: {e}　→ 可以用下面「手動貼上」的內容自己貼進試算表。")
    with st.expander("📋 手動貼上用（複製後貼到試算表最下面一列）"):
        st.caption("「對話範本」分頁（欄位順序：對話ID｜標題｜程度｜回合｜角色｜角色名稱｜英文｜中文｜情境｜角色描述）")
        st.code("\n".join("\t".join(str(r[h]) for h in r) for r in rows_t), language=None)
        st.caption("「替換字」分頁（欄位順序：對話ID｜欄位｜英文｜中文｜圖｜圖片描述）")
        st.code("\n".join("\t".join(str(r[h]) for h in r) for r in rows_c), language=None)


def render_teacher(ctx):
    st.markdown(_CSS, unsafe_allow_html=True)
    st.caption(f"對話練習模組 V{DLG_VERSION}")
    dialogs = load_dialogs(ctx)
    st.session_state["_dlg_run_tok"] = st.session_state.get("_dlg_run_tok", 0) + 1   # 整頁重跑的編號
    tabs = st.tabs(["🪄 AI 產生對話", "🖼️ 對話與圖卡", "📌 指派", "🎧 學生紀錄", "⚙️ 設定說明"])
    # V2.9.575 每個分頁各自是一個 fragment：在分頁裡改字、按按鈕，只重畫這一頁，
    # 不再把整個老師頁面（其他分頁、作答統計…）全部重跑，等待時間少很多
    with tabs[0]:
        _frag_gen(ctx, dialogs)
    with tabs[1]:
        _frag_cards(ctx, dialogs)
    with tabs[2]:
        _frag_assign(ctx, dialogs)
    with tabs[3]:
        _frag_records(ctx, dialogs)
    with tabs[4]:
        _teacher_setup()


def _fresh_dialogs(ctx, dialogs, name):
    """整頁重跑時用剛讀好的 dialogs；只有分頁自己重跑時（例如剛存好圖）才重新讀，才看得到新圖"""
    tok, k = st.session_state.get("_dlg_run_tok"), "_dlg_tok_" + name
    if st.session_state.get(k) == tok:
        return load_dialogs(ctx)
    st.session_state[k] = tok
    return dialogs


@st.fragment
def _frag_gen(ctx, dialogs):
    _teacher_gen(ctx, dialogs)


@st.fragment
def _frag_cards(ctx, dialogs):
    _teacher_cards(ctx, _fresh_dialogs(ctx, dialogs, "cards"))


@st.fragment
def _frag_assign(ctx, dialogs):
    _teacher_assign(ctx, dialogs)


@st.fragment
def _frag_records(ctx, dialogs):
    _teacher_records(ctx, dialogs)


def _pick_dialog(dialogs, key):
    # V2.9.569 最新加的對話排最前面（預設選它），內建示範 D00 放最後，免得指派時不小心選到示範
    ids = [i for i in reversed(list(dialogs.keys())) if i != DEMO_ID] + ([DEMO_ID] if DEMO_ID in dialogs else [])
    if st.session_state.get(key) not in ids:
        st.session_state.pop(key, None)
    return st.selectbox("對話", ids, key=key,
                        format_func=lambda i: f"{i}｜{dialogs[i]['title']}" + (f"（{dialogs[i]['level']}）" if dialogs[i]["level"] else ""))


def _zh_mismatch(turns):
    """V2.9.571 英文和中文的 {欄位} 或「||」不一致的句子（多半是中文欄錯開一格）→ 回傳回合編號"""
    out = []
    for t in turns:
        if not t.get("zh"):
            continue
        en_s = set(re.findall(r"\{\s*(\??\w+)\s*\}", t["en"]))
        zh_s = set(re.findall(r"\{\s*(\??\w+)\s*\}", t["zh"]))
        if en_s != zh_s or (("||" in t["en"]) != ("||" in t["zh"])):
            out.append(t["turn"])
    return out


def _teacher_cards(ctx, dialogs):
    c1, c2 = st.columns([5, 1])
    with c1:
        did = _pick_dialog(dialogs, "dlg_t_pick")
    if c2.button("🔄", key="dlg_t_reload", help="重新讀取試算表與圖卡"):
        _read_sheet.clear()
        _load_card_images.clear()
        st.rerun()
    d = dialogs[did]
    bad = _zh_mismatch(d["turns"])
    if bad:
        st.error("⚠️ 這些句子的英文和中文對不上（中文提示會顯示錯的句子），請到試算表「對話範本」修改中文欄："
                 + "、".join(f"第 {n} 句" for n in bad))
    with st.expander("📜 對話內容", expanded=True):
        for t in d["turns"]:
            st.markdown(f"**{t['turn']}. {html.escape(d['names'].get(t['role'], t['role']))}**："
                        f"{html.escape(t['en'])}　<span style='color:#888'>{html.escape(t['zh'])}</span>"
                        + ("　<b style='color:#d33'>⚠️ 中英不一致</b>" if t["turn"] in bad else ""),
                        unsafe_allow_html=True)
    _teacher_scene(ctx, did, d)
    missing_slots = [s for s in _slots_in(d) if not d["cards"].get(s)]
    if missing_slots:
        st.warning("這些欄位在「替換字」表還沒有單字：" + "、".join(missing_slots))

    all_cards = [c for s in d["cards"] for c in d["cards"][s]]
    no_img = [c for c in all_cards if not _s(c.get("img")).startswith("http")]
    st.markdown(f"**圖卡：{len(all_cards)} 張，其中 {len(no_img)} 張還沒有圖片檔**（emoji 只是暫代）")
    hint = st.text_input("🖌️ 給 AI 的圖卡要求（可空白；「一次產生」和每張「換圖→AI 產生」都會照這個畫）", key=f"dlg_hint_{did}",
                         placeholder="例：畫成一頁日曆，正中間用大大的繁體中文寫出星期幾（例如：星期一），不要出現英文")
    st.caption("💡 星期、月份、數字這類光看圖分不出來的字，建議用各組下面的「🈶 中文字卡」：不用 AI、馬上做好、字一定正確。"
               "AI 畫中文字常會寫錯。")
    if no_img and st.button(f"🎨 一次 AI 產生 {len(no_img)} 張缺圖", key="dlg_gen_all"):
        ok = _gen_many(ctx, did, [(c, c.get("desc") or c["en"], hint) for c in no_img])   # V2.9.575 同時畫
        st.session_state["dlg_cards_msg"] = f"完成 {ok}／{len(no_img)} 張"
        _rerun_frag()
    if st.session_state.get("dlg_cards_msg"):
        st.success(st.session_state.pop("dlg_cards_msg"))

    ncol = 2 if ctx.get("is_phone") else 4
    for slot, cards in d["cards"].items():
        h1, h2 = st.columns([3, 2])
        h1.markdown(f"##### 欄位 `{{{slot}}}`")
        if h2.button(f"🈶 這組全部做成中文字卡（{len(cards)} 張）", key=f"dlg_tc_{did}_{slot}", use_container_width=True,
                     help="每張卡寫上它的中文（沒有中文就寫英文），會取代原本的圖"):
            for j, c in enumerate(cards):
                try:
                    _save_card_image(ctx, did, c, _text_card_svg(c.get("zh") or c["en"], j))
                except Exception as e:
                    st.error(f"{c['en']}：{type(e).__name__}: {e}")
            _rerun_frag()
        for i in range(0, len(cards), ncol):
            cols = st.columns(ncol)
            for j, (col, c) in enumerate(zip(cols, cards[i:i + ncol])):
                with col:
                    _card_editor(ctx, did, c, hint, i + j)


def _teacher_scene(ctx, did, d):
    """V2.9.558 情境畫面：背景（不含人物）＋角色 A／B 立繪（透明背景）"""
    st.markdown("#### 🎬 情境畫面（背景＋角色立繪）")
    st.caption("學生練習時，對話會出現在這個場景裡，兩位角色站左右兩邊。"
               "背景和人物分開畫，同一個角色每一輪長相都一樣。半寫實插畫風，每張約 20–60 秒。")
    first = {}
    for s in _slots_in(d):
        if d["cards"].get(s):
            first[s] = d["cards"][s][0]
    t0 = d["turns"][0] if d["turns"] else None
    st.markdown(_stage_html(d, list(first.values()), active=t0["role"] if t0 else None,
                            say=_fill(t0["en"], first, "en", "mark") if t0 else ""), unsafe_allow_html=True)
    st.caption("↑ 預覽：說話的人會跳動、場景裡出現對話泡泡；抽到天氣單字會有下雨、下雪、颳風等特效。")
    st.radio("畫風（AI 產生時用）", list(STYLE_SETS.keys()), horizontal=True, key="dlg_style")
    items = [d["scene"], d["chars"]["A"], d["chars"]["B"]]
    missing = [c for c in items if not _url(c)]
    b1, b2 = st.columns(2)
    go_missing = bool(missing) and b1.button(f"🎨 一次 AI 產生情境畫面（缺 {len(missing)} 張）", key=f"dlg_scene_all_{did}")
    go_redo = b2.button("🔁 三張全部用目前畫風重畫", key=f"dlg_scene_redo_{did}")
    todo = items if go_redo else (missing if go_missing else [])
    if todo:
        _gen_many(ctx, did, [(c, c["desc"], "") for c in todo], workers=3)   # V2.9.575 背景和兩個角色同時畫
        _rerun_frag()
    cols = st.columns(3)
    for col, c, lbl in zip(cols, items, ["🏞️ 背景", f"🧍 A：{d['names'].get('A', 'A')}", f"🧍 B：{d['names'].get('B', 'B')}"]):
        with col:
            st.caption(lbl)
            _card_editor(ctx, did, c)
    st.divider()


def _card_editor(ctx, did, c, hint="", idx=0):
    if _kind(c) == "card":
        st.markdown(f"<div class='dlg-card'>{_img_html(c, 88)}<div class='w'>{html.escape(c['en'])}</div>"
                    f"<div class='z'>{html.escape(c.get('zh', ''))}</div></div>", unsafe_allow_html=True)
    elif _url(c):
        st.image(_url(c))
    else:
        st.caption("（還沒有圖）")
    hk = hashlib.md5(c["id"].encode("utf-8")).hexdigest()[:10]
    with st.popover("✏️ 換圖", use_container_width=True):
        up = st.file_uploader("上傳圖片", type=["png", "jpg", "jpeg", "webp"], key=f"dlg_up_{hk}")
        if up is not None and st.button("💾 使用上傳的圖", key=f"dlg_upok_{hk}"):
            try:
                _save_card_image(ctx, did, c, up.getvalue())
                st.success("已儲存")
                _rerun_frag()
            except Exception as e:
                st.error(f"儲存失敗：{type(e).__name__}: {e}")
        st.markdown("---")
        if _kind(c) == "card":
            tc = st.text_input("🈶 中文字卡上的字", value=c.get("zh") or c["en"], key=f"dlg_tct_{hk}")
            if st.button("🈶 改用中文字卡（不用 AI）", key=f"dlg_tcok_{hk}", disabled=not tc.strip()):
                try:
                    _save_card_image(ctx, did, c, _text_card_svg(tc.strip(), idx))
                    _rerun_frag()
                except Exception as e:
                    st.error(f"儲存失敗：{type(e).__name__}: {e}")
            st.markdown("---")
        desc = st.text_input("AI 圖片描述（英文較準）", value=c.get("desc") or c["en"], key=f"dlg_desc_{hk}")
        extra = st.text_input("給 AI 的額外要求（可中文）", value=hint, key=f"dlg_hint1_{hk}",
                              placeholder="例：畫成日曆，上面寫大大的「星期一」")
        pend_key = f"dlg_pending_{hk}"
        if st.button("🎨 AI 產生", key=f"dlg_gen_{hk}"):
            with st.spinner("產生中（約 10–30 秒）…"):
                try:
                    raw, model = _gen_for(c, desc, extra)
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
                    _rerun_frag()
                except Exception as e:
                    st.error(f"儲存失敗：{type(e).__name__}: {e}")
            if a2.button("🗑️ 不要", key=f"dlg_gendel_{hk}"):
                st.session_state.pop(pend_key, None)
                _rerun_frag()


def _teacher_assign(ctx, dialogs):
    did = _pick_dialog(dialogs, "dlg_a_pick")
    d = dialogs[did]
    # V2.9.569 先讓老師看清楚選到的是哪段對話（學生練的就是這幾句）
    st.markdown("<div style='background:#f6f8fa;border-radius:8px;padding:8px 12px;font-size:.92rem'>"
                + f"<b>學生會練的對話：{html.escape(did)}｜{html.escape(d['title'])}</b><br>"
                + "<br>".join(f"{html.escape(t['role'])}｜{html.escape(d['names'].get(t['role'], t['role']))}："
                              f"{html.escape(t['en'])}" for t in d["turns"])
                + "</div>", unsafe_allow_html=True)
    if did == DEMO_ID:
        st.warning("⚠️ 目前選的是內建的「天氣示範」對話。要指派自己的對話，請在上面「對話」改選。")
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
    if "dlg_a_stages" in st.session_state:   # 舊關卡名稱留在畫面狀態裡會出錯，先濾掉
        st.session_state["dlg_a_stages"] = [x for x in STAGES if x in
                                            [_norm_stage(s) for s in st.session_state["dlg_a_stages"]]]
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
        _ad = dialogs.get(a.get("dialog_id"))
        c1.markdown(f"**{html.escape(a.get('title') or '')}**  \n"
                    f"<span style='color:#888;font-size:.85rem'>#{a['id']}｜對話 {html.escape(str(a.get('dialog_id') or ''))}"
                    f"｜{html.escape(_ad['title'] if _ad else '找不到')}｜{a.get('rounds')} 輪｜{n_stu} 人｜截止 {str(a.get('end_date') or '')[:10]}</span>",
                    unsafe_allow_html=True)
        if c2.button("🗑️", key=f"dlg_a_del_{a['id']}", help="刪除這個指派"):
            ctx["sb"]().table("dialog_assignments").update({"status": "已刪除"}).eq("id", a["id"]).execute()
            _bump_assign()
            _rerun_frag()


@st.cache_data(ttl=120, show_spinner=False)
def _load_dlg_logs(_sb_factory, aid, ver=0):
    """V2.9.575 學生紀錄快取 2 分鐘（以前每改一個欄位都重讀 2000 筆）；按「🔄 重新整理」馬上重讀"""
    q = _sb_factory().table("dialog_logs").select("*").order("created_at", desc=True).limit(2000)
    q = q.is_("assign_id", "null") if aid is None else q.eq("assign_id", aid)
    return q.execute().data or []


def _teacher_records(ctx, dialogs):
    # V2.9.578 開老師頁時先不讀 Supabase（以前每次開都要讀，拖慢載入）；老師按了才載入
    if not st.session_state.get("dlg_r_on"):
        st.info("學生紀錄要按下面的按鈕才會載入（讓老師頁開得快一點）。也可以直接看「全班學習報告」。")
        if st.button("📥 載入學生紀錄", key="dlg_r_load", type="primary"):
            st.session_state["dlg_r_on"] = True
            _rerun_frag()
        return
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
        st.session_state["dlg_r_ver"] = st.session_state.get("dlg_r_ver", 0) + 1
    sb = ctx["sb"]()
    try:
        data = _load_dlg_logs(ctx["sb"], aid, st.session_state.get("dlg_r_ver", 0))
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
                line = _fill(_pick_branch(t["en"], _is_yes({s: c["en"] for s, c in combo.items()})), combo, "en", "plain")
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
