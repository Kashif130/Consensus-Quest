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
        return (
            "You are a quiz master for GenLayer blockchain education. "
            f"Generate ONE multiple-choice question about: {topic}. "
            f"This is round {round_num} — make a DIFFERENT question than previous rounds. "
            "Rules: Must be factual about GenLayer, exactly 4 options (index 0 to 3), "
            "only ONE correct answer, intermediate difficulty. "
            "Return ONLY a valid JSON object with NO extra text or markdown, "
            "using these exact keys: "
            "question (string), options (array of 4 strings), "
            "correct (integer 0-3), explanation (string), category (string IC or OD). "
            "Example: {\"question\":\"...\",\"options\":[\"A\",\"B\",\"C\",\"D\"],"
            "\"correct\":1,\"explanation\":\"...\",\"category\":\"IC\"}"
        )

    def _fetch_and_validate(self, prompt: str) -> str:
        def make_question():
            raw = gl.nondet.exec_prompt(prompt)
            cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
            start = cleaned.find("{")
            end   = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                cleaned = cleaned[start:end]
            return cleaned

        question_str = gl.eq_principle.prompt_comparative(
            make_question,
            "Both outputs must be valid JSON quiz questions about GenLayer with a question, "
            "4 options, a correct index (0-3), and an explanation. "
            "The correct answer index must match between both outputs."
        )

        parsed = json.loads(question_str)
        assert "question"    in parsed, "Missing question"
        assert "options"     in parsed and len(parsed["options"]) == 4, "Need 4 options"
        assert "correct"     in parsed and 0 <= int(parsed["correct"]) <= 3, "correct 0-3"
        assert "explanation" in parsed, "Missing explanation"
        parsed["correct"] = int(parsed["correct"])
        if "category" not in parsed:
            parsed["category"] = "GENERAL"
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

        # [FIX-1] Room ID cannot be overwritten
        assert self.rooms.get(room_id, None) is None, "Room ID already exists and cannot be overwritten"

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
            "host_answered":  False,   # [FIX-2] per-round answer flags
            "guest_answered": False,   # [FIX-2]
            "is_active":      True,
            "round_done":     False,   # [FIX-3] set True when both answered
            "game_over":      False,   # set True by end_game
        }
        self.rooms[room_id] = json.dumps(room)
        self.last_question  = question_json
        self.round_number   = u256(round_num)

    @gl.public.write
    def join_room(self, room_id: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,              "Room not found"

        room = json.loads(room_str)
        assert not room.get("game_over", False),  "Game is over"       # [FIX-7]
        assert room["is_active"],                 "Room is not active"
        assert room["guest"] == "",               "Room is already full"
        assert room["host"] != addr.as_hex,       "Host cannot join their own room"

        self._init_player(addr)
        room["guest"]       = addr.as_hex
        self.rooms[room_id] = json.dumps(room)

    @gl.public.view
    def get_room(self, room_id: str) -> str:
        """
        [FIX-9] Authoritative client sync state.
        Correct answer hidden while round is active.
        """
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)
        q    = json.loads(room["question"])

        result = {
            "room_id":        room_id,
            "host":           room["host"],
            "guest":          room["guest"],
            "is_full":        room["guest"] != "",
            "is_active":      room["is_active"],
            "round_num":      room["round_num"],
            "mode":           room["mode"],
            "host_answered":  room["host_answered"],    # [FIX-9]
            "guest_answered": room["guest_answered"],   # [FIX-9]
            "round_done":     room.get("round_done", False),
            "game_over":      room.get("game_over", False),
            "question":       q["question"],
            "options":        q["options"],
            "category":       q.get("category", "GENERAL"),
        }

        # [FIX-9] Only reveal correct answer after round is done
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
        assert room["is_active"],                                             "Room is not active"
        assert not room.get("round_done", False),                             "Round already completed"  # [FIX-3]
        assert room["host"] == addr.as_hex or room["guest"] == addr.as_hex,  "Not a player in this room"
        assert room["guest"] != "",                                           "Wait for guest to join"   # [FIX-6]

        is_host = room["host"] == addr.as_hex

        # [FIX-2] Block double submission per player per round
        if is_host:
            assert not room["host_answered"],  "Host already answered this round"
        else:
            assert not room["guest_answered"], "Guest already answered this round"

        q          = json.loads(room["question"])
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

        # Both answered → close round
        if room["host_answered"] and room["guest_answered"]:
            room["round_done"] = True   # [FIX-3] permanent flag
            room["is_active"]  = False

        self.rooms[room_id] = json.dumps(room)

    @gl.public.view
    def check_room_answer(self, room_id: str, answer_index: u256) -> str:
        """
        [FIX-8] Pure view — never awards XP.
        Only reveals answer after round_done to prevent cheating.
        """
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)

        # [FIX-8] Hide correct answer while round is still active
        if not room.get("round_done", False):
            return json.dumps({"error": "Round not finished yet"})

        q          = json.loads(room["question"])
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
        """Host starts next round. Only allowed after current round is done."""
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None, "Room not found"

        room = json.loads(room_str)
        assert room["host"] == addr.as_hex,        "Only host can start next round"
        assert not room.get("game_over", False),    "Game is over"                        # [FIX-7]
        assert room.get("round_done", False),       "Current round not finished yet"      # [FIX-5]
        assert room["guest"] != "",                 "Cannot start next round without guest" # [FIX-6]

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
        room["host_answered"]  = False   # [FIX-2] reset per-round flags
        room["guest_answered"] = False   # [FIX-2]
        room["is_active"]      = True
        room["round_done"]     = False   # [FIX-5] must complete before next
        self.rooms[room_id]    = json.dumps(room)

    @gl.public.write
    def end_game(self, room_id: str) -> None:
        """Host explicitly closes the room. Blocks further rounds or answers."""
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,            "Room not found"

        room = json.loads(room_str)
        assert room["host"] == addr.as_hex,     "Only host can end the game"
        assert not room.get("game_over", False), "Game already over"

        room["game_over"] = True
        room["is_active"] = False
        self.rooms[room_id] = json.dumps(room)

    # ── CLIENT SYNC ──────────────────────────────────────────────────────────

    @gl.public.view
    def get_sync_state(self, room_id: str) -> str:
        """
        [FIX-9] Lightweight poll endpoint for client sync.
        Clients must align UI to this — not local state.
        """
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
        q = json.loads(self.last_question)
        return json.dumps({
            "round":    int(self.round_number),
            "question": q["question"],
            "options":  q["options"],
            "category": q.get("category", "GENERAL"),
        })

    @gl.public.write
    def submit_answer(self, answer_index: u256, round_num: u256) -> None:
        """
        [FIX-4]  round_num must match — prevents re-submitting old rounds.
        [FIX-10] round_number advances + last_question cleared after submit.
        """
        addr = gl.message.sender_address
        assert int(round_num) == int(self.round_number), "Wrong round number"
        assert self.last_question != "",                 "No active question"

        q          = json.loads(self.last_question)
        is_correct = int(answer_index) == int(q["correct"])

        self._init_player(addr)

        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard[addr]) + 100)
            self.correct_count[addr] = u256(int(self.correct_count[addr]) + 1)

        self.games_played[addr] = u256(int(self.games_played[addr]) + 1)

        # [FIX-10] Advance round + clear question — same question cannot be answered again
        self.round_number  = u256(int(self.round_number) + 1)
        self.last_question = ""

    @gl.public.view
    def check_answer(self, answer_index: u256) -> str:
        """[FIX-8] Pure view — never awards XP."""
        if not self.last_question:
            return json.dumps({"error": "No active question"})
        q          = json.loads(self.last_question)
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
