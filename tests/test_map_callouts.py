"""Pure regression checks for ranked native-map callout placement."""

from __future__ import annotations

import unittest

from wevva.widgets.map_callouts import (
    DirectionalCalloutCandidate,
    DirectionalCalloutPolicy,
    plan_directional_callouts,
)


FIXED_MARKER_POLICY = DirectionalCalloutPolicy(allow_row_shift=False)


def _marker(placement) -> tuple[int, int]:
    column = (
        placement.column + placement.width - 1
        if placement.marker_on_right
        else placement.column
    )
    return column, placement.row


class RankedCalloutPlacementTests(unittest.TestCase):
    def test_neighbours_share_a_row_without_moving_either_marker(self) -> None:
        candidates = (
            DirectionalCalloutCandidate('west', (5, 1), 5),
            DirectionalCalloutCandidate('east', (8, 1), 5),
        )

        placements = plan_directional_callouts(
            candidates,
            canvas_width=14,
            canvas_height=3,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertEqual([placement.key for placement in placements], ['west', 'east'])
        self.assertEqual([_marker(placement) for placement in placements], [(5, 1), (8, 1)])
        self.assertTrue(placements[0].marker_on_right)
        self.assertFalse(placements[1].marker_on_right)

    def test_higher_priority_candidate_can_claim_lower_priority_anchor(self) -> None:
        candidates = (
            DirectionalCalloutCandidate('high', (3, 0), 5),
            DirectionalCalloutCandidate('low', (6, 0), 2),
        )

        placements = plan_directional_callouts(
            candidates,
            canvas_width=8,
            canvas_height=1,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertEqual([placement.key for placement in placements], ['high'])
        self.assertEqual(_marker(placements[0]), (3, 0))

    def test_identical_anchors_keep_only_the_higher_priority_callout(self) -> None:
        placements = plan_directional_callouts(
            (
                DirectionalCalloutCandidate('first', (4, 0), 3),
                DirectionalCalloutCandidate('second', (4, 0), 3),
            ),
            canvas_width=9,
            canvas_height=1,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertEqual([placement.key for placement in placements], ['first'])

    def test_overlong_callout_is_omitted(self) -> None:
        placements = plan_directional_callouts(
            (DirectionalCalloutCandidate('wide', (0, 0), 99),),
            canvas_width=5,
            canvas_height=1,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertEqual(placements, ())

    def test_avoidance_prefers_the_clear_direction_but_is_not_mandatory(self) -> None:
        candidate = DirectionalCalloutCandidate(
            'place',
            (5, 0),
            4,
            preferred_avoidance=frozenset({(6, 0), (7, 0)}),
        )
        clear = plan_directional_callouts(
            (candidate,),
            canvas_width=10,
            canvas_height=1,
            policy=FIXED_MARKER_POLICY,
        )
        unavoidable = plan_directional_callouts(
            (
                DirectionalCalloutCandidate(
                    'place',
                    (5, 0),
                    4,
                    preferred_avoidance=frozenset(
                        {(column, 0) for column in range(2, 9)} - {(5, 0)}
                    ),
                ),
            ),
            canvas_width=10,
            canvas_height=1,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertTrue(clear[0].marker_on_right)
        self.assertEqual(_marker(unavoidable[0]), (5, 0))

    def test_row_shift_requires_an_explicit_marker_safe_policy(self) -> None:
        candidate = (DirectionalCalloutCandidate('label', (4, 1), 3),)
        occupied = {(2, 1), (5, 1)}

        fixed = plan_directional_callouts(
            candidate,
            canvas_width=9,
            canvas_height=3,
            occupied=occupied,
            policy=FIXED_MARKER_POLICY,
        )
        shifted = plan_directional_callouts(
            candidate,
            canvas_width=9,
            canvas_height=3,
            occupied=occupied,
            policy=DirectionalCalloutPolicy(allow_row_shift=True),
        )

        self.assertEqual(fixed, ())
        self.assertEqual(shifted[0].row, 0)

    def test_exact_fallback_preserves_a_crowded_fix_anchor(self) -> None:
        placements = plan_directional_callouts(
            (
                DirectionalCalloutCandidate('fix', (3, 0), 7, fallback_width=1),
                DirectionalCalloutCandidate('later', (4, 0), 2, fallback_width=1),
            ),
            canvas_width=7,
            canvas_height=1,
            policy=DirectionalCalloutPolicy(
                allow_row_shift=False,
                retain_higher_priority=False,
            ),
        )

        self.assertEqual([_marker(placement) for placement in placements], [(3, 0), (4, 0)])
        self.assertTrue(placements[0].used_fallback)

    def test_repeated_planning_is_stable_and_does_not_mutate_input(self) -> None:
        occupied = {(0, 0)}
        candidates = (
            DirectionalCalloutCandidate('one', (3, 0), 3),
            DirectionalCalloutCandidate('two', (7, 0), 3),
        )

        first = plan_directional_callouts(
            candidates,
            canvas_width=10,
            canvas_height=2,
            occupied=occupied,
            policy=FIXED_MARKER_POLICY,
        )
        second = plan_directional_callouts(
            candidates,
            canvas_width=10,
            canvas_height=2,
            occupied=occupied,
            policy=FIXED_MARKER_POLICY,
        )

        self.assertEqual(first, second)
        self.assertEqual(occupied, {(0, 0)})


if __name__ == '__main__':
    unittest.main()
