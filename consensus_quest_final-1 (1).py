# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

class ConsensusQuest(gl.Contract):

    leaderboard:   TreeMap[Address, u256]
    usernames:     TreeMap[Address, str]
    correct_count: TreeMap[Address, u256]
    games_played:  TreeMap[Address, u256]
    rooms:         TreeMap[str, str]
    last_question: str
    round_number:  u256

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
            f"Round number: {round_num}. "
            "Rules: factual about GenLayer, exactly 4 options (index 0-3), "
            "one correct answer, intermediate difficulty. "
            "Respond ONLY with valid JSON, no markdown, no extra text: "
            "{\"question\":\"...\",\"options\":[\"A\",\"B\",\"C\",\"D\"],"
            "\"correct\":1,\"explanation\":\"...\",\"category\":\"IC\"}"
        )

    def _fetch_question(self, prompt: str) -> str:
        def make_question():
            raw = gl.nondet.exec_prompt(prompt)
            raw = raw.replace("```json", "").replace("```", "").strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                raw = raw[start:end]
            return raw

        return gl.eq_principle.prompt_comparative(
            make_question,
            "Both outputs must be valid JSON quiz questions about GenLayer "
            "with a question, 4 options, a correct index (0-3), and an explanation. "
            "The correct answer index must match."
        )

    def _validate_and_store(self, question_str: str) -> str:
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

    # ── CREATE ROOM ─────────────────────────────────────────────────────────

    @gl.public.write
    def create_room(self, room_id: str, mode: str) -> None:
        addr = gl.message.sender_address
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

        question_json = self._validate_and_store(self._fetch_question(prompt))

        room = {
            "host":          addr.as_hex,
            "guest":         "",
            "question":      question_json,
            "round_num":     round_num,
            "mode":          mode,
            "host_answered": False,
            "guest_answered":False,
            "is_active":     True,
            "round_done":    False,
        }
        self.rooms[room_id]  = json.dumps(room)
        self.last_question   = question_json
        self.round_number    = u256(round_num)

    # ── JOIN ROOM ────────────────────────────────────────────────────────────

    @gl.public.write
    def join_room(self, room_id: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,             "Room not found"

        room = json.loads(room_str)
        assert room["is_active"],                "Room is no longer active"
        assert room["guest"] == "",              "Room is already full"
        assert room["host"] != addr.as_hex,      "Host cannot join their own room"

        self._init_player(addr)
        room["guest"]       = addr.as_hex
        self.rooms[room_id] = json.dumps(room)

    # ── GET ROOM ─────────────────────────────────────────────────────────────

    @gl.public.view
    def get_room(self, room_id: str) -> str:
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room = json.loads(room_str)
        q    = json.loads(room["question"])

        return json.dumps({
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
            "question":       q["question"],
            "options":        q["options"],
            "category":       q.get("category", "GENERAL"),
        })

    # ── SUBMIT ANSWER ────────────────────────────────────────────────────────

    @gl.public.write
    def submit_room_answer(self, room_id: str, answer_index: u256) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None, "Room not found"

        room = json.loads(room_str)
        assert room["is_active"], "Room is not active"
        assert room["host"] == addr.as_hex or room["guest"] == addr.as_hex, "Not a player"

        q          = json.loads(room["question"])
        is_correct = int(answer_index) == int(q["correct"])

        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard.get(addr, u256(0))) + 100)
            self.correct_count[addr] = u256(int(self.correct_count.get(addr, u256(0))) + 1)

        self.games_played[addr] = u256(int(self.games_played.get(addr, u256(0))) + 1)

        if room["host"] == addr.as_hex:
            room["host_answered"] = True
        else:
            room["guest_answered"] = True

        if room["host_answered"] and room["guest_answered"]:
            room["is_active"]  = False
            room["round_done"] = True

        self.rooms[room_id] = json.dumps(room)

    # ── CHECK ANSWER ─────────────────────────────────────────────────────────

    @gl.public.view
    def check_room_answer(self, room_id: str, answer_index: u256) -> str:
        room_str = self.rooms.get(room_id, None)
        if room_str is None:
            return json.dumps({"error": "Room not found"})

        room       = json.loads(room_str)
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

    # ── NEXT ROUND ───────────────────────────────────────────────────────────

    @gl.public.write
    def next_round(self, room_id: str, mode: str) -> None:
        addr     = gl.message.sender_address
        room_str = self.rooms.get(room_id, None)
        assert room_str is not None,        "Room not found"

        room = json.loads(room_str)
        assert room["host"] == addr.as_hex, "Only host can start next round"

        topic_map = {
            "ic":    "GenLayer Intelligent Contracts, GenVM, Python smart contracts",
            "od":    "Optimistic Democracy, validator consensus, appeals, equivalence principle",
            "mixed": "GenLayer ecosystem, Intelligent Contracts, validators, consensus",
            "debate":"GenLayer AI debate judging, argument evaluation, consensus",
        }
        topic     = topic_map.get(mode, topic_map["mixed"])
        round_num = int(room["round_num"]) + 1
        prompt    = self._build_prompt(topic, round_num)

        question_json = self._validate_and_store(self._fetch_question(prompt))

        room["question"]       = question_json
        room["round_num"]      = round_num
        room["host_answered"]  = False
        room["guest_answered"] = False
        room["is_active"]      = True
        room["round_done"]     = False
        self.rooms[room_id]    = json.dumps(room)

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

        question_json     = self._validate_and_store(self._fetch_question(prompt))
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
        addr = gl.message.sender_address
        assert int(round_num) == int(self.round_number), "Wrong round number"
        assert self.last_question != "", "No active question"

        q          = json.loads(self.last_question)
        is_correct = int(answer_index) == int(q["correct"])

        self._init_player(addr)

        if is_correct:
            self.leaderboard[addr]   = u256(int(self.leaderboard[addr]) + 100)
            self.correct_count[addr] = u256(int(self.correct_count[addr]) + 1)

        self.games_played[addr] = u256(int(self.games_played[addr]) + 1)

    @gl.public.view
    def check_answer(self, answer_index: u256) -> str:
        if not self.last_question:
            return json.dumps({"error": "No question"})
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
