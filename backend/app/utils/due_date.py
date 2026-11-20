from __future__ import annotations
from datetime import datetime, timedelta, date
import logging
import holidays
from sqlalchemy import func

from app.config.database import SessionLocal
from app.models.plant_holiday import PlantHoliday

logger = logging.getLogger(__name__)

PLANT_COUNTRY = {
    "anhui": "CN",
    "kunshan": "CN",
    "tianjin": "CN",
    "chennai": "IN",
    "medina": "TN",
    "loire": "TN",
    "poitiers": "FR",
    "frankfort": "DE",
    "galeana": "MX",
    "monterrey": "MX",
    "rayones": "MX",
    "daegu": "KR",
    "carthage": "TN",
    "atlas": "TN",
}

EXTRA_HOLIDAYS_BY_PLANT: dict[str, set[date]] = {
    "kunshan": set(),
    "medina": set(),
}

# Country-calendar holidays that don't apply as a day off at specific plants,
# even though the `holidays` package marks them as public holidays for that
# country. Keyed by (month, day) since these are fixed-date observances.
EXCLUDED_HOLIDAYS_BY_PLANT: dict[str, set[tuple[int, int]]] = {
    # Tunisian Women's Day (Aug 13) is a national holiday but these plants
    # work through it.
    "medina": {(8, 13)},
    "loire": {(8, 13)},
    "carthage": {(8, 13)},
    "atlas": {(8, 13)},
}


def _get_db_extra_holidays_for_plant(plant: str, years: set[int]) -> dict[date, str]:
    """
    Fetch admin-managed plant holidays from DB.
    Uses a dedicated short-lived session to keep due-date utilities stateless.
    """
    plant_key = str(plant).lower()
    if not years:
        return {}

    start_date = date(min(years), 1, 1)
    end_date = date(max(years), 12, 31)

    db = SessionLocal()
    try:
        rows = (
            db.query(PlantHoliday)
            .filter(
                func.lower(PlantHoliday.plant) == plant_key,
                PlantHoliday.holiday_date >= start_date,
                PlantHoliday.holiday_date <= end_date,
            )
            .all()
        )
        return {
            row.holiday_date: (row.name or "Admin configured holiday")
            for row in rows
        }
    except Exception as exc:
        # Holiday computation must remain available even if DB extras fail.
        logger.warning("Failed loading admin holidays for plant '%s': %s", plant_key, exc)
        return {}
    finally:
        db.close()


def get_holiday_details_for_plant(plant: str, years: set[int]) -> dict[date, str]:
    """Return holiday date -> holiday name for a plant and years."""
    plant_key = str(plant).lower()
    if plant_key not in PLANT_COUNTRY:
        raise ValueError(f"Unknown plant for calendar: {plant_key}")

    country = PLANT_COUNTRY[plant_key]
    country_holidays = holidays.country_holidays(country, years=years)
    excluded = EXCLUDED_HOLIDAYS_BY_PLANT.get(plant_key, set())

    details: dict[date, str] = {}
    for holiday_date, holiday_name in country_holidays.items():
        if (holiday_date.month, holiday_date.day) in excluded:
            continue
        details[holiday_date] = str(holiday_name)

    for extra_date in EXTRA_HOLIDAYS_BY_PLANT.get(plant_key, set()):
        details.setdefault(extra_date, "Plant-specific holiday")

    for extra_date, extra_name in _get_db_extra_holidays_for_plant(plant_key, years).items():
        details.setdefault(extra_date, extra_name)

    return dict(sorted(details.items(), key=lambda item: item[0]))


def build_holidays_for_plant(plant: str, years: set[int]) -> set[date]:
    """Build holiday set for a specific plant and years."""
    return set(get_holiday_details_for_plant(plant, years).keys())


def is_working_day(d: date, holiday_set: set[date]) -> bool:
    """Check if date is a working day (not weekend, not holiday)."""
    return d.weekday() < 5 and d not in holiday_set


def count_working_days_between(
    start_date: date,
    end_date: date,
    holiday_set: set[date],
    *,
    include_start: bool = False,
    include_end: bool = True,
) -> int:
    """Count working days between two dates."""
    if end_date < start_date:
        return 0

    current = start_date if include_start else start_date + timedelta(days=1)
    count = 0
    while current <= end_date:
        if current == end_date and not include_end:
            break
        if is_working_day(current, holiday_set):
            count += 1
        current += timedelta(days=1)
    return count


def get_remaining_working_days(
    *,
    from_date: date,
    due_date: date,
    plant: str,
) -> int:
    """Return remaining working days from from_date until due_date."""
    if due_date < from_date:
        return -((from_date - due_date).days)

    years = {from_date.year, due_date.year, due_date.year + 1}
    holiday_set = build_holidays_for_plant(plant, years)
    return count_working_days_between(
        start_date=from_date,
        end_date=due_date,
        holiday_set=holiday_set,
        include_start=False,
        include_end=True,
    )


