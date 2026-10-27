from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def string_enum(enum_class: type[StrEnum]) -> SAEnum:
    return SAEnum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )
