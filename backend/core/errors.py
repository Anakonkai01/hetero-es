"""Errors raised by business operations and translated by HTTP adapters."""


class ServiceError(Exception):
    def __init__(self, status_code, detail, *, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
