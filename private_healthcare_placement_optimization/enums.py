from enum import Enum

class DocumentStatus(Enum):
    IN_REVIEW = "In Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"

    @classmethod
    def choices(cls):
        return [(status.value, status.value) for status in cls]
