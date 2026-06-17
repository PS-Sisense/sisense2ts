"""Sisense Datamodels v2 column type codes -> IR DataType.

Verified against the developer.sisense.com data-types reference (L2021.9+).
The v2 schema gives each column a numeric `type`. Older models used a smaller set
(8=Int, 18=Text, 19=Timestamp); those legacy codes are included below.
"""
from sisense2ts.ir.models import DataType

SISENSE_TYPE_CODES: dict[int, DataType] = {
    0: DataType.INT,       # BigInt
    2: DataType.BOOL,      # Boolean
    3: DataType.STRING,    # Char
    4: DataType.DATETIME,  # Timestamp (DateTime)
    5: DataType.DOUBLE,    # Decimal
    6: DataType.DOUBLE,    # Float
    8: DataType.INT,       # Integer
    13: DataType.DOUBLE,   # Real
    16: DataType.INT,      # SmallInt
    18: DataType.STRING,   # VarChar
    19: DataType.DATETIME,  # Timestamp (legacy, now 4)
    20: DataType.INT,      # TinyInt
    31: DataType.DATE,     # Date
    32: DataType.STRING,   # Time
    40: DataType.DOUBLE,   # Double
    41: DataType.DOUBLE,   # Numeric
    43: DataType.DATETIME,  # TimestampWithTimezone
    44: DataType.STRING,   # TimeWithTimezone
}


def to_datatype(code) -> DataType:
    """Map a Sisense type code (int or numeric string) to an IR DataType."""
    try:
        return SISENSE_TYPE_CODES.get(int(code), DataType.UNKNOWN)
    except (TypeError, ValueError):
        return DataType.UNKNOWN
