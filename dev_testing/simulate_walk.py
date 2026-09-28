# dev_testing/simulate_walk.py
# Fakes real-world progress against a running dev server, without waiting
# on a real Google Health sync to see the map move. Calls
# TravelFacade.record_steps() directly - the exact call the real webhook
# makes (services/google_health/webhook.py), just triggered by hand.
# Run after connecting via the website's Connect button and starting a
# trip from the "Where from? / Where to?" form (see CONNECT.md and
# TRIP_MAP.md).

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.connections import get_active_connection, get_active_user_id
from core.facade import travel_facade
from database import trips
from database.session import SessionLocal
from travel_logic.progress_calculator import resolve_stride_m

DEFAULT_STEPS = 3000

# Step a little PAST a checkpoint/the destination, not exactly onto it -
# otherwise floating-point rounding could leave a checkpoint just short of
# "hit" (distance_from_start_m <= distance_walked_m in
# database/trips.py's mark_checkpoints_hit).
OVERSHOOT_BUFFER_M = 1.0


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Credit fake steps to the connected user's active trip(s), for testing the live map without waiting on a real Google Health sync."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--steps", type=int, default=None,
        help=f"credit exactly this many steps to every active trip (default: {DEFAULT_STEPS} if no other mode is given)",
    )
    mode.add_argument(
        "--to-checkpoint", action="store_true",
        help="walk just far enough to cross the next unhit checkpoint on ONE trip (see --trip-id)",
    )
    mode.add_argument(
        "--finish", action="store_true",
        help="walk the remaining distance to complete ONE trip (see --trip-id)",
    )
    parser.add_argument(
        "--trip-id", type=str, default=None,
        help="which trip to target for --to-checkpoint/--finish - required if the user has more than one active trip",
    )
    return parser.parse_args()


def _steps_needed_for_distance(trip, distance_m: float) -> int:
    stride_m = resolve_stride_m(google_health_stride_m=trip.stride_length_m, gender=trip.gender)
    return max(1, math.ceil(distance_m / stride_m))


def _steps_to_credit(args, trip) -> int | None:
    """None means "nothing to do" (already finished, or no checkpoint left
    to walk to) - main() prints why and exits without calling record_steps."""
    if args.to_checkpoint:
        next_unhit_checkpoint = next((c for c in trip.checkpoints if c.hit_at is None), None)
        if next_unhit_checkpoint is None:
            print("No unhit checkpoints left on this trip - try --finish instead.")
            return None
        distance_m = (next_unhit_checkpoint.distance_from_start_m - trip.meters_walked) + OVERSHOOT_BUFFER_M
        return _steps_needed_for_distance(trip, distance_m)

    if args.finish:
        distance_m = (trip.total_distance_m - trip.meters_walked) + OVERSHOOT_BUFFER_M
        return _steps_needed_for_distance(trip, distance_m)

    return args.steps or DEFAULT_STEPS


def _pick_target_trip(args, active_trips):
    """--to-checkpoint/--finish need exactly one trip's route to compute a
    step count against - auto-picks when there's only one active trip,
    otherwise requires --trip-id (printing the options so that's easy to
    copy-paste)."""
    if args.trip_id:
        match = next((t for t in active_trips if str(t.id) == args.trip_id), None)
        if match is None:
            print(f"❌ No active trip with id {args.trip_id!r}.")
        return match

    if len(active_trips) == 1:
        return active_trips[0]

    print("❌ More than one active trip - pass --trip-id to pick one:")
    for trip in active_trips:
        print(f"  {trip.id}  {trip.from_place} -> {trip.to_place}")
    return None


def main():
    args = _parse_args()

    with SessionLocal() as session:
        user_id = get_active_user_id(session)
        connection = get_active_connection(session, user_id)
        print(f"connected: provider_user_id={connection.provider_user_id}")

        active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
        if not active_trips:
            print("❌ No active trip - start one from the website first, then re-run this.")
            return

        if args.to_checkpoint or args.finish:
            trip = _pick_target_trip(args, active_trips)
            if trip is None:
                return
            steps = _steps_to_credit(args, trip)
            if steps is None:
                return
        else:
            steps = args.steps or DEFAULT_STEPS

    states = travel_facade.record_steps(user_id, steps)

    print(f"credited {steps} steps to {len(states)} active trip(s)")
    for state in states:
        print(
            f"  {state['from_place']} -> {state['to_place']}: "
            f"distance_walked={state['miles_walked']:.2f} mi  percent_complete={state['percent_complete']:.1f}%"
        )
        for checkpoint in state["newly_hit_checkpoints"]:
            print(f"    🏁 newly hit: {checkpoint['name']}")
        if state["status"] == "completed":
            print("    🏆 trip completed!")


if __name__ == "__main__":
    main()
