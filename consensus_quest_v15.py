# v0.3.0 - Fixed: Room multiplayer sync, question loading with wallet
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

# ── FALLBACK DEFAULT QUESTION ─────────────────────────────────────────────────
# Used when LLM output cannot be parsed after all cleanup attempts.
# Ensures create_room / generate_question / next_round never revert due to
# a bad LLM response — transaction always succeeds with a valid question.
FALLBACK_QUESTION = json.dumps({
    "question":    "What is the core innovation of GenLayer Intelligent Contracts?",
    "options":     [
        "They compile to EVM bytecode",
        "They can execute LLM prompts and access the web on-chain",
        "They use zero-knowledge proofs for privacy",
        "They are written in Solidity with AI extensions"
    ],
    "correct":     1,
    "explanation": (
        "GenLayer Intelligent Contracts run inside GenVM, which can natively call "
        "LLMs and fetch web data during execution — making them fundamentally different "
        "from traditional smart contracts."
    ),
    "category": "IC"
})

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

    # ── HELPERS ──────────────────────────────────────────────────────────────

    def _init_player(self, addr: Address) -> None:
        if self.leaderboard.get(addr, None) is None:
            self.leaderboard[addr]   = u256(0)
            self.correct_count[addr] = u256(0)
            self.games_played[addr]  = u256(0)

    def _build_prompt(self, topic: str, round_num: int) -> str:
        return (
            f"Generate a GenLayer blockchain quiz question about: {topic}. "
            f"Round: {round_num}. "
            "Output ONLY a single JSON object — no markdown, no backticks, no extra text. "
            "Required keys: question (string), options (array of exactly 4 strings), "
            "correct (integer 0-3 indicating which option is correct), "
            "explanation (string), category (string, one of IC OD GENERAL). "
            'Example: {"question":"What is GenVM?","options":["A token","The VM for ICs","A DEX","A bridge"],'
            '"correct":1,"explanation":"GenVM executes Intelligent Contracts.","category":"IC"}'
        )

    def _extract_json(self, raw: str) -> dict:
        """
        Two-pass JSON extractor.
        Pass 1 — direct json.loads on stripped text.
        Pass 2 — strip markdown fences, extract first {…} block, retry.
        Returns parsed dict or raises ValueError.
        """
        # Pass 1
        try:
            return json.loads(raw.strip())
        except Exception:
            pass
        # Pass 2
        try:
            cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
            start   = cleaned.find("{")
            end     = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                cleaned = cleaned[start:end]
            return json.loads(cleaned)
        except Exception as e:
            raise ValueError(f"JSON extraction failed: {e} | raw[:200]={raw[:200]!r}")

    def _validate_question(self, parsed: dict) -> dict:
        """Structural + type normalisation. Raises AssertionError on bad data."""
        assert "question"    in parsed and isinstance(parsed["question"], str),     "Missing/invalid: question"
        assert "options"     in parsed and isinstance(parsed["options"], list),     "Missing/invalid: options"
        assert len(parsed["options"]) == 4,                                          "options must have exactly 4 items"
        assert all(isinstance(o, str) and o for o in parsed["options"]),            "All options must be non-empty strings"
        assert "correct"     in parsed,                                              "Missing: correct"
        assert 0 <= int(parsed["correct"]) <= 3,                                    "correct must be 0-3"
        assert "explanation" in parsed and isinstance(parsed["explanation"], str),  "Missing/invalid: explanation"
        parsed["correct"] = int(parsed["correct"])
        if parsed.get("category") not in ("IC", "OD", "GENERAL"):
            parsed["category"] = "GENERAL"
        return parsed

    def _fetch_and_validate(self, prompt: str, topic: str) -> str:
        """
        Calls gl.eq_principle.prompt_non_comparative with THREE parameters:
          1. make_question  — callable that runs the LLM and returns a JSON string
          2. task_desc      — what the task is (for leader context)
          3. checking_criteria — what validators must verify (substance, not just structure)

        Fallback: if make_question raises any exception (parse error, LLM failure,
        validation failure), the except block catches it and returns FALLBACK_QUESTION
        so the transaction always succeeds.
        """
        fallback = FALLBACK_QUESTION

        def make_question() -> str:
            try:
                raw    = gl.nondet.exec_prompt(prompt)
                parsed = self._extract_json(raw)
                parsed = self._validate_question(parsed)
                return json.dumps(parsed)
            except Exception:
                # Fallback default — transaction must not revert
                return fallback

        task_desc = (
            f"Generate a multiple-choice quiz question about GenLayer blockchain, "
            f"specifically about: {topic}. "
            "The output must be a JSON object with keys: question, options (4 items), "
            "correct (integer 0-3), explanation, category."
        )

        checking_criteria = (
            "Verify ALL of the following — reject if any fail:\n"
            "1. TOPIC RELEVANCE: The question text is genuinely about GenLayer blockchain "
            f"and specifically relates to: {topic}. "
            "A generic blockchain question that does not mention GenLayer concepts is NOT acceptable.\n"
            "2. CORRECT OPTION MATCHES INDEX: Read the 'correct' integer field. "
            "Confirm that options[correct] is the answer supported by the explanation. "
            "If options[correct] is clearly wrong given the explanation, reject.\n"
            "3. PLAUSIBLE DISTRACTORS: The three incorrect options must be plausible "
            "wrong answers (not obviously absurd, not identical to the correct answer, "
            "not empty strings).\n"
            "4. STRUCTURE: output is valid JSON with a non-empty 'question' string, "
            "'options' array of exactly 4 non-empty strings, 'correct' integer 0-3, "
            "and non-empty 'explanation' string.\n"
            "If the output is the fallback default question, accept it as valid."
        )

        result = gl.eq_principle.prompt_non_comparative(
            make_question,
            task_desc,
            checking_criteria
        )

        # Final safety parse — if consensus output is somehow broken, use fallback
        try:
            parsed = self._extract_json(result)
            parsed = self._validate_question(parsed)
            return json.dumps(parsed)
        except Exception:
            return fallback

    # ── REGISTER ─────────────────────────────────────────────────────────────

    @gl.public.write
    def register(self, username: str) -> None:
        addr = gl.message.sender_address
        self.usernames[addr] = username
        self._init_player(addr)

    @gl.public.view
    def get_username(self, addr: Address) -> str:
        return self.usernames.get(addr, addr.as_hex[:10])

    # ── ROOM MANAGEMENT ──────────────────────────────────────────────────────

    def _topic_for_mode(self, mode: str) -> str:
        return {
            "ic":    "GenLayer Intelligent Contracts, GenVM, Python smart contracts",
            "od":    "Optimistic Democracy, validator consensus, appeals, equivalence principle",
            "mixed": "GenLayer ecosystem, Intelligent Contracts, validators, consensus",
            "debate":"GenLayer AI debate judging, argument evaluation, consensus",
        }.get(mode, "GenLayer ecosystem, Intelligent Contracts, validators, consensus")

    @gl.public.write
    def create_room(self, room_id: str, mode: str) -> None:
        addr = gl.message.sender_address

        # [FIX-1] Room ID immutable once created
        assert self.rooms.get(room_id, None) is None, \
            "Room ID already exists and cannot be overwritten"

        self._init_player(addr)

        topic     = self._topic_for_mode(mode)
        round_num = int(self.round_number) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json = self._fetch_and_validate(prompt, topic)

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
        if is_host:
            assert not room["host_answered"],  "Host already answered this round"   # [FIX-2]
        else:
            assert not room["guest_answered"], "Guest already answered this round"  # [FIX-2]

        try:
            q = json.loads(room["question"])
        except Exception:
            assert False, "Corrupt question data — cannot score"

        is_correct = int(answer_index) == int(q["correct"])

        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard.get(addr, u256(0))) + 100)
            self.correct_count[addr] = u256(int(self.correct_count.get(addr, u256(0))) + 1)

        self.games_played[addr] = u256(int(self.games_played.get(addr, u256(0))) + 1)

        if is_host:
            room["host_answered"]  = True
        else:
            room["guest_answered"] = True

        if room["host_answered"] and room["guest_answered"]:
            room["round_done"] = True   # [FIX-3]
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
        assert room["host"] == addr.as_hex,     "Only host can start next round"
        assert not room.get("game_over", False), "Game is over"                        # [FIX-7]
        assert room.get("round_done", False),    "Current round not finished yet"      # [FIX-5]
        assert room["guest"] != "",              "Cannot start next round without guest"  # [FIX-6]

        topic     = self._topic_for_mode(mode)
        round_num = int(room["round_num"]) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json = self._fetch_and_validate(prompt, topic)

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

    # ── SOLO MODE ─────────────────────────────────────────────────────────────

    @gl.public.write
    def generate_question(self, mode: str) -> None:
        topic     = self._topic_for_mode(mode)
        round_num = int(self.round_number) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json      = self._fetch_and_validate(prompt, topic)
        self.last_question = question_json
        self.round_number  = u256(round_num)

    @gl.public.view
    def get_question(self) -> str:
        if not self.last_question:
            return json.dumps({"error": "No question yet."})
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

        # [FIX-10] Advance round + clear — same question cannot be answered again
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

    # ── LEADERBOARD ───────────────────────────────────────────────────────────

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
