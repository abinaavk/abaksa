# logic.py
# All the actual billing math lives here - working out the bill amount,
# late fines, and checking if someone's usage looks unusually high.
# We kept this separate from db.py and gui.py on purpose, so if someone
# asks "how exactly do you calculate the bill" in the viva, you can just
# point to this one file instead of hunting through the GUI code.

from datetime import date, datetime, timedelta


def calculate_energy_charge(units, slabs):
    # This works exactly like income tax slabs. slabs is a list of
    # (upto_units, rate) pairs sorted from lowest to highest. So the
    # first bunch of units get charged at the cheapest rate, then the
    # next bunch at a higher rate, and so on. The very last slab has
    # None as its limit which just means "everything above this point".
    remaining = units
    total_charge = 0.0
    lower_limit = 0
    breakdown = []

    for upper_limit, rate in slabs:
        if remaining <= 0:
            break

        if upper_limit is None:
            units_in_this_slab = remaining
        else:
            units_in_this_slab = min(remaining, upper_limit - lower_limit)

        if units_in_this_slab < 0:
            units_in_this_slab = 0

        charge_for_slab = units_in_this_slab * rate

        if units_in_this_slab > 0:
            breakdown.append({
                "from": lower_limit,
                "to": lower_limit + units_in_this_slab,
                "units": units_in_this_slab,
                "rate": rate,
                "amount": round(charge_for_slab, 2),
            })

        total_charge = total_charge + charge_for_slab
        remaining = remaining - units_in_this_slab

        if upper_limit is not None:
            lower_limit = upper_limit
        else:
            lower_limit = lower_limit + units_in_this_slab

    return round(total_charge, 2), breakdown


def calculate_bill(units_consumed, connection_type, tariff_cfg):
    # puts together the full bill: energy charge (slab based) + fixed
    # monthly charge + surcharge + tax - subsidy (if they qualify)
    slabs = []
    for s in tariff_cfg["slabs"][connection_type]:
        slabs.append(tuple(s))

    energy_charge, breakdown = calculate_energy_charge(units_consumed, slabs)
    fixed_charge = tariff_cfg["fixed_charges"][connection_type]

    subtotal = energy_charge + fixed_charge
    surcharge = round(subtotal * tariff_cfg["surcharge_rate"], 2)
    tax = round(subtotal * tariff_cfg["tax_rate"], 2)

    # small domestic customers who used very little power get a rebate
    subsidy = 0.0
    if connection_type == "Domestic":
        if units_consumed <= tariff_cfg["subsidy_unit_threshold"]:
            subsidy = tariff_cfg["subsidy_amount"]

    total = subtotal + surcharge + tax - subsidy
    total = round(total, 2)
    if total < 0:
        total = 0.0

    return {
        "energy_charge": energy_charge,
        "fixed_charge": fixed_charge,
        "surcharge": surcharge,
        "tax": tax,
        "subsidy": subsidy,
        "total_amount": total,
        "slab_breakdown": breakdown,
    }


def calculate_due_date(bill_date, tariff_cfg):
    # bill_date can come in either as a date object or as a plain string
    # like "2026-08-21" (that's how it's stored in the database), so we
    # handle both here
    if isinstance(bill_date, str):
        bill_date = date.fromisoformat(bill_date)
    due = bill_date + timedelta(days=tariff_cfg["due_period_days"])
    return due.isoformat()


def calculate_late_fine(bill_amount, due_date, tariff_cfg, as_of=None):
    # works out the late fine based on how many days overdue the bill is.
    # there's a short grace period where no fine is charged, and after
    # that it grows a little bit every day but never goes past a cap
    # (so someone who forgets to pay for a year doesn't get charged more
    # than the bill itself many times over).
    if as_of is None:
        as_of = date.today()
    if isinstance(due_date, str):
        due_date = date.fromisoformat(due_date)

    days_overdue = (as_of - due_date).days
    grace_days = tariff_cfg["late_fine_grace_days"]

    if days_overdue <= grace_days:
        if days_overdue > 0:
            return 0.0, days_overdue, "Overdue"
        else:
            return 0.0, days_overdue, "Unpaid"

    chargeable_days = days_overdue - grace_days
    fine = bill_amount * tariff_cfg["late_fine_rate_per_day"] * chargeable_days
    max_allowed_fine = bill_amount * tariff_cfg["late_fine_max_fraction"]

    if fine > max_allowed_fine:
        fine = max_allowed_fine

    return round(fine, 2), days_overdue, "Overdue"


def detect_anomaly(units_consumed, past_bills, multiplier, min_history):
    # simple way of catching bills that look "off" - if this month's usage
    # is way higher than what the customer normally uses, flag it so the
    # admin can double check (could be a meter fault, a leak, theft, etc)
    past_values = []
    for b in past_bills:
        if b is not None:
            past_values.append(b)

    if len(past_values) < min_history:
        # not enough history yet to know what "normal" looks like
        return False, None

    average = sum(past_values) / len(past_values)

    if average <= 0:
        return False, average

    is_anomalous = units_consumed > average * multiplier
    return is_anomalous, round(average, 2)


def format_currency(amount):
    # just a little helper so we don't have to type the rupee symbol
    # and the formatting everywhere
    return "\u20b9" + format(amount, ",.2f")
