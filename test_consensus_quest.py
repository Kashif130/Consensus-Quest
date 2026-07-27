"""
Consensus Quest — Automated Test Suite v1.1
Tests: state updates, security fixes, fallback behaviour, consensus path.

Run:
  python3 test_consensus_quest.py

35 tests covering all FIX-1 through FIX-10, fallback, and consensus mechanism.
"""

import sys, json, types, importlib.util, os, traceback

# ── GenLayer runtime mock ─────────────────────────────────────────────────────

class MockAddress:
    def __init__(self, h): self.as_hex = h
    def __eq__(self, o): return self.as_hex == (o.as_hex if isinstance(o, MockAddress) else o)
    def __hash__(self): return hash(self.as_hex)
    def __repr__(self): return f"Addr({self.as_hex[:10]})"

class MockTreeMap(dict):
    def get(self, k, d=None): return super().get(k, d)

_LLM_OUT   = None
_LLM_RAISE = False

def _good_q(correct=1):
    return json.dumps({
        "question":    "What is GenVM?",
        "options":     ["A token", "The GenLayer VM", "A DEX", "A bridge"],
        "correct":     correct,
        "explanation": "GenVM executes Intelligent Contracts.",
        "category":    "IC"
    })

class MockNondet:
    @staticmethod
    def exec_prompt(p):
        if _LLM_RAISE: raise RuntimeError("Simulated LLM failure")
        return _LLM_OUT or _good_q()

class MockEqPrinciple:
    _spy = None
    @staticmethod
    def prompt_non_comparative(fn, td, cc):
        if MockEqPrinciple._spy: MockEqPrinciple._spy(td, cc)
        return fn()

def _noop(fn): return fn   # decorator stub

class _Public:
    write = staticmethod(_noop)
    view  = staticmethod(_noop)

class MockGl:
    nondet       = MockNondet()
    eq_principle = MockEqPrinciple()
    public       = _Public()
    class message:
        sender_address = MockAddress("0xHOST0001")
    class Contract: pass

def u256(v): return int(v)

gm = types.ModuleType("genlayer")
gm.u256 = u256; gm.Address = MockAddress; gm.TreeMap = MockTreeMap; gm.gl = MockGl
sys.modules["genlayer"] = gm

CONTRACT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "consensus_quest_v15.py")
spec = importlib.util.spec_from_file_location("cq", CONTRACT_PATH)
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CQ       = mod.ConsensusQuest
FALLBACK = mod.FALLBACK_QUESTION

HOST  = MockAddress("0xHOST0001")
GUEST = MockAddress("0xGUEST002")
OTHER = MockAddress("0xOTHER003")

# ── helpers ──────────────────────────────────────────────────────────────────

def contract():
    c = CQ.__new__(CQ)
    c.leaderboard   = MockTreeMap(); c.usernames     = MockTreeMap()
    c.correct_count = MockTreeMap(); c.games_played  = MockTreeMap()
    c.last_question = "";            c.round_number  = 0
    c.rooms         = MockTreeMap()
    return c

def sender(a): MockGl.message.sender_address = a

def llm(out=None, raises=False):
    global _LLM_OUT, _LLM_RAISE
    _LLM_OUT = out; _LLM_RAISE = raises

def create_join(c, rid="r1", mode="mixed"):
    sender(HOST); llm(_good_q()); c.create_room(rid, mode)
    sender(GUEST); c.join_room(rid)

def expect_raises(fn):
    try: fn(); return False
    except: return True

# ── test runner ───────────────────────────────────────────────────────────────

PASS = 0; FAIL = 0; ERRORS = []

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  PASS  {name}")
        PASS += 1
    except Exception:
        print(f"  FAIL  {name}")
        ERRORS.append((name, traceback.format_exc()))
        FAIL += 1

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Registration ─────────────────────────────────────────────────────────")

def t_reg():
    c = contract(); sender(HOST); c.register("Alice")
    assert c.usernames[HOST] == "Alice"
test("register: sets username", t_reg)

def t_reg_zero():
    c = contract(); sender(HOST); c.register("Bob")
    assert c.leaderboard[HOST] == 0 and c.correct_count[HOST] == 0 and c.games_played[HOST] == 0
test("register: stats initialised to 0", t_reg_zero)

def t_reg_update():
    c = contract(); sender(HOST); c.register("Alice"); c.register("Alice2")
    assert c.usernames[HOST] == "Alice2"
test("register: username updatable", t_reg_update)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-1: Room ID immutability ──────────────────────────────────────────")

def t_fix1():
    c = contract(); sender(HOST); llm(_good_q()); c.create_room("r1", "mixed")
    assert expect_raises(lambda: c.create_room("r1", "ic"))
test("FIX-1: room ID cannot be overwritten", t_fix1)

def t_create_flags():
    c = contract(); sender(HOST); llm(_good_q()); c.create_room("r1", "mixed")
    r = json.loads(c.rooms["r1"])
    assert r["host_answered"] == False and r["guest_answered"] == False and r["round_done"] == False
