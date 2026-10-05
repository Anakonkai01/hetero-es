import numpy as np
import pytest

from heteroes.es.update import standardize_rewards


def test_master_example_gives_the_hand_computed_coefficients():
    # rewards [0, 1, 1, 2]: mean 1, population std sqrt(0.5), so z = (R - 1) / sqrt(0.5)
    z = standardize_rewards([0, 1, 1, 2])

    assert z == pytest.approx([-(2**0.5), 0.0, 0.0, 2**0.5], rel=1e-6, abs=1e-7)


def test_master_example_update_is_0_106066():
    # MASTER 23.2.1 (P1): epsilon = [-1, 0, 1, 2], alpha = 0.1 -> d = 1.06066, update = 0.106066
    z = standardize_rewards([0, 1, 1, 2]).astype(np.float64)
    epsilon = np.array([-1.0, 0.0, 1.0, 2.0])

    direction = np.mean(z * epsilon)

    assert direction == pytest.approx(1.06066, rel=1e-5)
    assert 0.1 * direction == pytest.approx(0.106066, rel=1e-5)


def test_result_is_a_float32_array_of_the_same_length():
    z = standardize_rewards([0.2, 0.4, 0.9])

    assert isinstance(z, np.ndarray)
    assert z.dtype == np.float32
    assert z.shape == (3,)


def test_accepts_lists_tuples_arrays_and_ints():
    expected = standardize_rewards([1.0, 2.0, 4.0])

    assert np.array_equal(standardize_rewards((1, 2, 4)), expected)
    assert np.array_equal(standardize_rewards(np.array([1.0, 2.0, 4.0])), expected)


def test_does_not_modify_its_input():
    rewards = np.array([0.1, 0.5, 0.2])
    before = rewards.copy()

    standardize_rewards(rewards)

    assert np.array_equal(rewards, before)


def test_coefficients_have_mean_zero_and_unit_population_std():
    rewards = np.random.default_rng(0).uniform(0, 1, size=20)

    z = standardize_rewards(rewards).astype(np.float64)

    assert abs(z.mean()) < 1e-6
    assert z.std() == pytest.approx(1.0, abs=1e-6)  # population std, ddof = 0


def test_a_positive_affine_change_of_the_rewards_changes_nothing():
    rewards = np.array([0.1, 0.5, 0.2, 0.9])

    assert standardize_rewards(rewards * 3 + 7) == pytest.approx(standardize_rewards(rewards), rel=1e-5, abs=1e-6)


def test_coefficients_follow_the_rewards_when_they_are_reordered():
    rewards = [0.1, 0.5, 0.2, 0.9]
    order = [2, 0, 3, 1]

    z = standardize_rewards(rewards)
    z_permuted = standardize_rewards([rewards[i] for i in order])

    assert np.allclose(z_permuted, z[order], rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("rewards", [[0.5] * 5, [1.0], [0.0, 0.0], [3, 3, 3]])
def test_equal_rewards_give_all_zero_coefficients(rewards):
    # No signal: the update must be a no-op, never a division by (almost) zero.
    z = standardize_rewards(rewards)

    assert not z.any()
    assert z.dtype == np.float32


def test_a_spread_below_eta_counts_as_equal_and_above_eta_does_not():
    assert not standardize_rewards([1.0, 1.0 + 1e-9]).any()  # std 5e-10 < 1e-8
    assert standardize_rewards([1.0, 1.0 + 1e-3]).any()


def test_eta_is_a_parameter():
    rewards = [0.0, 1e-3]  # population std 5e-4

    assert standardize_rewards(rewards).any()
    assert not standardize_rewards(rewards, eta=1e-2).any()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_reward_is_rejected_not_turned_into_zero(bad):
    with pytest.raises(ValueError):
        standardize_rewards([0.1, bad, 0.3])


@pytest.mark.parametrize("bad", [[[0.1, 0.2], [0.3, 0.4]], 0.5], ids=["2-D", "single number"])
def test_rewards_must_be_a_one_dimensional_sequence(bad):
    # A matrix would otherwise be standardized as a whole and silently give a 2-D result.
    with pytest.raises(ValueError):
        standardize_rewards(bad)


def test_empty_rewards_are_rejected():
    with pytest.raises(ValueError):
        standardize_rewards([])


@pytest.mark.parametrize("bad_eta", [0.0, -1e-8, float("nan"), float("inf")])
def test_eta_must_be_positive_and_finite(bad_eta):
    with pytest.raises(ValueError):
        standardize_rewards([0.1, 0.2], eta=bad_eta)
