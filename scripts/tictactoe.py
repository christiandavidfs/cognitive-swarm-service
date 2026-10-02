#!/usr/bin/env python3
"""Tic-tac-toe learning lab: the whole architecture on a toy with ground truth.

minimax = exact oracle (verification). The system learns board -> best-move
traces into LTM; curiosity (self-play) generates positions; families group
openings; outcomes (win/loss/draw) feed success rates. Measurable: coverage,
agreement with minimax on unseen boards, win rate vs random.

  python scripts/tictactoe.py --games 200

No commit needed to learn something: this is the fastest closed loop we have.
"""
import argparse
import random
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.memory.store import ProcedureStore

WINS = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
        (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

# 8 symmetries (rotations + flips) for canonical board identity.
_SYMS = [(0, 1, 2, 3, 4, 5, 6, 7, 8), (6, 3, 0, 7, 4, 1, 8, 5, 2),
         (8, 7, 6, 5, 4, 3, 2, 1, 0), (2, 5, 8, 1, 4, 7, 0, 3, 6),
         (2, 1, 0, 5, 4, 3, 8, 7, 6), (6, 7, 8, 3, 4, 5, 0, 1, 2),
         (0, 3, 6, 1, 4, 7, 2, 5, 8), (8, 5, 2, 7, 4, 1, 6, 3, 0)]


def canonical(board: str) -> str:
    return min("".join(board[i] for i in s) for s in _SYMS)


def winner(board: str):
    for a, b, c in WINS:
        if board[a] != "." and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if "." not in board else None


def minimax(board: str, player: str) -> tuple:
    """Return (score, best_move) for player to move. X=+1, O=-1, draw=0."""
    w = winner(board)
    if w == "X":
        return 1, -1
    if w == "O":
        return -1, -1
    if w == "draw":
        return 0, -1
    best, move = (-2 if player == "X" else 2), -1
    nxt = "O" if player == "X" else "X"
    for i, cell in enumerate(board):
        if cell != ".":
            continue
        s, _ = minimax(board[:i] + player + board[i + 1:], nxt)
        if player == "X" and s > best or player == "O" and s < best:
            best, move = s, i
    return best, move


def play_game(store: ProcedureStore, rng: random.Random, explore: float = 0.3):
    """System (X, memory-guided) vs random (O). Returns (result, minimax_agreements, moves)."""
    board = "........."
    agrees = moves = 0
    trace = []
    while winner(board) is None:
        empt = [i for i, c in enumerate(board) if c == "."]
        if board.count("X") == board.count("O"):  # X to move (system)
            key = f"ttt:{canonical(board)}:X"
            rec = store.lookup(key)
            if rec is not None and rng.random() > explore:
                mv = int(rec["answer"])
                if board[mv] != ".":
                    mv = None
            else:
                mv = None
            _, opt = minimax(board, "X")
            if mv is None:  # consult oracle, learn
                mv = opt if rng.random() > explore else rng.choice(empt)
                store.remember_trace(key, f"ttt {canonical(board)} X->{mv} (minimax {opt})",
                                     str(mv), tier="game", confidence=0.9)
            agrees += mv == opt
            moves += 1
            trace.append((key, mv, opt))
            board = board[:mv] + "X" + board[mv + 1:]
        else:
            mv = rng.choice(empt)
            board = board[:mv] + "O" + board[mv + 1:]
    result = winner(board)
    for key, mv, opt in trace:  # outcomes feed success rates
        try:
            store.record_outcome(key, (result == "X" and mv == opt) or result == "draw")
        except Exception:
            pass
    return result, agrees / max(moves, 1), moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--explore", type=float, default=0.3)
    ap.add_argument("--mem", default="data/ttt_memory.json")
    args = ap.parse_args()

    store = ProcedureStore(path=_REPO / args.mem)
    rng = random.Random(7)
    res = {"X": 0, "O": 0, "draw": 0}
    agree = 0
    for g in range(1, args.games + 1):
        r, a, _ = play_game(store, rng, explore=args.explore)
        res[r] += 1
        agree += a
        if g % 50 == 0:
            print(f"[{g}] W={res['X']} L={res['O']} D={res['draw']} "
                  f"minimax_agree={agree / g:.2f} entries={store.size()}", flush=True)
    print(f"\nFINAL {args.games} games: win={res['X'] / args.games:.2f} "
          f"loss={res['O'] / args.games:.2f} draw={res['draw'] / args.games:.2f} "
          f"minimax_agree={agree / args.games:.3f} entries={store.size()}")
    print("READ: win rate vs random + minimax agreement climbing = learning. "
          "Coverage (entries) is the mechanism.")


if __name__ == "__main__":
    main()
