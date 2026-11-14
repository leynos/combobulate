//! An independent proleptic Gregorian oracle for the Verus release tests.
//!
//! The release validator asks whether a year, month and day exist. An expected
//! value built from the same month-length table would agree with a wrong
//! implementation, so this oracle instead converts a date to a day number and
//! back using Howard Hinnant's civil-from-days arithmetic. The round trip
//! depends only on arithmetic, which makes agreement independent evidence that
//! a date exists rather than a restatement of the rule under test.

/// Returns the day number for `year-month-day`, counted from 1970-01-01.
///
/// `month` must be in 1–12. Out-of-range days are normalized into a
/// neighbouring month rather than rejected, which is what lets the round trip
/// in [`is_real_date`] detect them. Division is Euclidean so the arithmetic
/// stays exact for dates before 1970 as well.
fn days_from_civil(year: i32, month: i32, day: i32) -> i32 {
    let shifted_year = if month <= 2 { year - 1 } else { year };
    let era = shifted_year.div_euclid(400);
    let year_of_era = shifted_year.rem_euclid(400);
    let month_index = if month > 2 { month - 3 } else { month + 9 };
    let day_of_year = (153 * month_index + 2).div_euclid(5) + day - 1;
    let day_of_era =
        year_of_era * 365 + year_of_era.div_euclid(4) - year_of_era.div_euclid(100) + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

/// Converts a day number counted from 1970-01-01 into a civil date.
fn civil_from_days(days: i32) -> (i32, i32, i32) {
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted.rem_euclid(146_097);
    let year_of_era = (day_of_era - day_of_era.div_euclid(1_460) + day_of_era.div_euclid(36_524)
        - day_of_era.div_euclid(146_096))
    .div_euclid(365);
    let year = year_of_era + era * 400;
    let day_of_year =
        day_of_era - (365 * year_of_era + year_of_era.div_euclid(4) - year_of_era.div_euclid(100));
    let month_index = (5 * day_of_year + 2).div_euclid(153);
    let day = day_of_year - (153 * month_index + 2).div_euclid(5) + 1;
    let month = if month_index < 10 {
        month_index + 3
    } else {
        month_index - 9
    };
    let civil_year = if month <= 2 { year + 1 } else { year };
    (civil_year, month, day)
}

/// Reports whether `year-month-day` exists in the proleptic Gregorian calendar.
///
/// A month outside 1–12 is never real. Any other candidate is real exactly
/// when converting it to a day number and back returns the same three fields,
/// so days such as the 0th or the 32nd are rejected by construction.
pub(crate) fn is_real_date(year: i32, month: i32, day: i32) -> bool {
    if !(1..=12).contains(&month) {
        return false;
    }
    civil_from_days(days_from_civil(year, month, day)) == (year, month, day)
}
