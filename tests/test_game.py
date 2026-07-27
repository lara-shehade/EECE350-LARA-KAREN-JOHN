"""
Seed tests for game.py — pure logic, no pygame/sockets required.

Run with: python -m pytest tests/ -v

This file is a starting point; the game-logic-test-writer subagent
(.claude/agents/game-logic-test-writer.md) is meant to extend it.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from game import GameState, Player, HEALTH_START, HEALTH_MAX, WALL_DAMAGE  # noqa: E402


def make_player_info():
    return {"color": [255, 0, 0], "head_style": "classic", "head_emoji": None}


def make_game():
    return GameState("alice", make_player_info(), "bob", make_player_info())


def test_new_player_starts_at_full_health_and_alive():
    game = make_game()
    assert game.player1.health == HEALTH_START
    assert game.player1.alive is True


def test_set_direction_ignores_180_reversal():
    game = make_game()
    # player1 starts moving RIGHT (1, 0); UP then DOWN is fine, but a direct
    # reversal to LEFT should be ignored.
    original_dir = game.player1.direction
    game.set_direction("alice", "LEFT")
    game.player1._apply_direction()
    assert game.player1.direction == original_dir, (
        "a direct 180-degree reversal should be ignored, not applied"
    )


def test_wall_hit_applies_damage_and_does_not_move_snake():
    player = Player(
        username="alice", color=[255, 0, 0], head_style="classic", head_emoji=None,
        start_pos=[(0, 7), (1, 7)], start_dir=(-1, 0),  # already at left edge, moving further left
    )
    head_before = player.snake[0]
    result = player.move()
    assert result == "wall"
    assert player.snake[0] == head_before, "snake should not move into the wall"
    assert player.health == HEALTH_START - WALL_DAMAGE


def test_apply_damage_respects_invincibility():
    player = Player(
        username="alice", color=[255, 0, 0], head_style="classic", head_emoji=None,
        start_pos=[(3, 7)], start_dir=(1, 0),
    )
    first_hit = player.apply_damage(10)
    assert first_hit is True
    health_after_first_hit = player.health

    # Immediately hitting again should be blocked by the invincibility
    # window granted by the first hit.
    second_hit = player.apply_damage(10)
    assert second_hit is False
    assert player.health == health_after_first_hit


def test_health_clamps_at_zero_and_marks_not_alive():
    player = Player(
        username="alice", color=[255, 0, 0], head_style="classic", head_emoji=None,
        start_pos=[(3, 7)], start_dir=(1, 0),
    )
    player.apply_damage(10_000)  # far more than max health
    assert player.health == 0
    assert player.alive is False


def test_health_clamps_at_max_on_heal():
    player = Player(
        username="alice", color=[255, 0, 0], head_style="classic", head_emoji=None,
        start_pos=[(3, 7)], start_dir=(1, 0),
    )
    player.apply_heal(10_000)
    assert player.health == HEALTH_MAX


def test_check_game_over_reports_winner_when_one_player_dies():
    game = make_game()
    game.player1.apply_damage(10_000)  # kill player1 outright
    # game_over/winner are only refreshed inside tick() (via
    # _evaluate_game_over()), not immediately on apply_damage — check_game_over
    # just reads the cached flag, so a tick is required first.
    game.tick()
    over, winner = game.check_game_over()
    assert over is True
    assert winner == "bob"
