"""Tests for task generation."""

from emergent_divergence.tasks.generator import TaskGenerator


def test_task_generation():
    gen = TaskGenerator(seed=42)
    task = gen.generate(round_id=0)
    assert task.task_id.startswith("task_0000_")
    assert len(task.claim) > 10
    assert task.instructions
    assert task.domain


def test_task_cycling():
    gen = TaskGenerator(seed=42)
    tasks = [gen.generate(i) for i in range(25)]
    claims = [t.claim for t in tasks]
    # Should use different claims (not all the same)
    assert len(set(claims)) > 1


def test_deterministic_with_seed():
    gen1 = TaskGenerator(seed=99)
    gen2 = TaskGenerator(seed=99)
    for i in range(10):
        assert gen1.generate(i).claim == gen2.generate(i).claim
