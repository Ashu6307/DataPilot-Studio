# Pivot and Unpivot Engine

Pivot configuration separates row fields, column fields, value field, aggregate,
fill value, sort behavior, and a maximum generated-column limit. Distinct column
keys are counted before reshaping; configurations above the limit block with an
explicit width error. Preview reports generated columns and an estimated memory peak.

Unpivot identifies stable identifier fields and one or more value fields, with
configurable variable/value output names and keep/drop null-row policy. Both paths
operate only on aligned canonical data.