test("create_room: answer/round flags start False", t_create_flags)

def t_round_inc():
    c = contract(); sender(HOST); llm(_good_q()); c.create_room("r1", "mixed")
    assert c.round_number == 1
test("create_room: round_number increments", t_round_inc)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-7: Join room guards ──────────────────────────────────────────────")

def t_join():
    c = contract(); create_join(c)
    assert json.loads(c.rooms["r1"])["guest"] == GUEST.as_hex
test("join_room: sets guest", t_join)

def t_fix7_full():
    c = contract(); create_join(c); sender(OTHER)
    assert expect_raises(lambda: c.join_room("r1"))
test("FIX-7: full room blocks join", t_fix7_full)

def t_fix7_self():
    c = contract(); sender(HOST); llm(_good_q()); c.create_room("r1", "mixed")
    assert expect_raises(lambda: c.join_room("r1"))
test("FIX-7: host cannot join own room", t_fix7_self)

def t_fix7_gameover():
    c = contract(); create_join(c); sender(HOST); c.end_game("r1"); sender(OTHER)
    assert expect_raises(lambda: c.join_room("r1"))
test("FIX-7: cannot join game_over room", t_fix7_gameover)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-2: Double answer prevention ─────────────────────────────────────")

def t_fix2_host():
    c = contract(); create_join(c); sender(HOST); c.submit_room_answer("r1", 1)
    assert expect_raises(lambda: c.submit_room_answer("r1", 0))
test("FIX-2: host cannot answer twice", t_fix2_host)

def t_fix2_guest():
    c = contract(); create_join(c); sender(GUEST); c.submit_room_answer("r1", 2)
    assert expect_raises(lambda: c.submit_room_answer("r1", 0))
test("FIX-2: guest cannot answer twice", t_fix2_guest)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-3: XP scored exactly once ───────────────────────────────────────")

def t_fix3_xp():
    c = contract(); create_join(c); sender(HOST); c.submit_room_answer("r1", 1)
    assert c.leaderboard[HOST] == 100
test("FIX-3: correct answer awards 100 XP", t_fix3_xp)

def t_fix3_no_xp():
    c = contract(); create_join(c); sender(HOST); c.submit_room_answer("r1", 0)
    assert c.leaderboard.get(HOST, 0) == 0
test("FIX-3: wrong answer awards 0 XP", t_fix3_no_xp)

def t_fix3_round_done():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    assert json.loads(c.rooms["r1"])["round_done"] == False
    sender(GUEST); c.submit_room_answer("r1", 2)
    assert json.loads(c.rooms["r1"])["round_done"] == True
test("FIX-3: round_done only after both players answer", t_fix3_round_done)

def t_fix3_after_done():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    assert expect_raises(lambda: c.submit_room_answer("r1", 0))
test("FIX-3: cannot answer after round_done", t_fix3_after_done)

def t_fix3_no_double_xp():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    assert c.leaderboard[HOST] == 100
    expect_raises(lambda: c.submit_room_answer("r1", 1))
    assert c.leaderboard[HOST] == 100
test("FIX-3: XP not double-credited", t_fix3_no_double_xp)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-6: Guest required before answering ───────────────────────────────")

def t_fix6():
    c = contract(); sender(HOST); llm(_good_q()); c.create_room("r1", "mixed")
    assert expect_raises(lambda: c.submit_room_answer("r1", 1))
test("FIX-6: cannot answer without guest", t_fix6)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-5: Match progression enforced ───────────────────────────────────")

def t_fix5_block():
    c = contract(); create_join(c); sender(HOST); llm(_good_q())
    assert expect_raises(lambda: c.next_round("r1", "mixed"))
test("FIX-5: next_round blocked before round_done", t_fix5_block)

def t_fix5_ok():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    sender(HOST); llm(_good_q(correct=2)); c.next_round("r1", "mixed")
    r = json.loads(c.rooms["r1"])
    assert r["round_done"] == False and r["is_active"] == True and r["round_num"] == 2
test("FIX-5: next_round resets all flags correctly", t_fix5_ok)

def t_fix7_gameover_next():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    sender(HOST); c.end_game("r1")
    assert expect_raises(lambda: c.next_round("r1", "mixed"))
test("FIX-7: next_round blocked after game_over", t_fix7_gameover_next)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-8: check_room_answer is pure view ────────────────────────────────")

def t_fix8_hidden():
    c = contract(); create_join(c)
    assert "error" in json.loads(c.check_room_answer("r1", 1))
test("FIX-8: answer hidden during active round", t_fix8_hidden)

def t_fix8_revealed():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    res = json.loads(c.check_room_answer("r1", 1))
    assert res["is_correct"] == True and res["correct_index"] == 1
test("FIX-8: answer revealed after round_done", t_fix8_revealed)

def t_fix8_no_xp():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    xp = c.leaderboard.get(HOST, 0)
    c.check_room_answer("r1", 1)
    assert c.leaderboard.get(HOST, 0) == xp
