# dev_testing/pull_data.py
# Standalone check: is the Google Health connection live, and what does it
# actually send back. No travel logic, no webhook - just a direct pull.
# Run after connecting via the website's Connect button (see CONNECT.md).

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.connections import get_active_connection, get_active_user_id
from database.session import SessionLocal
from services.google_health import client
from services.fitbitMetrics.fitbit_steps import StepsMetric
from services.fitbitMetrics.fitbit_exercise import ExerciseMetric
from services.fitbitMetrics.fitbit_sleep import SleepMetric
from services.fitbitMetrics.fitbit_user_data import UserMetric

DEFAULT_HOURS = 24


def _shaped(metric_cls, raw_points: list):
    """Raw dicts -> typed objects via the same Strategy classes the real
    webhook uses (services/fitbitMetrics/) - a point that doesn't match
    the schema prints its parse error instead of crashing the pull."""
    shaped = []
    for p in raw_points:
        try:
            shaped.append(metric_cls(p).metric_obj())
        except Exception as e:
            print(f"  [unshaped: {e}]  raw={p}")
    return shaped


def _parse_args():
    p = argparse.ArgumentParser(description="Pull recent Google Health data for the connected account.")
    p.add_argument("--hours", type=float, default=DEFAULT_HOURS, help=f"rolling window ending now, in hours (default: {DEFAULT_HOURS})")
    p.add_argument("--today", action="store_true", help="local midnight to now, in this machine's local time zone")
    p.add_argument("--start", help="explicit start time (ISO 8601, e.g. 2026-09-20 or 2026-09-20T08:00:00 - naive times are read as local)")
    p.add_argument("--end", help="explicit end time (ISO 8601, default: now)")
    return p.parse_args()


def _window(args):
    fmt = lambda t: t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    if args.start:
        start = datetime.fromisoformat(args.start).astimezone()
        end = datetime.fromisoformat(args.end).astimezone() if args.end else datetime.now().astimezone()
        return fmt(start), fmt(end)

    if args.today:
        now_local = datetime.now().astimezone()
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return fmt(start_local), fmt(now_local)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.hours)
    return fmt(start), fmt(end)


def main():
    args = _parse_args()

    with SessionLocal() as session:
        user_id = get_active_user_id(session)
        connection = get_active_connection(session, user_id)
        print(f"connected: provider_user_id={connection.provider_user_id} status={connection.status}")

    start, end = _window(args)
    print(f"pulling {start} -> {end}\n")

    steps_total = client.get_steps_total(start, end, user_id)
    steps = _shaped(StepsMetric, client.get_data_points("steps", start, end, user_id))
    print(f"STEPS: {steps_total} total (server-side rollup), {len(steps)} raw data point(s)")
    for s in steps:
        print(f"  {s.count} steps  ({s.interval.start_time} -> {s.interval.end_time})")
    if steps:
        newest_end = max(s.interval.end_time for s in steps)
        lag = datetime.now(timezone.utc) - datetime.fromisoformat(newest_end.replace("Z", "+00:00"))
        print(f"  newest data point ends {newest_end}  ({lag.total_seconds() / 60:.1f} min ago - Fitbit/Google sync lag, not a bug)")

    # Rollup summary, not raw samples: heart-rate is sampled every few
    # seconds, so pulling every point for a wide window means dozens of
    # paginated requests just to see a number - one rollup call instead.
    hr_summary = client.get_heart_rate_summary(start, end, user_id)
    if hr_summary:
        print(f"HEART RATE: avg={hr_summary['avg_bpm']:.0f} bpm  min={hr_summary['min_bpm']:.0f}  max={hr_summary['max_bpm']:.0f}  (server-side rollup)")
    else:
        print("HEART RATE: no data in this window")

    sleep = _shaped(SleepMetric, client.get_data_points("sleep", start, end, user_id))
    print(f"\nSLEEP: {len(sleep)} session(s)  (minutesAsleep/minutesAwake only - Google Health has no sleep score field)")
    for s in sleep:
        print(f"  {s.summary.minutes_asleep} min asleep, {s.summary.minutes_awake} min awake  ({s.interval.start_time} -> {s.interval.end_time})")

    exercise = _shaped(ExerciseMetric, client.get_data_points("exercise", start, end, user_id))
    print(f"\nACTIVITY: {len(exercise)} session(s)")
    for e in exercise:
        summary = e.metrics_summary
        print(
            f"  {e.exercise_type}  ({e.interval.start_time} -> {e.interval.end_time})  "
            f"steps={summary.steps} distance_mm={summary.distance_millimeters} "
            f"calories_kcal={summary.calories_kcal} avg_hr_bpm={summary.average_heart_rate_bpm} "
            f"avg_pace_s_per_m={summary.average_pace_s_per_m} avg_speed_mm_per_s={summary.average_speed_mm_per_s}"
        )

    try:
        profile = UserMetric(client.get_profile(user_id)).metric_obj()
        print(f"\nPROFILE: age={profile.age} walking_stride_mm={profile.walking_stride_length_mm} running_stride_mm={profile.running_stride_length_mm}")
    except Exception as e:
        print(f"\nPROFILE: pull failed ({e})")


if __name__ == "__main__":
    main()
