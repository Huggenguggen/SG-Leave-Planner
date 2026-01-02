#!/usr/bin/env python3
"""
leave_planner.py
A simple CLI program that reads Singapore public holiday ICS files and a holidays.csv,
then generates an HTML calendar highlighting working days (green), public holidays (purple),
user planned leave (red), and days that are both public holidays and leave (blue).
It also reports the number of annual leave days used (leave taken on working days that are not public holidays).
"""

import argparse
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from typing import Iterable, List, Set

# ------------------------------
# ICS parsing utilities (no external packages)
# ------------------------------

def unfold_ics_lines(lines: List[str]) -> List[str]:
    """
    Unfold folded iCalendar lines (RFC 5545). Continuation lines start with a single space.
    """
    unfolded: List[str] = []
    for raw in lines:
        line = raw.rstrip('\n').rstrip('\r')
        if not unfolded:
            unfolded.append(line)
        else:
            if line.startswith(' '):
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
    return unfolded


def parse_ics_dtstart_dates(file_path: Path) -> Set[date]:
    """Parse DTSTART dates (VALUE=DATE) from VEVENT blocks in the given .ics file."""
    dates: Set[date] = set()
    if not file_path.exists():
        return dates
    try:
        with file_path.open('r', encoding='utf-8') as f:
            raw_lines = f.readlines()
    except UnicodeDecodeError:
        # Try latin-1 if utf-8 fails
        with file_path.open('r', encoding='latin-1') as f:
            raw_lines = f.readlines()

    lines = unfold_ics_lines(raw_lines)
    in_event = False
    for line in lines:
        if line.startswith('BEGIN:VEVENT'):
            in_event = True
        elif line.startswith('END:VEVENT'):
            in_event = False
        elif in_event and line.startswith('DTSTART'):
            # e.g. "DTSTART;VALUE=DATE:20250101" or "DTSTART:20250101"
            try:
                _, value = line.split(':', 1)
                value = value.strip()
                # Sometimes DTSTART might include time. We only care about YYYYMMDD.
                value = value[:8]
                d = datetime.strptime(value, '%Y%m%d').date()
                dates.add(d)
            except Exception:
                # Skip malformed lines
                pass
    return dates


def load_public_holidays(public_dir: Path) -> Set[date]:
    """Load public holidays from all files matching 'public-holidays-sg-*.ics' in the directory."""
    all_dates: Set[date] = set()
    if not public_dir.exists():
        return all_dates
    for p in sorted(public_dir.glob('public-holidays-sg-*.ics')):
        all_dates |= parse_ics_dtstart_dates(p)
    return all_dates

# ------------------------------
# Holidays.csv parsing
# ------------------------------

def parse_holiday_ranges(csv_path: Path) -> Set[date]:
    """
    Parse a comma-separated list of ranges like 'yyyymmdd-yyyymmdd,yyyymmdd-yyyymmdd' into a set of dates.
    File may contain newlines; all tokens are aggregated.
    """
    dates: Set[date] = set()
    if not csv_path.exists():
        return dates
    content = csv_path.read_text(encoding='utf-8').strip()
    # Allow whitespace and newlines
    tokens = [tok.strip() for tok in content.replace('\n', ',').split(',') if tok.strip()]
    for tok in tokens:
        if '-' not in tok:
            # Single day support: 'yyyymmdd'
            try:
                d = datetime.strptime(tok, '%Y%m%d').date()
                dates.add(d)
            except Exception:
                pass
            continue
        start_s, end_s = tok.split('-', 1)
        try:
            start_d = datetime.strptime(start_s, '%Y%m%d').date()
            end_d = datetime.strptime(end_s, '%Y%m%d').date()
            if end_d < start_d:
                start_d, end_d = end_d, start_d
            cur = start_d
            while cur <= end_d:
                dates.add(cur)
                cur += timedelta(days=1)
        except Exception:
            # Skip malformed tokens
            continue
    return dates



def parse_leave_csv(csv_path: Path) -> dict:
    """
    Parse leave.csv that holds: leave-package,leave-to-carry-over,misc-leave,carry-over-cap
    Returns dict: {'package': int, 'carry_over': int, 'misc': int, 'cap': int}
    If file is missing or malformed, defaults to 0s.
    """
    defaults = {'package': 0, 'carry_over': 0, 'misc': 0, 'cap': 0}
    if not csv_path.exists():
        return defaults
    try:
        line = csv_path.read_text(encoding='utf-8').strip()
        for token in line.splitlines():
            token = token.strip()
            if not token:
                continue
            parts = [p.strip() for p in token.split(',')]
            if len(parts) != 4:
                return defaults
            package = int(parts[0])
            carry = int(parts[1])
            misc = int(parts[2])
            cap = int(parts[3])
            return {'package': package, 'carry_over': carry, 'misc': misc, 'cap': cap}
    except Exception:
        pass
    return defaults




