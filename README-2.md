# ⚡ Consensus Quest — GenLayer On-Chain Mini-Game

> A fully on-chain multiplayer quiz game powered by GenLayer Intelligent Contracts, AI-generated questions, and Optimistic Democracy consensus.

![GenLayer](https://img.shields.io/badge/GenLayer-Testnet%20Asimov-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-GenVM-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 🎮 Live Demo

**▶ Play Now: [https://kashif130.github.io/Consensus-Quest/](https://kashif130.github.io/Consensus-Quest/)**

---

## ⛓ Deployed Contract

| Field | Value |
|-------|-------|
| **Network** | GenLayer Testnet Asimov |
| **Contract Address** | `0x3999ea8fAd64154426Df3570dbD92b7FE905b699` |
| **Language** | Python (GenLayer SDK v0.2.16) |
| **Source** | `consensus_quest_final.py` |

---

## 🧠 What Makes This Different

Unlike traditional blockchain games that use pre-written question banks stored in databases, **Consensus Quest generates every question live on-chain using AI.**

```
Player starts round
       ↓
Contract calls gl.nondet.exec_prompt() → LLM generates question
       ↓
Multiple validators independently run the same LLM
       ↓
gl.eq_principle.prompt_comparative() → validators reach consensus
       ↓
Question stored on-chain → players answer → XP saved permanently
```

This is only possible on **GenLayer** — no other blockchain supports this.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────┐
│         Frontend (index.html)               │
│  • Connect wallet                           │
│  • Create/Join rooms                        │
│  • Submit answers                           │
│  • View leaderboard                         │
└──────────────┬──────────────────────────────┘
               │ GenLayer RPC calls
               ▼
┌─────────────────────────────────────────────┐
│   ConsensusQuest Intelligent Contract       │
│   0x3999ea8fAd64154426Df3570dbD92b7FE905b699│
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  gl.nondet.exec_prompt()            │    │
│  │  → AI generates quiz question       │    │
│  └────────────────┬────────────────────┘    │
│                   │                         │
│  ┌────────────────▼────────────────────┐    │
│  │  gl.eq_principle.prompt_comparative │    │
│  │  → Validators reach consensus       │    │
│  └────────────────┬────────────────────┘    │
│                   │                         │
│  ┌────────────────▼────────────────────┐    │
│  │  TreeMap[Address, u256]             │    │
│  │  → XP stored on-chain permanently  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## 📋 GenLayer Bounty Requirements

| Requirement | ✅ Implementation |
|-------------|------------------|
| **Multiplayer** | `create_room()` + `join_room()` — host & guest system |
| **5–15 min duration** | 7 rounds × 20 seconds = ~8–10 min per game |
| **Replayable weekly** | `next_round()` — AI generates fresh question every round |
| **Leaderboard + XP** | `TreeMap[Address, u256]` — permanent on-chain scores |
| **IC showcase** | `gl.nondet.exec_prompt()` — AI generates all questions |
| **Optimistic Democracy** | `gl.eq_principle.prompt_comparative()` — validator consensus |

---

## 🗂 Repository Structure

```
Consensus-Quest/
├── consensus_quest_final.py   ← GenLayer Intelligent Contract
└── index.html                 ← Frontend (connects to contract)
```

---

## 🔧 Contract Methods

### Game Modes
| Mode | Topic |
|------|-------|
| `ic` | Intelligent Contracts, GenVM, Python |
| `od` | Optimistic Democracy, validators, consensus |
| `mixed` | Full GenLayer ecosystem |
| `debate` | AI debate judging, argument evaluation |

### Write Methods (transactions)

```python
# Register username on-chain
register(username: str) -> None

# Create room + AI generates question via validators
create_room(room_id: str, mode: str) -> None

# Join an existing room
join_room(room_id: str) -> None

# Submit answer — XP stored on-chain if correct
submit_room_answer(room_id: str, answer_index: u256) -> None

# Start next round — AI generates new question
next_round(room_id: str, mode: str) -> None

# Solo mode — generate question
generate_question(mode: str) -> None

# Solo mode — submit answer
submit_answer(answer_index: u256, round_num: u256) -> None
```

### Read Methods (free calls)

```python
# Get room state + question (without answer)
get_room(room_id: str) -> str  # JSON

# Check if answer is correct + get explanation
check_room_answer(room_id: str, answer_index: u256) -> str  # JSON

# Get global leaderboard (top 20)
get_leaderboard() -> str  # JSON

# Get player stats
get_player_stats(addr: Address) -> str  # JSON

# Get current round number
get_round() -> u256
```

---

## 🔑 Key GenLayer Features Used

### 1. `gl.nondet.exec_prompt()` — AI Question Generation
```python
def make_question():
    raw = gl.nondet.exec_prompt(prompt)
    raw = raw.replace("```json", "").replace("```", "").strip()
    # extract clean JSON
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    return raw[start:end]
```
Every round, the contract calls an LLM to generate a **fresh, unique GenLayer quiz question** — no pre-written question bank needed.

### 2. `gl.eq_principle.prompt_comparative()` — Optimistic Democracy
```python
return gl.eq_principle.prompt_comparative(
    make_question,
    "Both outputs must be valid JSON quiz questions about GenLayer "
    "with a question, 4 options, a correct index (0-3), and an explanation."
)
```
Multiple validators independently run the LLM and compare outputs. If they agree → consensus reached → question accepted. This is GenLayer's **Optimistic Democracy** in action.

### 3. `TreeMap[Address, u256]` — On-Chain Storage
```python
leaderboard:   TreeMap[Address, u256]   # wallet → total XP
usernames:     TreeMap[Address, str]    # wallet → username
correct_count: TreeMap[Address, u256]   # wallet → correct answers
games_played:  TreeMap[Address, u256]   # wallet → games played
rooms:         TreeMap[str, str]        # room_id → room state (JSON)
```
All game state is stored **permanently on GenLayer blockchain** — no database, no server.

---

## 🚀 Play the Game

### Option 1 — Browser (No Setup)
1. Visit **[https://kashif130.github.io/Consensus-Quest/](https://kashif130.github.io/Consensus-Quest/)**
2. Enter your name → Select game mode
3. Click **Start Game** — questions load from chain
4. Answer 7 rounds → see your XP on the leaderboard

### Option 2 — Deploy Your Own Contract
```bash
# 1. Open GenLayer Studio
#    https://studio.genlayer.com

# 2. Create new file → paste consensus_quest_final.py

# 3. Click Deploy → wait for validators to process

# 4. Copy your contract address

# 5. Update index.html line 285:
const CONTRACT_ADDRESS = "YOUR_CONTRACT_ADDRESS_HERE";

# 6. Deploy frontend → GitHub Pages or any static host
```

---

## 🌐 Links

| Resource | Link |
|----------|------|
| 🎮 Live Game | [kashif130.github.io/Consensus-Quest](https://kashif130.github.io/Consensus-Quest/) |
| 📦 GitHub | [github.com/Kashif130/Consensus-Quest](https://github.com/Kashif130/Consensus-Quest) |
| 📖 GenLayer Docs | [docs.genlayer.com](https://docs.genlayer.com) |
| 🔧 GenLayer Studio | [studio.genlayer.com](https://studio.genlayer.com) |
| 🌐 GenLayer Portal | [portal.genlayer.foundation](https://portal.genlayer.foundation) |

---

## 👤 Author

**mkashifalikcp** — Web3 builder & GenLayer community contributor

Built for the **GenLayer Mini-Games for Community** bounty.

---

*"Bringing AI consensus to on-chain gaming — one question at a time."* ⚡