def compute_due_date(created_at: datetime, plant: str, workdays: int = 10) -> date:
    """
    Calculate initial due date: creation date + N working days.
    
    Example:
        Created: Monday Jan 1
        Workdays: 10
        Result: ~Friday Jan 12 (skipping weekends & holidays)
    """
    years = {created_at.date().year, created_at.date().year + 1}
    holiday_set = build_holidays_for_plant(plant, years)

    current = created_at.date()
    added = 0
    
    while added < workdays:
        current += timedelta(days=1)
        if is_working_day(current, holiday_set):
            added += 1
    
    return current


def count_unavailable_workdays(
    start_date: date,
    end_date: date,
    unavailability_periods: list[tuple[date, date]],
    holiday_set: set[date]
) -> int:
    """
    Count how many WORKING DAYS fall within unavailability periods.
    
    Example:
        Window: Jan 1 - Jan 15
        Unavailability: Jan 5 (Fri) - Jan 9 (Tue)
        Holidays: Jan 8
        Weekends: Jan 6-7
        Result: 3 working days (Jan 5, Jan 9; Jan 8 is holiday, Jan 6-7 weekend)
    """
    current = start_date
    unavailable_count = 0
    
    while current <= end_date:
        # Check if this is a working day
        if is_working_day(current, holiday_set):
            # Check if it falls in any unavailability period
            is_unavailable = any(
                period_start <= current <= period_end
                for period_start, period_end in unavailability_periods
            )
            if is_unavailable:
                unavailable_count += 1
        
        current += timedelta(days=1)
    
    return unavailable_count


def add_working_days(
    from_date: date,
    num_days: int,
    unavailability_periods: list[tuple[date, date]],
    holiday_set: set[date]
) -> date:
    """
    Add N working days to a date, skipping weekends, holidays, AND unavailability.
    
    Example:
        Start: Jan 8
        Add: 3 workdays
        Unavailability: Jan 10-12
        Result: Jan 17 (skips weekends, holidays, and Jan 10-12)
    """
    current = from_date
    added = 0
    
    while added < num_days:
        current += timedelta(days=1)
        
        # Check if it's a working day
        if is_working_day(current, holiday_set):
            # Check if auditee is available
            is_unavailable = any(
                period_start <= current <= period_end
                for period_start, period_end in unavailability_periods
            )
            
            # Only count if it's a working day AND auditee is available
            if not is_unavailable:
                added += 1
    
    return current


def recompute_due_date_from_base(
    created_at: datetime,
    plant: str,
    due_base: date,
    unavailability_periods: list[tuple[date, date]],
) -> date:
    """
    Recalculate due date based on unavailability periods.
    
    SIMPLE LOGIC:
    1. Count working days that fall in unavailability between creation -> due_base
    2. Add that many available working days after due_base
    
    Example:
        Created: Jan 1
        Due base: Jan 15 (10 workdays)
        Unavailability: Jan 8-10 (2 working days unavailable)
        New due: Jan 17 (original + 2 available workdays)
    """
    if not unavailability_periods:
        return due_base
    
    # Normalize periods to date objects
    normalized_periods = []
    for start, end in unavailability_periods:
        start = start.date() if isinstance(start, datetime) else start
        end = end.date() if isinstance(end, datetime) else end
        normalized_periods.append((start, end))
    
    # Calculate years needed for holidays
    years_needed = {created_at.date().year, due_base.year}
    for start, end in normalized_periods:
        years_needed.add(start.year)
        years_needed.add(end.year)
    years_needed.add(max(years_needed) + 1)
    
    holiday_set = build_holidays_for_plant(plant, years_needed)
    
    # Step 1: Count unavailable workdays in the original window
    window_start = created_at.date() + timedelta(days=1)
    unavailable_workdays = count_unavailable_workdays(
        start_date=window_start,
        end_date=due_base,
        unavailability_periods=normalized_periods,
        holiday_set=holiday_set
    )
    
    logger.info("Unavailable workdays in base window: %s", unavailable_workdays)
    
    if unavailable_workdays == 0:
        return due_base
    
    # Step 2: Add that many available workdays after due_base
    new_due = add_working_days(
        from_date=due_base,
        num_days=unavailable_workdays,
        unavailability_periods=normalized_periods,
        holiday_set=holiday_set
    )
    
    logger.info(
        "Due date recomputed from %s to %s (+%s working days)",
        due_base,
        new_due,
        unavailable_workdays,
    )
    
    return new_due