def compute_leave_entitlements(leave_info: dict, current_year: int) -> dict:
    """
    Returns a dict mapping year -> entitlement.
    current_year: carry_over only.
    next_year: package + min(carry_over, cap) + misc.
    Also returns 'burned' (carry_over - cap if positive).
    """
    carry = leave_info.get('carry_over', 0)
    package = leave_info.get('package', 0)
    misc = leave_info.get('misc', 0)
    cap = leave_info.get('cap', 0)

    next_year = current_year + 1
    carry_allowed = min(carry, cap)
    burned = max(carry - cap, 0)

    entitlements = {
        current_year: carry,
        next_year: package + carry_allowed + misc
    }
    # Attach burned as a separate key
    return {'entitlements': entitlements, 'burned': burned}




# ------------------------------
# Calendar generation
# ------------------------------

class LeaveHTMLCalendar(calendar.HTMLCalendar):
    def __init__(self, working_days: List[int], holiday_dates: Set[date], public_holidays: Set[date]):
        super().__init__(firstweekday=0)  # Monday=0
        if len(working_days) != 7 or any(d not in (0, 1) for d in working_days):
            raise ValueError('working_days must be a list of 7 integers (0 or 1), Monday..Sunday.')
        self.working_days = working_days
        self.holiday_dates = holiday_dates
        self.public_holidays = public_holidays
        self._yyyy = None
        self._mm = None

    def formatmonth(self, theyear, themonth, withyear=True):
        self._yyyy = theyear
        self._mm = themonth
        return super().formatmonth(theyear, themonth, withyear)

    def _status_for(self, y: int, m: int, d: int) -> str:
        cur = date(y, m, d)
        is_public = cur in self.public_holidays
        is_holiday = cur in self.holiday_dates
        is_working = bool(self.working_days[cur.weekday()])
        # Precedence: both (blue) > public (purple) > holiday (red) > workday (green)
        if is_public and is_holiday:
            return 'both'
        if is_public:
            return 'public'
        if is_holiday:
            return 'holiday'
        if is_working:
            return 'workday'
        return ''

    def formatday(self, day, weekday):
        if day == 0:
            return '<td class="noday">&nbsp;</td>'
        cssclass = self.cssclasses[weekday]
        status = self._status_for(self._yyyy, self._mm, day)
        extra_class = f' {status}' if status else ''
        return f'<td class="{cssclass}{extra_class}">{day}</td>'

# ------------------------------
# HTML page assembly
# ------------------------------



def build_html_page(
    years: Iterable[int],
    working_days: List[int],
    holiday_dates: Set[date],
    public_holidays: Set[date],
    title: str,
    annual_leave_used: int,
    leave_left_by_year: dict,   # existing
    burned_leave: int           # NEW
) -> str:
    cal = LeaveHTMLCalendar(working_days, holiday_dates, public_holidays)
    years_sorted = sorted(set(years))
    css = """
    <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
    h1, h2 { margin: 0.5em 0; }
    .legend span { display:inline-block; padding:4px 8px; margin-right:8px; border:1px solid #ddd; border-radius:4px; }
    table { border-collapse: collapse; margin: 8px; }
    th { background:#f0f0f0; }
    th, td { border: 1px solid #ddd; padding: 4px; text-align: center; }
    .workday { background: #d4edda; }      /* green */
    .public  { background: #e2d1f9; }      /* purple */
    .holiday { background: #f8d7da; }      /* red */
    .both    { background: #cfe2ff; }      /* blue */
    .noday   { background: #f9f9f9; }
    .month-container { display:flex; flex-wrap:wrap; gap: 12px; }
    .month-container table { width: 280px; }
    .summary { padding: 8px; background: #f6f6f6; border: 1px solid #ddd; border-radius: 4px; }
    </style>
    """
    parts = [
        '<!doctype html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        f'<title>{title}</title>',
        css,
        '</head>',
        '<body>',
        f'<h1>{title}</h1>',
        f'<div class="summary"><strong>Annual leave used:</strong> {annual_leave_used} day(s)</div>',
        '<div class="legend">',
        '<span class="workday">Working day</span>',
        '<span class="public">Public holiday</span>',
        '<span class="holiday">Planned leave</span>',
        '<span class="both">Public holiday + Leave</span>',
        '</div>'
    ]
    
    # NEW: annual leave left section
    parts.append('<div class="summary">')
    parts.append('<strong>Annual leave left:</strong>')
    # Show for each year we have data
    for y in sorted(leave_left_by_year.keys()):
        parts.append(f'<div>Year {y}: {leave_left_by_year[y]} day(s)</div>')
    parts.append('</div>')

    # NEW: burned leave section (applies to carry that exceeds cap when rolling into next year)
    parts.append('<div class="summary">')
    parts.append(f'<strong>Burned leave (exceeds carry-over cap):</strong> {burned_leave} day(s)')
    parts.append('</div>')

    for y in years_sorted:
        parts.append(f'<h2>{y}</h2>')
        parts.append('<div class="month-container">')
        for m in range(1, 13):
            parts.append(cal.formatmonth(y, m))
        parts.append('</div>')
    parts.append('</body></html>')
    return '\n'.join(parts)