test("FIX-8: check_room_answer never awards XP", t_fix8_no_xp)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-9: get_room client sync ──────────────────────────────────────────")

def t_fix9_hidden():
    c = contract(); create_join(c)
    assert "correct_index" not in json.loads(c.get_room("r1"))
test("FIX-9: correct_index hidden during active round", t_fix9_hidden)

def t_fix9_visible():
    c = contract(); create_join(c)
    sender(HOST); c.submit_room_answer("r1", 1)
    sender(GUEST); c.submit_room_answer("r1", 2)
    res = json.loads(c.get_room("r1"))
    assert "correct_index" in res and res["correct_index"] == 1
test("FIX-9: correct_index visible after round_done", t_fix9_visible)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── FIX-4 + FIX-10: Solo mode ────────────────────────────────────────────")

def t_solo_xp():
    c = contract(); sender(HOST); llm(_good_q(correct=1))
    c.generate_question("ic"); c.submit_answer(1, 1)
    assert c.leaderboard[HOST] == 100
test("solo: correct answer awards XP", t_solo_xp)

def t_fix10_advance():
    c = contract(); sender(HOST); llm(_good_q())
    c.generate_question("ic"); assert c.round_number == 1
    c.submit_answer(1, 1)
    assert c.round_number == 2 and c.last_question == ""
test("FIX-10: round advances and question clears after submit", t_fix10_advance)

def t_fix4_wrong():
    c = contract(); sender(HOST); llm(_good_q())
    c.generate_question("ic")
    assert expect_raises(lambda: c.submit_answer(1, 999))
test("FIX-4: wrong round_num rejected", t_fix4_wrong)

def t_fix10_no_double():
    c = contract(); sender(HOST); llm(_good_q())
    c.generate_question("ic"); c.submit_answer(1, 1)
    assert expect_raises(lambda: c.submit_answer(1, 2))
test("FIX-10: same question cannot be answered twice", t_fix10_no_double)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Fallback default question ────────────────────────────────────────────")

def t_fallback_raises():
    c = contract(); sender(HOST); llm(raises=True)
    c.generate_question("ic")
    assert c.last_question != ""
    assert json.loads(c.last_question)["question"] == json.loads(FALLBACK)["question"]
test("FALLBACK: LLM exception triggers fallback, no revert", t_fallback_raises)

def t_fallback_garbage():
    c = contract(); sender(HOST); llm("not json!!!")
    c.generate_question("mixed")
    assert json.loads(c.last_question)["question"] == json.loads(FALLBACK)["question"]
test("FALLBACK: garbage LLM output triggers fallback", t_fallback_garbage)

def t_fallback_valid():
    c = contract(); parsed = c._validate_question(json.loads(FALLBACK))
    assert parsed["correct"] == 1 and len(parsed["options"]) == 4
test("FALLBACK: fallback question passes validation", t_fallback_valid)

def t_fallback_create():
    c = contract(); sender(HOST); llm(raises=True)
    c.create_room("r1", "ic"); assert "r1" in c.rooms
test("FALLBACK: create_room succeeds on LLM failure", t_fallback_create)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Consensus: prompt_non_comparative ────────────────────────────────────")

def t_consensus():
    captured = {}
    def spy(td, cc): captured["td"] = td; captured["cc"] = cc
    MockEqPrinciple._spy = spy
    c = contract(); sender(HOST); llm(_good_q()); c.generate_question("ic")
    MockEqPrinciple._spy = None
    assert "GenLayer"              in captured.get("td", ""), "task_desc missing GenLayer"
    cc = captured.get("cc", "")
    assert "TOPIC RELEVANCE"       in cc, "missing TOPIC RELEVANCE"
    assert "CORRECT OPTION"        in cc, "missing CORRECT OPTION MATCHES"
    assert "PLAUSIBLE DISTRACTORS" in cc, "missing PLAUSIBLE DISTRACTORS"
    assert "STRUCTURE"             in cc, "missing STRUCTURE"
test("CONSENSUS: prompt_non_comparative called with 3-param substance criteria", t_consensus)

# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Leaderboard ──────────────────────────────────────────────────────────")

def t_lb():
    c = contract()
    c.leaderboard[HOST] = 200;  c.leaderboard[GUEST] = 100
    c.usernames[HOST]   = "A";  c.usernames[GUEST]   = "B"
    c.correct_count[HOST] = 2;  c.correct_count[GUEST] = 1
    c.games_played[HOST]  = 2;  c.games_played[GUEST]  = 1
    entries = json.loads(c.get_leaderboard())
    assert entries[0]["xp"] >= entries[1]["xp"] and entries[0]["address"] == HOST.as_hex
test("leaderboard: sorted by XP descending", t_lb)

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"Results: {PASS} passed, {FAIL} failed  ({PASS+FAIL} total)")
if ERRORS:
    print()
    for name, tb in ERRORS:
        print(f"--- FAILED: {name} ---"); print(tb)
print('='*60)
sys.exit(0 if FAIL == 0 else 1)
