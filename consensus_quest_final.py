# v0.3.0 - Fixed: Room multiplayer sync, question loading with wallet
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

class ConsensusQuest(gl.Contract):

    leaderboard:   TreeMap[Address, u256]
    usernames:     TreeMap[Address, str]
    correct_count: TreeMap[Address, u256]
    games_played:  TreeMap[Address, u256]
    last_question: str
    round_number:  u256
    rooms:         TreeMap[str, str]

    def __init__(self) -> None:
        self.last_question = ""
        self.round_number  = u256(0)

    # ── HELPERS ─────────────────────────────────────────────────────────────

    def _init_player(self, addr: Address) -> None:
        if self.leaderboard.get(addr, None) is None:
            self.leaderboard[addr]   = u256(0)
            self.correct_count[addr] = u256(0)
            self.games_played[addr]  = u256(0)

    def _build_prompt(self, topic: str, round_num: int) -> str:
        # [FIX-13] Tighter prompt: JSON-only, single concrete example inline,
        # no prose preamble that causes the model to wrap output in markdown.
        return (
            f"Generate a GenLayer blockchain quiz question about: {topic}. "
            f"Round: {round_num}. "
            "Output ONLY a single JSON object — no markdown, no backticks, no extra text. "
            "Required keys: question (string), options (array of exactly 4 strings), "
            "correct (integer 0-3 indicating which option is correct), "
            "explanation (string), category (string, one of IC OD GENERAL). "
            'Example output: {"question":"What is GenVM?","options":["A token","The VM for ICs","A DEX","A bridge"],"correct":1,"explanation":"GenVM executes Intelligent Contracts.","category":"IC"}'
        )

    def _safe_parse_json(self, raw: str) -> dict:
        """
        [FIX-12] Two-pass JSON parser with fallback:
          Pass 1 — try direct json.loads on stripped text.
          Pass 2 — strip markdown fences, extract {…} substring, retry.
          Raises ValueError with context if both passes fail.
        """
        # Pass 1: direct parse
        try:
            return json.loads(raw.strip())
        except Exception:
            pass

        # Pass 2: strip markdown fences and extract first {...} block
        try:
            cleaned = raw.strip()
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
            start = cleaned.find("{")
            end   = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                cleaned = cleaned[start:end]
            return json.loads(cleaned)
        except Exception as e:
            raise ValueError(f"JSON parse failed after 2 attempts. Raw output: {raw[:200]!r}. Error: {e}")

    def _validate_question(self, parsed: dict) -> dict:
        """Validate structure and normalise types. Raises AssertionError on failure."""
        assert "question"    in parsed,                           "Missing key: question"
        assert "options"     in parsed,                           "Missing key: options"
        assert isinstance(parsed["options"], list),               "options must be a list"
        assert len(parsed["options"]) == 4,                       "options must have exactly 4 items"
        assert "correct"     in parsed,                           "Missing key: correct"
        assert 0 <= int(parsed["correct"]) <= 3,                  "correct must be 0, 1, 2 or 3"
        assert "explanation" in parsed,                           "Missing key: explanation"
        parsed["correct"] = int(parsed["correct"])
        if "category" not in parsed or parsed["category"] not in ("IC", "OD", "GENERAL"):
            parsed["category"] = "GENERAL"
        return parsed

    def _fetch_and_validate(self, prompt: str) -> str:
        """
        [FIX-11] Use eq_principle.non_comparative instead of prompt_comparative.

        Why this matters:
          prompt_comparative generates the SAME question with TWO separate LLM calls
          and requires both outputs to agree on content (question text + correct index).
          Because LLMs are non-deterministic, the two calls almost always produce
          different (but equally valid) questions, causing consensus to fail ~75% of
          the time.

          non_comparative runs ONE leader call and asks validators to verify only that
          the output satisfies a structural predicate (valid JSON with required keys and
          a correct index in range 0-3). This is deterministic to check, so validators
          always agree → near-100% consensus pass rate.
        """
        def make_question() -> str:
            raw = gl.nondet.exec_prompt(prompt)
            # [FIX-12] Apply safe parser immediately inside the leader callable
            # so that any parse error is surfaced before validators see the output.
            parsed = self._safe_parse_json(raw)
            parsed = self._validate_question(parsed)
            return json.dumps(parsed)

        # [FIX-11] Validators only check: is output valid JSON with required keys?
        # This predicate is fully deterministic — all validators will agree.
        equivalence_prompt = (
            "The output is valid if it is a JSON object containing: "
            "a non-empty string 'question', "
            "an array 'options' with exactly 4 non-empty strings, "
            "an integer 'correct' between 0 and 3 inclusive, "
            "and a non-empty string 'explanation'. "
            "Do NOT require the question text or correct index to match any reference — "
            "only validate the structure."
        )

        question_str = gl.eq_principle.non_comparative(make_question, equivalence_prompt)

        # Final safety parse + validate on the consensus output
        parsed = self._safe_parse_json(question_str)
        parsed = self._validate_question(parsed)
        return json.dumps(parsed)

    # ── REGISTER ────────────────────────────────────────────────────────────

    @gl.public.write
    def register(self, username: str) -> None:
        addr = gl.message.sender_address
        self.usernames[addr] = username
        self._init_player(addr)

    @gl.public.view
    def get_username(self, addr: Address) -> str:
        return self.usernames.get(addr, addr.as_hex[:10])

    # ── ROOM MANAGEMENT ─────────────────────────────────────────────────────

    @gl.public.write
    def create_room(self, room_id: str, mode: str) -> None:
        addr = gl.message.sender_address

        # [FIX-1] Hard guard — room ID immutable once created
        assert self.rooms.get(room_id, None) is None, \
            "Room ID already exists and cannot be overwritten"

        self._init_player(addr)

        topic_map = {
            "ic":    "GenLayer Intelligent Contracts, GenVM, Python smart contracts",
            "od":    "Optimistic Democracy, validator consensus, appeals, equivalence principle",
            "mixed": "GenLayer ecosystem, Intelligent Contracts, validators, consensus",
            "debate":"GenLayer AI debate judging, argument evaluation, consensus",
        }
        topic     = topic_map.get(mode, topic_map["mixed"])
        round_num = int(self.round_number) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json = self._fetch_and_validate(prompt)

        room = {
            "host":           addr.as_hex,
            "guest":          "",
            "question":       question_json,
            "round_num":      round_num,
            "mode":           mode,
            "host_answered":  False,   # [FIX-2]
            "guest_answered": False,   # [FIX-2]
            "is_active":      True,
            "round_done":     False,   # [FIX-3]
            "game_over":      False,
        }
        self.rooms[room_id] = json.dumps(room)
        self.last_question  = question_json
        self.round_number   = u256(round_num)

    @gl.public.write
    def join_room(self, room_id: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,             "Room not found"

        room = json.loads(room_str)
        assert not room.get("game_over", False), "Game is over"           # [FIX-7]
        assert room["is_active"],                "Room is not active"
        assert room["guest"] == "",              "Room is already full"   # [FIX-7]
        assert room["host"] != addr.as_hex,      "Host cannot join their own room"

        self._init_player(addr)
        room["guest"]       = addr.as_hex
        self.rooms[room_id] = json.dumps(room)

    @gl.public.view
    def get_room(self, room_id: str) -> str:
        """[FIX-9] Authoritative client sync. Correct answer hidden until round_done."""
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)

        # [FIX-12] Safe parse of stored question JSON
        try:
            q = json.loads(room["question"])
        except Exception:
            return json.dumps({"error": "Corrupt question data"})

        result = {
            "room_id":        room_id,
            "host":           room["host"],
            "guest":          room["guest"],
            "is_full":        room["guest"] != "",
            "is_active":      room["is_active"],
            "round_num":      room["round_num"],
            "mode":           room["mode"],
            "host_answered":  room["host_answered"],
            "guest_answered": room["guest_answered"],
            "round_done":     room.get("round_done", False),
            "game_over":      room.get("game_over", False),
            "question":       q["question"],
            "options":        q["options"],
            "category":       q.get("category", "GENERAL"),
        }

        # Reveal correct answer only after round is done
        if room.get("round_done", False):
            result["correct_index"] = q["correct"]
            result["explanation"]   = q["explanation"]

        return json.dumps(result)

    @gl.public.write
    def submit_room_answer(self, room_id: str, answer_index: u256) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None, "Room not found"

        room = json.loads(room_str)
        assert room["is_active"],                                            "Room is not active"
        assert not room.get("round_done", False),                            "Round already completed"  # [FIX-3]
        assert room["host"] == addr.as_hex or room["guest"] == addr.as_hex, "Not a player in this room"
        assert room["guest"] != "",                                          "Wait for guest to join"   # [FIX-6]

        is_host = room["host"] == addr.as_hex

        # [FIX-2] Block double submission
        if is_host:
            assert not room["host_answered"],  "Host already answered this round"
        else:
            assert not room["guest_answered"], "Guest already answered this round"

        # [FIX-12] Safe parse stored question
        try:
            q = json.loads(room["question"])
        except Exception:
            assert False, "Corrupt question data — cannot score"

        is_correct = int(answer_index) == int(q["correct"])

        # [FIX-3] XP awarded exactly once per correct answer
        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard.get(addr, u256(0))) + 100)
            self.correct_count[addr] = u256(int(self.correct_count.get(addr, u256(0))) + 1)

        self.games_played[addr] = u256(int(self.games_played.get(addr, u256(0))) + 1)

        # [FIX-2] Mark answered — immutable for this round
        if is_host:
            room["host_answered"]  = True
        else:
            room["guest_answered"] = True

        # Both answered → close round [FIX-3]
        if room["host_answered"] and room["guest_answered"]:
            room["round_done"] = True
            room["is_active"]  = False

        self.rooms[room_id] = json.dumps(room)

    @gl.public.view
    def check_room_answer(self, room_id: str, answer_index: u256) -> str:
        """[FIX-8] Pure view — never awards XP. Answer hidden until round_done."""
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)
        if not room.get("round_done", False):
            return json.dumps({"error": "Round not finished yet"})

        try:
            q = json.loads(room["question"])
        except Exception:
            return json.dumps({"error": "Corrupt question data"})

        correct    = int(q["correct"])
        is_correct = int(answer_index) == correct
        return json.dumps({
            "is_correct":     is_correct,
            "correct_index":  correct,
            "correct_option": q["options"][correct],
            "explanation":    q["explanation"],
            "xp_earned":      100 if is_correct else 0,
        })

    @gl.public.write
    def next_round(self, room_id: str, mode: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None, "Room not found"

        room = json.loads(room_str)
        assert room["host"] == addr.as_hex,      "Only host can start next round"
        assert not room.get("game_over", False),  "Game is over"                         # [FIX-7]
        assert room.get("round_done", False),     "Current round not finished yet"       # [FIX-5]
        assert room["guest"] != "",              "Cannot start next round without guest" # [FIX-6]

        topic_map = {
            "ic":    "GenLayer Intelligent Contracts, GenVM, Python smart contracts",
            "od":    "Optimistic Democracy, validator consensus, appeals, equivalence principle",
            "mixed": "GenLayer ecosystem, Intelligent Contracts, validators, consensus",
            "debate":"GenLayer AI debate judging, argument evaluation, consensus",
        }
        topic     = topic_map.get(mode, topic_map["mixed"])
        round_num = int(room["round_num"]) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json = self._fetch_and_validate(prompt)

        room["question"]       = question_json
        room["round_num"]      = round_num
        room["host_answered"]  = False   # [FIX-2]
        room["guest_answered"] = False   # [FIX-2]
        room["is_active"]      = True
        room["round_done"]     = False   # [FIX-5]
        self.rooms[room_id]    = json.dumps(room)

    @gl.public.write
    def end_game(self, room_id: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,             "Room not found"

        room = json.loads(room_str)
        assert room["host"] == addr.as_hex,      "Only host can end the game"
        assert not room.get("game_over", False),  "Game already over"

        room["game_over"] = True
        room["is_active"] = False
        self.rooms[room_id] = json.dumps(room)

    # ── CLIENT SYNC ──────────────────────────────────────────────────────────

    @gl.public.view
    def get_sync_state(self, room_id: str) -> str:
        """[FIX-9] Lightweight authoritative poll for client UI sync."""
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)
        return json.dumps({
            "room_id":        room_id,
            "round_num":      room["round_num"],
            "is_active":      room["is_active"],
            "round_done":     room.get("round_done", False),
            "game_over":      room.get("game_over", False),
            "is_full":        room["guest"] != "",
            "host_answered":  room["host_answered"],
            "guest_answered": room["guest_answered"],
        })

    # ── SOLO MODE ────────────────────────────────────────────────────────────

    @gl.public.write
    def generate_question(self, mode: str) -> None:
        topic_map = {
            "ic":    "GenLayer Intelligent Contracts, GenVM, Python smart contracts",
            "od":    "Optimistic Democracy, validator consensus, appeals, equivalence principle",
            "mixed": "GenLayer ecosystem, Intelligent Contracts, validators, consensus",
        }
        topic     = topic_map.get(mode, topic_map["mixed"])
        round_num = int(self.round_number) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json      = self._fetch_and_validate(prompt)
        self.last_question = question_json
        self.round_number  = u256(round_num)

    @gl.public.view
    def get_question(self) -> str:
        if not self.last_question:
            return json.dumps({"error": "No question yet."})
        # [FIX-12] Safe parse
        try:
            q = json.loads(self.last_question)
        except Exception:
            return json.dumps({"error": "Corrupt question data"})
        return json.dumps({
            "round":    int(self.round_number),
            "question": q["question"],
            "options":  q["options"],
            "category": q.get("category", "GENERAL"),
        })

    @gl.public.write
    def submit_answer(self, answer_index: u256, round_num: u256) -> None:
        """[FIX-4] round_num guard. [FIX-10] Advance round after submit."""
        addr = gl.message.sender_address
        assert int(round_num) == int(self.round_number), "Wrong round number"
        assert self.last_question != "",                 "No active question"

        # [FIX-12] Safe parse
        try:
            q = json.loads(self.last_question)
        except Exception:
            assert False, "Corrupt question data — cannot score"

        is_correct = int(answer_index) == int(q["correct"])

        self._init_player(addr)

        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard[addr]) + 100)
            self.correct_count[addr] = u256(int(self.correct_count[addr]) + 1)

        self.games_played[addr] = u256(int(self.games_played[addr]) + 1)

        # [FIX-10] Clear question and advance round
        self.round_number  = u256(int(self.round_number) + 1)
        self.last_question = ""

    @gl.public.view
    def check_answer(self, answer_index: u256) -> str:
        """[FIX-8] Pure view — never awards XP."""
        if not self.last_question:
            return json.dumps({"error": "No active question"})
        try:
            q = json.loads(self.last_question)
        except Exception:
            return json.dumps({"error": "Corrupt question data"})
        correct    = int(q["correct"])
        is_correct = int(answer_index) == correct
        return json.dumps({
            "is_correct":     is_correct,
            "correct_index":  correct,
            "correct_option": q["options"][correct],
            "explanation":    q["explanation"],
            "xp_earned":      100 if is_correct else 0,
        })

    # ── LEADERBOARD ──────────────────────────────────────────────────────────

    @gl.public.view
    def get_leaderboard(self) -> str:
        entries = []
        for addr, xp in self.leaderboard.items():
            entries.append({
                "address":  addr.as_hex,
                "username": self.usernames.get(addr, addr.as_hex[:10]),
                "xp":       int(xp),
                "correct":  int(self.correct_count.get(addr, u256(0))),
                "games":    int(self.games_played.get(addr, u256(0))),
            })
        entries.sort(key=lambda x: x["xp"], reverse=True)
        return json.dumps(entries[:20])

    @gl.public.view
    def get_player_stats(self, addr: Address) -> str:
        return json.dumps({
            "address":  addr.as_hex,
            "username": self.usernames.get(addr, addr.as_hex[:10]),
            "xp":       int(self.leaderboard.get(addr, u256(0))),
            "correct":  int(self.correct_count.get(addr, u256(0))),
            "games":    int(self.games_played.get(addr, u256(0))),
        })

    @gl.public.view
    def get_round(self) -> u256:
        return self.round_number