# ------------------------------
# CLI logic
# ------------------------------

def compute_annual_leave_used(holiday_dates: Set[date], public_holidays: Set[date], working_days: List[int]) -> int:
    count = 0
    for d in holiday_dates:
        if working_days[d.weekday()] == 1 and d not in public_holidays:
            count += 1
    return count


def compute_annual_leave_used_by_year(holiday_dates: Set[date], public_holidays: Set[date], working_days: List[int]) -> dict:
    """
    Returns a dict: {year: used_days}, counting leave on working days excluding public holidays.
    """
    used_by_year = {}
    for d in holiday_dates:
        if working_days[d.weekday()] == 1 and d not in public_holidays:
            used_by_year[d.year] = used_by_year.get(d.year, 0) + 1
    return used_by_year


def years_from_dates(*sets: Iterable[date]) -> Set[int]:
    ys: Set[int] = set()
    for s in sets:
        for d in s:
            ys.add(d.year)
    return ys


def parse_working_days(s: str) -> List[int]:
    s = s.strip()
    if len(s) != 7 or any(ch not in '01' for ch in s):
        raise ValueError('Working days must be 7 characters of 0/1 (e.g., 1111100 for Mon-Fri).')
    return [int(ch) for ch in s]


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description='Plan leave and generate an HTML calendar highlighting working days, public holidays, and planned leave.')
    parser.add_argument('--public-dir', default='public-holidays', help='Directory containing public-holidays-sg-<year>.ics files (default: public-holidays)')
    parser.add_argument('--csv', default='holidays.csv', help='CSV file listing leave ranges like yyyymmdd-yyyymmdd, separated by commas (default: holidays.csv)')
    parser.add_argument('--working-days', default='1111100', help='7 chars (Mon..Sun) of 0/1 indicating working days (default: 1111100)')
    parser.add_argument('--out', default='leave_plan.html', help='Output HTML file path (default: leave_plan.html)')
    parser.add_argument('--title', default='Leave Planner', help='Title for the generated HTML page')
    parser.add_argument('--leave-csv', default='leave.csv', help='CSV file with leave-package,leave-to-carry-over,misc-leave (default: leave.csv)')    
    parser.add_argument(
        '--show-years',
        choices=['current', 'next', 'both'],
        default='both',
        help='Choose which year(s) to render in HTML: current, next, or both (default: both)'
    )

    args = parser.parse_args(argv)

    public_dir = Path(args.public_dir)
    csv_path = Path(args.csv)
    out_path = Path(args.out)
    working_days = parse_working_days(args.working_days)

    public_holidays = load_public_holidays(public_dir)
    holiday_dates = parse_holiday_ranges(csv_path)

    # NEW: leave entitlements current and next year
    leave_csv_path = Path(args.leave_csv)
    leave_info = parse_leave_csv(leave_csv_path)
    current_year = date.today().year
    result = compute_leave_entitlements(leave_info, current_year)
    entitlements = result['entitlements']
    burned_leave = result['burned']


    # Used per year
    used_by_year = compute_annual_leave_used_by_year(holiday_dates, public_holidays, working_days)
    
    # Compute leave left by year = entitlement - used
    leave_left_by_year = {}
    for y, entitlement in entitlements.items():
        used = used_by_year.get(y, 0)
        leave_left_by_year[y] = max(entitlement - used, 0)  # no negative

    burned_leave = max(burned_leave - used_by_year.get(date.today().year, 0), 0)

    current_year = date.today().year
    next_year = current_year + 1

    # Years discovered from data
    ys = years_from_dates(public_holidays, holiday_dates)
    if not ys:
        ys = {current_year}

    # Ensure entitlements years are considered
    ys |= set(entitlements.keys())

    # Filter based on --show-years
    if args.show_years == 'current':
        ys = {current_year}
    elif args.show_years == 'next':
        ys = {next_year}
    else:
        ys = {current_year, next_year}

    leave_left_by_year = {y: leave_left_by_year.get(y, 0) for y in sorted(ys)}
    annual_leave_used = compute_annual_leave_used(holiday_dates, public_holidays, working_days)


    html = build_html_page(
        ys, working_days, holiday_dates, public_holidays, args.title,
        annual_leave_used, leave_left_by_year, burned_leave
    )

    try:
        out_path.write_text(html, encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f'Failed to write HTML file: {e}\n')

    # Print HTML to stdout so the program "prints out the output in html"; summary is included at the top of the HTML.
    print(html)

    # Also print the numeric count to stderr so it is available separately without corrupting HTML output.

    sys.stderr.write(f'Annual leave used: {annual_leave_used} day(s)\n')
    for y in sorted(leave_left_by_year.keys()):
        sys.stderr.write(f'Annual leave left ({y}): {leave_left_by_year[y]} day(s)\n')
        sys.stderr.write(f'Burned leave (exceeds carry-over cap): {burned_leave} day(s)\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
